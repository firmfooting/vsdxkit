"""Jinja templating for vsdx documents.

Static methods defined here are bound onto VisioFile at import time so the
public API (vis.jinja_render_vsdx(context)) is unchanged.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from jinja2.sandbox import SandboxedEnvironment

from .logging_support import get_logger
from .pages import Page
from .shapes import Shape
from .xmlio import adopt_prefixes

logger = get_logger(__name__)

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


def _template(source: str):
    """Compile document-supplied text in the sandbox. Never use jinja2.Template here."""
    return _ENVIRONMENT.from_string(source)


class JinjaTemplatingMixin:
    # attributes provided by the VisioFile host class
    pages: list[Page]

    def increment_sub_shape_ids(self, shape: Shape, page: Page, id_map: dict[str, int] | None = None) -> dict[str, int]: ...
    def remove_page_by_index(self, index: int) -> None: ...
    def _require_open(self, operation: str) -> None: ...

    def jinja_render_vsdx(self, context: dict[str, object]) -> None:
        """Transform a template VisioFile object using the Jinja language
        The method updates the VisioFile object loaded from the template file, so does not return any value
        Note: vsdx specific extensions are available such as `{% for item in list %}` statements with no `{% endfor %}`

        :param context: A dictionary containing values that can be accessed by the Jinja processor
        :type context: dict

        :return: None
        """
        # up front, not at the page.xml assignment below: shape text is
        # rewritten in place before that line, so a late refusal would leave
        # earlier pages rendered and later ones untouched
        self._require_open("VisioFile.jinja_render_vsdx()")
        # parse each shape in each page as Jinja2 template with context
        pages_to_remove: list[Page] = []
        for page in self.pages:  # type: Page
            # check if page should be removed
            if JinjaTemplatingMixin.jinja_page_showif(page, context):
                loop_shape_ids = list()
                for shapes_by_id in page._shapes:  # type: Shape
                    JinjaTemplatingMixin.jinja_render_shape(shape=shapes_by_id, context=context, loop_shape_ids=loop_shape_ids)

                page_root = page.xml.getroot()
                if page_root is None:
                    continue
                source = ET.tostring(page_root, encoding="unicode")
                source = JinjaTemplatingMixin.unescape_jinja_statements(source)  # unescape chars like < and > inside {%...%}
                template = _template(source)
                output = template.render(context)
                rendered = ET.fromstring(output)
                # the round trip through a string drops the prefixes the
                # page declared, and a rendered page is still that page
                adopt_prefixes(rendered, page_root)
                page.xml = ET.ElementTree(rendered)

                # update loop shape IDs which have been duplicated by Jinja template
                for shape_id in loop_shape_ids:
                    shapes_by_id = page._find_shapes_by_id(shape_id)  # type: list[Shape]
                    if shapes_by_id and len(shapes_by_id) > 1:
                        delta = 0.0
                        for shape in shapes_by_id[1:]:  # from the 2nd onwards - leaving original unchanged
                            # increment each new shape duplicated by the jinja loop
                            self.increment_sub_shape_ids(shape, page)
                            delta += shape.height or 0.0  # automatically move each duplicate down
                            shape.move(0, -delta)  # move duplicated shapes so they are visible
            else:
                # note page to remove after this loop has completed
                pages_to_remove.append(page)
        # remove pages after processing
        for p in pages_to_remove:
            logger.debug("Removing page:'%s' index:%s", p.name, p.index_num)
            if p.index_num is not None:
                self.remove_page_by_index(p.index_num)

    @staticmethod
    def jinja_render_shape(shape: Shape, context: dict[str, object], loop_shape_ids: list[str]) -> None:
        prev_shape = None
        for s in shape.child_shapes:  # type: Shape
            # manage for loops in template
            loop_shape_id = JinjaTemplatingMixin.jinja_create_for_loop_if(s, prev_shape)
            if loop_shape_id:
                loop_shape_ids.append(loop_shape_id)
            prev_shape = s
            # manage 'set self' statements
            JinjaTemplatingMixin.jinja_set_selfs(s, context)
            JinjaTemplatingMixin.jinja_render_shape(shape=s, context=context, loop_shape_ids=loop_shape_ids)

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

    @staticmethod
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
                raise ValueError(f"{statement} refers to self.{name}, which is not an attribute of a shape") from error

        return JinjaTemplatingMixin._SELF_REFERENCE.sub(resolve, expression)

    @staticmethod
    def jinja_set_selfs(shape: Shape, context: dict[str, object]) -> None:
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
        for statement in JinjaTemplatingMixin._SET_SELF_STATEMENT.finditer(jinja_source):
            property_name, expression = statement.group(1), statement.group(2)
            expression = JinjaTemplatingMixin._resolve_self_references(shape, expression, statement.group(0))
            value = "{{ " + expression + " }}"  # Jinja to be processed
            # use Jinja template to calculate any self refs found
            template = _template(value)  # value might be '{{ 1.0+2.4*3 }}'
            value = template.render(context)
            if property_name in JinjaTemplatingMixin._SETTABLE:
                setattr(shape, property_name, value)

        # remove any {% set self %} statements, leaving any remaining text
        matches = re.findall("{% set self.*?%}", jinja_source)
        for m in matches:
            jinja_source = jinja_source.replace(m, "")  # remove Jinja 'set self' statement
        shape.text = jinja_source

    @staticmethod
    def unescape_jinja_statements(jinja_source: str) -> str:
        # unescape any text between {% ... %}
        jinja_source_out = jinja_source
        matches = re.findall("{%(.*?)%}", jinja_source)  # non-greedy search for all {%...%} strings
        for m in matches:
            unescaped = m.replace("&gt;", ">").replace("&lt;", "<")
            jinja_source_out = jinja_source_out.replace(m, unescaped)
        return jinja_source_out

    @staticmethod
    def jinja_create_for_loop_if(shape: Shape, previous_shape: Shape | None) -> str | None:
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
                parent_xml = shape.parent.xml
                # Page.xml is an ElementTree; Shape.xml is an Element
                parent_root = parent_xml.getroot() if isinstance(parent_xml, ET.ElementTree) else parent_xml
                parent_text = parent_root.text or "" if parent_root is not None else ""
                if parent_root is not None:
                    parent_root.text = (
                        parent_text + jinja_loop_text
                    )  # add jinja loop at start of parent, just before this element
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
                parent_xml = shape.parent.xml
                # Page.xml is an ElementTree; Shape.xml is an Element
                parent_root = parent_xml.getroot() if isinstance(parent_xml, ET.ElementTree) else parent_xml
                parent_text = parent_root.text or "" if parent_root is not None else ""
                if parent_root is not None:
                    parent_root.text = (
                        parent_text + jinja_show_if
                    )  # add jinja loop at start of parent, just before this element

            # remove original jinja showif from <Text> tag in element
            shape.text = (shape.text or "").replace(f"{{% showif {show_if} %}}", "")

            # add closing 'endfor' to just inside the shapes element, after last shape
            if shape.xml.tail:  # extend or set text at end of Shape element
                shape.xml.tail += "{% endif %}"
            else:
                shape.xml.tail = "{% endif %}"

        if jinja_loops:
            return shape.ID  # return shape ID if it is a loop, so that duplicate shape IDs can be updated

    @staticmethod
    def jinja_page_showif(page: Page, context: dict[str, object]) -> bool:
        text = page.name
        jinja_source = re.findall(r"{% showif\s(.*?)\s%}", text)
        if len(jinja_source):
            # process last matching value
            template_source = "{{ " + jinja_source[-1] + " }}"
            template = _template(template_source)  # value might be '{{ 1.0+2.4*3 }}'
            value = template.render(context)
            # is the value truthy - i.e. not 0, False, or empty string, tuple, list or dict
            logger.debug(
                "jinja_page_showif(context=%s) statement: %s returns: %s %s", context, template_source, type(value), value
            )
            if value in ["False", "0", "", "()", "[]", "{}"]:
                logger.debug("value in ['False', '0', '', '()', '[]', '{}']")
                return False  # page should be hidden
            # remove jinja statement from page name
            page_name = page.name or ""
            jinja_statement = re.match("{%.*?%}", page_name)
            if jinja_statement:
                page.name = page_name.replace(jinja_statement[0], "")
        return True  # page should be left in
