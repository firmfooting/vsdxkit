"""A page name is a template, and its ``{% showif %}`` is judged as a shape's is (Phase 7, F2 and F3).

``Document.render``'s docstring and ``docs/templating.rst`` both said page
names are Jinja templates. They were not: only a ``{% showif %}`` in a name
was read, its expression was judged by the string it rendered to, and it was
taken out of the name only when it opened the name.
"""

import zipfile

import pytest
from jinja2.exceptions import TemplateSyntaxError

from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError


def _render_page_and_shape(vsdx_copy, value: object) -> tuple[bool, bool]:
    """Render test1 with one page and one shape behind ``{% showif flag %}``: is each kept?"""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    vis.pages[1].name = "{% showif flag %}Behind a showif"
    shape = vis.pages[0].children.require_id("1")
    shape.text = "{% showif flag %}Behind a showif"

    vis.render({"flag": value})

    page_kept = [page.name for page in vis.pages] == ["Page-1", "Behind a showif", "Page-3"]
    return page_kept, vis.pages[0].shapes.by_id("1") is not None


@pytest.mark.parametrize(
    "value",
    [True, 1, "yes", None, 0.0, 0, "", set(), [], {}, False],
    ids=repr,
)
def test_a_page_showif_keeps_the_page_exactly_when_a_shape_showif_keeps_the_shape(vsdx_copy, value):
    """Fails if a page and a shape behind the same showif part ways.

    The page's expression was rendered to a string and looked up in a list of
    falsy spellings, so ``None``, ``0.0`` and ``set()`` kept the page while
    the shape went.
    """
    page_kept, shape_kept = _render_page_and_shape(vsdx_copy, value)

    assert page_kept == shape_kept == bool(value)


@pytest.mark.parametrize("value", ["0", "False", "no"])
def test_a_page_showif_on_a_non_empty_string_keeps_the_page(vsdx_copy, value):
    """Fails if a string that spells a false value hides the page: it is a non-empty string, and true.

    A context read from a CSV file or the environment carries strings. 0.x
    and 1.0 before Phase 7 hid a page for ``"0"`` and ``"False"`` and kept
    it for ``"no"``, while a shape behind the same showif stayed for all three.
    """
    page_kept, shape_kept = _render_page_and_shape(vsdx_copy, value)

    assert page_kept and shape_kept


@pytest.mark.parametrize(
    ("first", "second", "kept"),
    [(True, True, True), (True, False, False), (False, True, False)],
)
def test_a_page_with_two_showifs_is_kept_only_when_both_are_true(vsdx_copy, first, second, kept):
    """Fails if one showif in a page name decides alone, as the last one did.

    A shape with two showifs sits inside two ``{% if %}`` blocks, and a page
    is judged as a shape is.
    """
    vis = Document.open(vsdx_copy("test1.vsdx"))
    vis.pages[1].name = "{% showif first %}{% showif second %}Both"

    vis.render({"first": first, "second": second})

    assert ("Both" in [page.name for page in vis.pages]) == kept


def test_a_page_name_is_rendered_as_a_template(vsdx_copy, tmp_path):
    """Fails if ``{{ title }}`` in a page name survives the render, in pages.xml or in app.xml."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    vis.pages[0].name = "{{ title }}"

    vis.render({"title": "Quarterly"})
    saved = vis.save(tmp_path / "rendered.vsdx")

    assert [page.name for page in Document.open(saved).pages] == ["Quarterly", "Page-2", "Page-3"]
    with zipfile.ZipFile(saved) as archive:
        app_xml = archive.read("docProps/app.xml").decode("utf-8")
    assert "Quarterly" in app_xml
    assert "{{ title }}" not in app_xml


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("{% showif flag %}Report", "Report"),
        ("Report{% showif flag %}", "Report"),
        ("Q3 {% showif flag %}report", "Q3 report"),
    ],
)
def test_a_showif_anywhere_in_a_page_name_is_taken_out_of_it(vsdx_copy, name, expected):
    """Fails if a showif that does not open the name stays in it, as it did with ``re.match``."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    vis.pages[1].name = name

    vis.render({"flag": True})

    assert vis.pages[1].name == expected


