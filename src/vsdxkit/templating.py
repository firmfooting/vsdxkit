"""Jinja templating for vsdx documents.

:func:`render_document` renders a document in place;
:meth:`vsdxkit.document.Document.render` calls it. Shape text and page names
are the templates, with vsdx-specific statements: a ``{% for %}`` or
``{% showif %}`` in a shape's text repeats or hides that shape, a
``{% showif %}`` in a page name hides the page, and ``{% set self.x = ... %}``
places a shape.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from logging import Logger
from typing import Protocol

from jinja2.sandbox import SandboxedEnvironment

from vsdxkit.errors import NotFoundError
from vsdxkit.logging_support import get_logger
from vsdxkit.pages import Page, PageCollection
from vsdxkit.shapes import Shape
from vsdxkit.xmlio import adopt_prefixes

logger: Logger = get_logger(__name__)

# Every template rendered here comes out of the .vsdx being processed: shape
# text, shape names, cell formulas. On Jinja's default environment that text is
# executable -- `{{ cycler.__init__.__globals__.os.popen(...) }}` reaches the os
# module and runs shell commands. Rendering a document you did not write would
# mean handing it a shell. The sandbox refuses the attribute access such a
# payload needs while leaving ordinary loops, conditionals and arithmetic alone.
#
# One environment, built once: templates are compiled per shape and per page, so
# a fresh Environment on each call would recompile the filter and test registry
# every time for no benefit.
_ENVIRONMENT = SandboxedEnvironment()

# One `{% set self.<name> = <expression> %}` statement. Both names are bound
# to an identifier rather than left as `.*`: a `.*` on the right-hand side
# is greedy to the end of the statement, so an expression naming two
# attributes yielded one match covering both, and only the first was ever
# substituted. The dot is escaped in both, which it was not before.
# `\s*`, not `\s?`: the pattern that strips these statements back out of the
# text allows any amount of whitespace, so a single optional space here meant
# `{% set self.x  =  2 %}` was removed without ever being assigned.
_SET_SELF_STATEMENT = re.compile(r"{% set self\.([A-Za-z_]\w*)\s*=\s*(.*?) %}")
_SELF_REFERENCE = re.compile(r"self\.([A-Za-z_]\w*)")

# What a statement may assign. Reading stays wider on purpose: an expression
# may reference any attribute of the shape.
_SETTABLE = ("x", "y")


class RenderTarget(Protocol):
    """What rendering needs from a document: its pages.

    Each page renumbers the copies a ``{% for %}`` loop makes of its shapes.
    """

    @property
    def pages(self) -> PageCollection: ...


def _template(source: str):
    """Compile document-supplied text in the sandbox. Never use jinja2.Template here."""
    return _ENVIRONMENT.from_string(source)


def render_document(document: RenderTarget, context: Mapping[str, object]) -> None:
    """Render `document` as a Jinja template, in place.

    Shape text, and page names, are Jinja templates. vsdx-specific
    extensions are available, such as `{% for item in list %}` statements
    with no `{% endfor %}`.

    :param document: the document to render, usually a :class:`vsdxkit.document.Document`
    :param context: the values the templates can refer to
    """
    # parse each shape in each page as Jinja2 template with context
    pages_to_remove: list[Page] = []
    for page in document.pages:  # type: Page
        # check if page should be removed
        if _page_is_shown(page, context):
            loop_shape_ids = list()
            shown_before = page._shape_ids()
            _render_statements(shape=page, context=context, loop_shape_ids=loop_shape_ids)

            page_root = page.xml.getroot()
            if page_root is None:
                continue
            source = ET.tostring(page_root, encoding="unicode")
            source = _unescape_statements(source)  # unescape chars like < and > inside {%...%}
            template = _template(source)
            output = template.render(context)
            rendered = ET.fromstring(output)
            # the round trip through a string drops the prefixes the
            # page declared, and a rendered page is still that page
            adopt_prefixes(rendered, page_root)
            page.xml = ET.ElementTree(rendered)

            # update loop shape IDs which have been duplicated by Jinja template
            for shape_id in loop_shape_ids:
                # every copy the loop made carries the template shape's ID
                shapes_by_id = [shape for shape in page.shapes if shape_id == shape.ID]
                if shapes_by_id and len(shapes_by_id) > 1:
                    delta = 0.0
                    for shape in shapes_by_id[1:]:  # from the 2nd onwards - leaving original unchanged
                        # give each copy the loop made IDs of its own, and its formulas with them
                        page._renumber_shape_ids(shape.xml)
                        delta += shape.height or 0.0  # automatically move each duplicate down
                        shape.move(0, -delta)  # move duplicated shapes so they are visible

            # a shape a showif rendered out is deleted like any other: the
            # connectors glued to it and the records naming it go too
            hidden = shown_before - page._shape_ids()
            if hidden:
                page._delete((), hidden)
        else:
            # note page to remove after this loop has completed
            pages_to_remove.append(page)
    # remove pages after processing
    for p in pages_to_remove:
        logger.debug("Removing page:'%s' index:%s", p.name, p.index_num)
        if p.index_num is not None:
            document.pages.delete(p)


def _render_statements(shape: Page | Shape, context: Mapping[str, object], loop_shape_ids: list[str]) -> None:
    """Render the statements in the text of every shape inside `shape`, a page or a group."""
    prev_shape = None
    for s in shape._children():  # type: Shape
        # manage for loops in template
        loop_shape_id = _open_block(s, prev_shape)
        if loop_shape_id:
            loop_shape_ids.append(loop_shape_id)
        prev_shape = s
        # manage 'set self' statements
        _apply_set_self(s, context)
        _render_statements(shape=s, context=context, loop_shape_ids=loop_shape_ids)


def _resolve_self_references(shape: Shape, expression: str, statement: str) -> str:
    """Replace each `self.<name>` in `expression` with the shape's value.

    One pass, not one `str.replace` per name: replacing them one at a time
    rewrites `self.ab` inside `self.abc`, because the names come back in the
    order they appear rather than longest first.
    """

    def resolve(reference: re.Match[str]) -> str:
        name = reference.group(1)
        try:
            return str(getattr(shape, name))
        except AttributeError as error:
            # Chained, not suppressed: a property that raises AttributeError
            # from inside its own getter arrives here too, and reporting
            # that as "no such attribute" would bury the real fault.
            raise NotFoundError(f"{statement} refers to self.{name}, which is not an attribute of a shape") from error

    return _SELF_REFERENCE.sub(resolve, expression)


def _apply_set_self(shape: Shape, context: Mapping[str, object]) -> None:
    """Apply every `{% set self.x = ... %}` statement in the shape's text.

    The expression may reference the shape's own attributes as `self.<name>`,
    including more than one in the same expression. Each is replaced by the
    shape's current value before the expression is rendered, so `self.x`
    means the value on the way in, not the one being assigned.

    Only `x` and `y` can be assigned. A statement assigning anything else is
    still evaluated and still removed from the text, but the result is
    discarded -- longstanding behaviour, and a trap worth knowing about.
    """
    jinja_source = shape.text or ""
    for statement in _SET_SELF_STATEMENT.finditer(jinja_source):
        property_name, expression = statement.group(1), statement.group(2)
        expression = _resolve_self_references(shape, expression, statement.group(0))
        value = "{{ " + expression + " }}"  # Jinja to be processed
        # use Jinja template to calculate any self refs found
        template = _template(value)  # value might be '{{ 1.0+2.4*3 }}'
        value = template.render(context)
        if property_name in _SETTABLE:
            setattr(shape, property_name, value)

    # remove any {% set self %} statements, leaving any remaining text
    matches = re.findall("{% set self.*?%}", jinja_source)
    for m in matches:
        jinja_source = jinja_source.replace(m, "")  # remove Jinja 'set self' statement
    shape.text = jinja_source


def _unescape_statements(jinja_source: str) -> str:
    # unescape any text between {% ... %}
    jinja_source_out = jinja_source
    matches = re.findall("{%(.*?)%}", jinja_source)  # non-greedy search for all {%...%} strings
    for m in matches:
        unescaped = m.replace("&gt;", ">").replace("&lt;", "<")
        jinja_source_out = jinja_source_out.replace(m, unescaped)
    return jinja_source_out


def _open_block(shape: Shape, previous_shape: Shape | None) -> str | None:
    # update a Shapes tag where text looks like a jinja {% for xxxx %} loop
    # move text to start of Shapes tag and add {% endfor %} at end of tag
    text = shape.text

    # use regex to find all loops
    jinja_loops = re.findall(r"{% for\s(.*?)\s%}", text)

    for loop in jinja_loops:
        jinja_loop_text = f"{{% for {loop} %}}"
        # move the for loop to start of shapes element (just before first Shape element)
        if previous_shape:
            if previous_shape.xml.tail:
                previous_shape.xml.tail += jinja_loop_text
            else:
                previous_shape.xml.tail = jinja_loop_text  # add jinja loop text after previous shape, before this element
        else:
            # at the start of the Shapes element the shape sits in, just
            # before it: the {% end... %} goes on its tail, inside the same element
            container = shape._container()
            if container is not None:
                container.text = (container.text or "") + jinja_loop_text
        shape.text = (shape.text or "").replace(jinja_loop_text, "")  # remove jinja loop from <Text> tag in element

        # add closing 'endfor' to just inside the shapes element, after last shape
        if shape.xml.tail:  # extend or set text at end of Shape element
            shape.xml.tail += "{% endfor %}"
        else:
            shape.xml.tail = "{% endfor %}"

    jinja_show_ifs = re.findall(r"{% showif\s(.*?)\s%}", text)  # find all showif statements
    # jinja_show_if - translate non-standard {% showif statement %} to valid jinja if statement
    for show_if in jinja_show_ifs:
        jinja_show_if = f"{{% if {show_if} %}}"  # translate to actual jinja if statement
        # move the for loop to start of shapes element (just before first Shape element)
        if previous_shape:
            previous_shape.xml.tail = (previous_shape.xml.tail or "") + jinja_show_if
        else:
            # at the start of the Shapes element the shape sits in, just
            # before it: the {% end... %} goes on its tail, inside the same element
            container = shape._container()
            if container is not None:
                container.text = (container.text or "") + jinja_show_if

        # remove original jinja showif from <Text> tag in element
        shape.text = (shape.text or "").replace(f"{{% showif {show_if} %}}", "")

        # add closing 'endfor' to just inside the shapes element, after last shape
        if shape.xml.tail:  # extend or set text at end of Shape element
            shape.xml.tail += "{% endif %}"
        else:
            shape.xml.tail = "{% endif %}"

    if jinja_loops:
        return shape.ID  # return shape ID if it is a loop, so that duplicate shape IDs can be updated


def _page_is_shown(page: Page, context: Mapping[str, object]) -> bool:
    text = page.name
    jinja_source = re.findall(r"{% showif\s(.*?)\s%}", text)
    if len(jinja_source):
        # process last matching value
        template_source = "{{ " + jinja_source[-1] + " }}"
        template = _template(template_source)  # value might be '{{ 1.0+2.4*3 }}'
        value = template.render(context)
        # is the value truthy - i.e. not 0, False, or empty string, tuple, list or dict
        logger.debug("_page_is_shown(context=%s) statement: %s returns: %s %s", context, template_source, type(value), value)
        if value in ["False", "0", "", "()", "[]", "{}"]:
            logger.debug("value in ['False', '0', '', '()', '[]', '{}']")
            return False  # page should be hidden
        # remove jinja statement from page name
        page_name = page.name or ""
        jinja_statement = re.match("{%.*?%}", page_name)
        if jinja_statement:
            page.name = page_name.replace(jinja_statement[0], "")
    return True  # page should be left in
