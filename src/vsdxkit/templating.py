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

from vsdxkit._logging_support import get_logger
from vsdxkit._xmlio import adopt_prefixes
from vsdxkit.errors import NotFoundError
from vsdxkit.pages import Page, PageCollection
from vsdxkit.shapes import Shape

_logger: Logger = get_logger(__name__)
"""This module's logger, under the ``vsdxkit`` hierarchy the library never configures a handler for."""

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
"""The one Jinja environment every template here is compiled in: sandboxed, because the templates come from the document."""

# One `{% set self.<name> = <expression> %}` statement. Both names are bound
# to an identifier rather than left as `.*`: a `.*` on the right-hand side
# is greedy to the end of the statement, so an expression naming two
# attributes yielded one match covering both, and only the first was ever
# substituted. The dot is escaped in both, which it was not before.
# `\s*`, not `\s?`: the pattern that strips these statements back out of the
# text allows any amount of whitespace, so a single optional space here meant
# `{% set self.x  =  2 %}` was removed without ever being assigned.
_SET_SELF_STATEMENT = re.compile(r"{% set self\.([A-Za-z_]\w*)\s*=\s*(.*?) %}")
"""One `{% set self.<name> = <expression> %}` in a shape's text: group 1 is the name, group 2 the expression."""
_SELF_REFERENCE = re.compile(r"self\.([A-Za-z_]\w*)")
"""One `self.<name>` in a set statement's expression, group 1 the name, for `_resolve_self_references` to replace."""

# What a statement may assign. Reading stays wider on purpose: an expression
# may reference any attribute of the shape.
_SETTABLE = ("x", "y")
"""The shape attributes a `{% set self.<name> = ... %}` statement writes; any other name is evaluated and discarded."""

# A `{% showif <expression> %}` in a page name, anywhere in it. `findall`
# gives the expressions; `sub` removes whole statements, since it replaces the
# match and not the group. The statement is not Jinja, so it is taken out of
# the name before the name is rendered.
_PAGE_SHOWIF = re.compile(r"{% showif\s(.*?)\s%}")
"""A `{% showif ... %}` in a page name: `_page_is_shown` evaluates each group 1, and `_render_page_name` removes each whole match."""


class RenderTarget(Protocol):
    """What rendering needs from a document: its pages.

    Each page renumbers the copies a ``{% for %}`` loop makes of its shapes.
    """

    @property
    def pages(self) -> PageCollection:
        """The document's pages, in order: rendering reads each one's name and shapes, and deletes a page a ``{% showif %}`` hides."""
        ...


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
            _render_page_name(page, context)
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
        _logger.debug("Removing page:'%s' index:%s", p.name, p.index_num)
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
        """The shape's value for one `self.<name>`, as a string; a name the shape lacks raises `NotFoundError`."""
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
    """`jinja_source`, a page serialised to XML, with ``&gt;`` and ``&lt;`` inside each ``{% ... %}`` turned back into ``>`` and ``<`` for Jinja to read."""
    # unescape any text between {% ... %}
    jinja_source_out = jinja_source
    matches = re.findall("{%(.*?)%}", jinja_source)  # non-greedy search for all {%...%} strings
    for m in matches:
        unescaped = m.replace("&gt;", ">").replace("&lt;", "<")
        jinja_source_out = jinja_source_out.replace(m, unescaped)
    return jinja_source_out


def _open_block(shape: Shape, previous_shape: Shape | None) -> str | None:
    """Wrap `shape` in the Jinja blocks its text opens, and return its ID if one is a loop.

    Each ``{% for %}`` and ``{% showif %}`` in the shape's text is taken out of
    it and written into the XML around the shape's element: the opening tag
    on `previous_shape`'s tail, or at the start of the ``<Shapes>`` element
    the shape sits in when it is the first, and ``{% endfor %}`` or
    ``{% endif %}`` on the shape's own tail. A ``showif`` becomes an ``if``.
    Rendering the page then repeats or hides that one shape. The ID is
    returned so the copies a loop makes, which all carry it, can be given IDs
    of their own.
    """
    # wrap this shape in each jinja {% for xxxx %} loop its text holds: move
    # the statement to just before the shape and add {% endfor %} just after it
    text = shape.text

    # use regex to find all loops
    jinja_loops = re.findall(r"{% for\s(.*?)\s%}", text)

    for loop in jinja_loops:
        jinja_loop_text = f"{{% for {loop} %}}"
        # move the for loop to just before this shape: the previous shape's tail, or the start of the Shapes element
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

        # add closing 'endfor' just after this shape, on its tail
        if shape.xml.tail:  # extend or set text at end of Shape element
            shape.xml.tail += "{% endfor %}"
        else:
            shape.xml.tail = "{% endfor %}"

    jinja_show_ifs = re.findall(r"{% showif\s(.*?)\s%}", text)  # find all showif statements
    # jinja_show_if - translate non-standard {% showif statement %} to valid jinja if statement
    for show_if in jinja_show_ifs:
        jinja_show_if = f"{{% if {show_if} %}}"  # translate to actual jinja if statement
        # move the if statement to just before this shape: the previous shape's tail, or the start of the Shapes element
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

        # add closing 'endif' just after this shape, on its tail
        if shape.xml.tail:  # extend or set text at end of Shape element
            shape.xml.tail += "{% endif %}"
        else:
            shape.xml.tail = "{% endif %}"

    if jinja_loops:
        return shape.ID  # return shape ID if it is a loop, so that duplicate shape IDs can be updated


def _page_is_shown(page: Page, context: Mapping[str, object]) -> bool:
    """Whether `page` survives the render: every ``{% showif %}`` in its name is true.

    Each expression is evaluated as ``{% if %}`` evaluates one, so a page is
    kept exactly when a shape with the same ``showif`` would be. Its rendered
    string was tested before, which kept a page for ``None`` or ``0.0`` and
    dropped one for the strings ``"0"`` and ``"False"`` (Phase 7). A showif
    may sit anywhere in the name, and a name with none is always kept.
    """
    for expression in _PAGE_SHOWIF.findall(page.name):
        shown = bool(_ENVIRONMENT.compile_expression(expression)(context))
        _logger.debug("page %r: showif %s is %s", page.name, expression, shown)
        if not shown:
            return False
    return True


def _render_page_name(page: Page, context: Mapping[str, object]) -> None:
    """Render a kept page's name as a template, without its ``{% showif %}`` statements.

    The name is set through :attr:`Page.name`, which renames the page's title
    in app.xml as well, and only when rendering changed it: setting a name
    writes both ``Name`` and ``NameU``, and a page whose two differ would
    otherwise lose its universal name to a render that changed nothing.
    """
    name = page.name
    rendered = _template(_PAGE_SHOWIF.sub("", name)).render(context)
    if rendered != name:
        page.name = rendered