def test_a_page_name_with_a_showif_and_an_expression_is_judged_then_rendered(vsdx_copy):
    """Fails if the expression in a kept page's name is not rendered, or the showif is left for Jinja to reject."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    vis.pages[1].name = "{% showif flag %}{{ quarter }} report"
    vis.pages[2].name = "{% showif not flag %}{{ quarter }} summary"

    vis.render({"flag": True, "quarter": "Q3"})

    assert [page.name for page in vis.pages] == ["Page-1", "Q3 report"]


def test_a_page_name_without_a_template_is_not_rewritten(vsdx_copy):
    """Fails if a render sets the name of a page it has nothing to render in.

    Setting a name writes ``Name`` and ``NameU`` both; a page whose universal
    name differs from its local one would lose it.
    """
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    element = page._page_xml()
    element.attrib["NameU"] = "Universal"
    element.attrib["Name"] = "Local"

    vis.render({})

    assert (element.attrib["Name"], element.attrib["NameU"]) == ("Local", "Universal")


def test_two_page_names_that_render_alike_are_refused_before_anything_changes(vsdx_copy):
    """Fails if render writes a document in which two pages share a name.

    Visio keeps page names unique and ``pages.by_name`` refuses a repeat, so
    the render raises before it changes any page or shape.
    """
    vis = Document.open(vsdx_copy("test1.vsdx"))
    vis.pages[1].name = "{{ first }}"
    vis.pages[2].name = "{{ second }}{% showif flag %}"
    names = [page.name for page in vis.pages]

    with pytest.raises(InvalidOperationError, match="two pages would be called 'Same'"):
        vis.render({"first": "Same", "second": "Same", "flag": True})

    assert [page.name for page in vis.pages] == names


def test_a_page_the_render_removes_does_not_count_toward_a_repeated_name(vsdx_copy):
    """Fails if a page a ``showif`` removes still blocks the name it would have had."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    vis.pages[1].name = "{{ first }}"
    vis.pages[2].name = "{{ second }}{% showif flag %}"

    vis.render({"first": "Same", "second": "Same", "flag": False})

    assert [page.name for page in vis.pages] == ["Page-1", "Same"]


def test_a_broken_template_in_a_page_name_fails_as_broken_shape_text_does(vsdx_copy):
    """Fails if the page path's exception differs from the shape path's for the same broken template.

    Both a page's name and a shape's text go through ``_template`` and the
    same sandboxed ``_ENVIRONMENT``, so a syntax error in either should raise
    the same way. Nothing pinned that before: the docstring's "as `{% if %}`
    would" was a claim of parity, not a test of it.
    """
    broken = "{% if %}Broken"

    page_vis = Document.open(vsdx_copy("test1.vsdx"))
    page_vis.pages[1].name = broken
    with pytest.raises(TemplateSyntaxError) as page_error:
        page_vis.render({})

    shape_vis = Document.open(vsdx_copy("test1.vsdx"))
    shape_vis.pages[0].children.require_id("1").text = broken
    with pytest.raises(TemplateSyntaxError) as shape_error:
        shape_vis.render({})

    assert type(page_error.value) is type(shape_error.value)


def test_a_missing_variable_in_a_page_name_renders_as_it_does_in_shape_text(vsdx_copy):
    """Fails if a page name's undefined variable renders differently from a shape's.

    Jinja's default ``Undefined`` renders an unknown name as an empty string
    rather than raising, in a page's name exactly as in a shape's text.
    """
    holding_missing = "{{ missing }} report"

    page_vis = Document.open(vsdx_copy("test1.vsdx"))
    page_vis.pages[1].name = holding_missing
    page_vis.render({})

    shape_vis = Document.open(vsdx_copy("test1.vsdx"))
    shape = shape_vis.pages[0].children.require_id("1")
    shape.text = holding_missing
    shape_vis.render({})
    shape_after = shape_vis.pages[0].shapes.by_id("1")

    assert page_vis.pages[1].name == shape_after.text == " report"
