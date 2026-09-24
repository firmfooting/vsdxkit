"""The finders the collections replaced still answer as they did, and say they are going (#103).

Each is a deprecated shim over `vsdxkit.retired_finders` until 1.0.0, so these
pin what a caller who has not migrated still gets: the first match, a text
match anywhere in the text, a property value compared as text.
"""

import pytest

from vsdxkit.document import Document
from vsdxkit.shapes import Shape

# test2.vsdx: group 9 holds 1 ("Shape Text"), 7 ("Sub-shape 1") and 8 ("Sub-shape 2")
PAGE_FINDERS = [
    ("find_shape_by_id", ("7",), "7"),
    ("find_shapes_by_id", ("7",), ["7"]),
    ("find_shape_by_attr", ("ID", "8"), "8"),
    ("find_shape_by_text", ("Sub-shape",), "7"),
    ("find_shapes_by_text", ("Sub-shape",), ["7", "8", "2", "10"]),
    ("find_shapes_by_regex", (r"^Sub-shape \d$",), ["7", "8", "10"]),
]


def _ids(found):
    if found is None:
        return None
    if isinstance(found, list):
        return [shape.ID for shape in found]
    return found.ID


@pytest.mark.parametrize(("finder", "args", "expected"), PAGE_FINDERS)
def test_a_page_finder_warns_and_answers_as_it_did(vsdx_copy, finder, args, expected):
    """Fails if a Page finder stops warning, or starts matching whole text or refusing a second match."""
    vis = Document.open(vsdx_copy("test2.vsdx"))
    page = vis.pages[0]
    with pytest.warns(
        DeprecationWarning, match=rf"Page\.{finder}\(\) is deprecated .* Use (a comprehension over )?page\.shapes"
    ):
        found = getattr(page, finder)(*args)
    assert _ids(found) == expected


@pytest.mark.parametrize(
    ("finder", "args", "expected"),
    [
        ("find_shape_by_id", ("8",), "8"),
        ("find_shapes_by_id", ("9",), []),  # the shape itself is not inside itself
        ("find_shape_by_text", ("Sub-shape",), "7"),
        ("find_shapes_by_text", ("Sub-shape",), ["7", "8"]),
        ("find_shapes_by_regex", (r"Text$",), ["1"]),
    ],
)
def test_a_shape_finder_searches_inside_the_shape(vsdx_copy, finder, args, expected):
    """Fails if a Shape finder warns about the wrong owner or searches beyond the shape's descendants."""
    vis = Document.open(vsdx_copy("test2.vsdx"))
    group = vis.pages[0].shapes.require_id("9")
    with pytest.warns(
        DeprecationWarning, match=rf"Shape\.{finder}\(\) is deprecated .* Use (a comprehension over )?shape\.descendants"
    ):
        found = getattr(group, finder)(*args)
    assert _ids(found) == expected


def test_the_property_finders_forward_to_the_collection(vsdx_copy):
    """Fails if a property finder stops comparing the value as text, or drops the first-match form."""
    vis = Document.open(vsdx_copy("test6_shape_properties.vsdx"))
    page = vis.pages[0]
    with pytest.warns(DeprecationWarning):
        assert _ids(page.find_shape_by_property_label("my_property_label")) == "1"
    with pytest.warns(DeprecationWarning):
        assert _ids(page.find_shapes_by_property_label("my_property_label")) == ["1", "2"]
    with pytest.warns(DeprecationWarning):
        found = page.find_shape_by_property_label_value("my_property_label", "a different value")
    assert _ids(found) == "2"
    with pytest.warns(DeprecationWarning):
        found = page.find_shapes_by_property_label_value("my_second_property_label", "a different value")
    assert _ids(found) == ["5"]


def test_the_master_finders_match_both_ids(vsdx_copy):
    """Fails if a master finder matches on the master page alone."""
    vis = Document.open(vsdx_copy("test5_master.vsdx"))
    page = vis.pages[0]
    sub_shape = page.shapes.require_id("2")
    with pytest.warns(DeprecationWarning, match=r"Page\.find_shapes_with_same_master\(\)"):
        assert _ids(page.find_shapes_with_same_master(sub_shape)) == ["2", "4"]
    group = page.shapes.require_id("1")
    with pytest.warns(DeprecationWarning, match=r"Shape\.find_shapes_by_master\(\)"):
        assert _ids(group.find_shapes_by_master("1", "6")) == ["2"]


def test_get_sub_shapes_warns(vsdx_copy):
    """Fails if `Document.get_sub_shapes` goes quietly, or before 1.0.0."""
    vis = Document.open(vsdx_copy("test2.vsdx"))
    group = vis.pages[0].shapes.require_id("9")
    with pytest.warns(DeprecationWarning, match=r"Document\.get_sub_shapes\(\)"):
        shapes = vis.get_sub_shapes(group.xml)
    assert shapes is not None
    assert [child.attrib["ID"] for child in shapes] == ["1", "7", "8"]


def test_the_warning_points_at_the_caller(vsdx_copy):
    """Fails if the warning names a line inside vsdxkit rather than the code that called the finder."""
    vis = Document.open(vsdx_copy("test2.vsdx"))
    page = vis.pages[0]
    with pytest.warns(DeprecationWarning) as caught:
        page.find_shape_by_id("7")
    assert caught[0].filename == __file__


@pytest.mark.parametrize("finder", ["find_shape_by_property_label", "find_shape_by_property_label_value"])
def test_a_first_match_property_finder_stops_at_the_first_match(vsdx_copy, monkeypatch, finder):
    """Fails if the first-match form reads the properties of shapes after the one it answers."""
    read: list[str | None] = []
    data_properties = Shape.data_properties

    def recording(shape):
        read.append(shape.ID)
        return data_properties.fget(shape)

    vis = Document.open(vsdx_copy("test6_shape_properties.vsdx"))
    page = vis.pages[0]
    order = [shape.ID for shape in page.shapes]
    monkeypatch.setattr(Shape, "data_properties", property(recording))
    args = ("my_property_label",) if finder == "find_shape_by_property_label" else ("my_property_label", "property value")
    with pytest.warns(DeprecationWarning):
        found = getattr(page, finder)(*args)
    assert found is not None
    assert found.ID == "1"
    assert read == order[: order.index("1") + 1]
