"""Mutating a closed document raises instead of editing state that can never be saved.

`save_vsdx` refuses a closed document; the operations that build the state it
would have written did not, so the failure surfaced at the save, or never
(issue #242). `create_shape` and `Connect.create` were also the only way to
make a `Media` that nothing would ever close.
"""

import xml.etree.ElementTree as ET
from collections.abc import Callable

import pytest

import vsdx

BASE = "test4_connectors.vsdx"

Mutation = Callable[[vsdx.VisioFile, vsdx.Page, vsdx.Shape, vsdx.Shape], object]


@pytest.fixture
def closed_document(vsdx_copy):
    """Handles taken while open, so each test mutates through a live reference."""
    vis = vsdx.VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    shapes = page.child_shapes
    connect = page.connects[0]
    vis.close_vsdx()
    return vis, page, shapes[0], shapes[1], connect


DOCUMENT_MUTATIONS: dict[str, Mutation] = {
    "create_shape": lambda vis, page, a, b: vis.create_shape(page, "PALETTE_PROCESS", 1.0, 1.0),
    "copy_shape": lambda vis, page, a, b: vis.copy_shape(a.xml, page),
    "insert_shape": lambda vis, page, a, b: vis.insert_shape(a.xml, page.xml.getroot(), page, page.filename),
    "increment_shape_ids": lambda vis, page, a, b: vis.increment_shape_ids(a.xml, page),
    "increment_sub_shape_ids": lambda vis, page, a, b: vis.increment_sub_shape_ids(a, page),
    "renumber_shape_ids": lambda vis, page, a, b: vis.renumber_shape_ids(a.xml, page),
    "add_page": lambda vis, page, a, b: vis.add_page("new"),
    "add_page_at": lambda vis, page, a, b: vis.add_page_at(0, "new"),
    "copy_page": lambda vis, page, a, b: vis.copy_page(page),
    "remove_page_by_index": lambda vis, page, a, b: vis.remove_page_by_index(0),
    "remove_page_by_name": lambda vis, page, a, b: vis.remove_page_by_name(page.name),
    "jinja_render_vsdx": lambda vis, page, a, b: vis.jinja_render_vsdx({"x": 1}),
    "save_vsdx": lambda vis, page, a, b: vis.save_vsdx(),
}

PAGE_MUTATIONS: dict[str, Mutation] = {
    "name": lambda vis, page, a, b: setattr(page, "name", "renamed"),
    "background": lambda vis, page, a, b: setattr(page, "background", True),
    "width": lambda vis, page, a, b: setattr(page, "width", 10.0),
    "height": lambda vis, page, a, b: setattr(page, "height", 10.0),
    "xml": lambda vis, page, a, b: setattr(page, "xml", page.xml),
    "apply_text_context": lambda vis, page, a, b: page.apply_text_context({"x": 1}),
    "find_replace": lambda vis, page, a, b: page.find_replace("a", "b"),
    "connect_shapes": lambda vis, page, a, b: page.connect_shapes(a, b),
    "add_swimlane": lambda vis, page, a, b: page.add_swimlane("lane"),
    "add_shape_to_lane": lambda vis, page, a, b: page.add_shape_to_lane(a, b),
    "reanchor_connector": lambda vis, page, a, b: page.reanchor_connector(a, from_shape=b),
    "delete_shape": lambda vis, page, a, b: page.delete_shape(a),
    "remove_connect_records": lambda vis, page, a, b: page.remove_connect_records([a.ID]),
}

ALL_MUTATIONS: dict[str, Mutation] = DOCUMENT_MUTATIONS | PAGE_MUTATIONS


@pytest.mark.parametrize("mutation", DOCUMENT_MUTATIONS.values(), ids=list(DOCUMENT_MUTATIONS))
def test_document_mutation_after_close_raises(closed_document, mutation):
    vis, page, shape_a, shape_b, _ = closed_document
    with pytest.raises(vsdx.VisioFileNotOpen):
        mutation(vis, page, shape_a, shape_b)


@pytest.mark.parametrize("mutation", PAGE_MUTATIONS.values(), ids=list(PAGE_MUTATIONS))
def test_page_mutation_after_close_raises(closed_document, mutation):
    vis, page, shape_a, shape_b, _ = closed_document
    with pytest.raises(vsdx.VisioFileNotOpen):
        mutation(vis, page, shape_a, shape_b)


def test_add_connect_after_close_raises(closed_document):
    """Kept out of the table: the Connect has to be taken before the close."""
    _, page, _, _, connect = closed_document
    with pytest.raises(vsdx.VisioFileNotOpen):
        page.add_connect(connect)


@pytest.mark.parametrize("mutation", ALL_MUTATIONS.values(), ids=list(ALL_MUTATIONS))
def test_a_refused_mutation_changes_nothing(closed_document, mutation):
    """The guard runs before the work, not partway through it.

    A guard reached late leaves half a rename or half a rendered template
    behind, which is worse than the leniency it replaces.
    """
    vis, page, shape_a, shape_b, _ = closed_document
    before = [ET.tostring(p.xml.getroot()) for p in vis.pages]
    page_names = vis.get_page_names()

    with pytest.raises(vsdx.VisioFileNotOpen):
        mutation(vis, page, shape_a, shape_b)

    assert [ET.tostring(p.xml.getroot()) for p in vis.pages] == before
    assert vis.get_page_names() == page_names


def test_deprecated_name_aliases_are_guarded(closed_document):
    _, page, _, _, _ = closed_document
    with pytest.deprecated_call(), pytest.raises(vsdx.VisioFileNotOpen):
        page.set_name("renamed")
    with pytest.deprecated_call(), pytest.raises(vsdx.VisioFileNotOpen):
        page.page_name = "renamed"


def test_reads_still_work_after_close(closed_document):
    """The guard covers mutation only: the in-memory document stays inspectable."""
    vis, page, shape_a, _, _ = closed_document
    assert page.name
    assert page.width > 0
    assert page.find_shape_by_id(str(shape_a.ID)) is not None
    assert vis.get_page_names()
    with pytest.deprecated_call():
        assert page.page_name == page.name
    with pytest.deprecated_call():
        assert page.shapes


def test_the_guard_follows_the_page_not_the_receiver(vsdx_copy):
    """`Shape.copy` runs on the source document but edits the destination.

    Guarding the receiver instead would refuse a copy out of a closed source
    into a live document, and wave through a copy into a closed one.
    """
    source = vsdx.VisioFile(vsdx_copy(BASE))
    destination = vsdx.VisioFile(vsdx_copy("test1.vsdx"))
    from_closed_source = source.pages[0].child_shapes[0]
    into_closed_destination = destination.pages[0].child_shapes[0]

    source.close_vsdx()
    copied = from_closed_source.copy(destination.pages[0])
    assert destination.pages[0].find_shape_by_id(str(copied.ID)) is not None

    destination.close_vsdx()
    with pytest.raises(vsdx.VisioFileNotOpen):
        into_closed_destination.copy(destination.pages[0])


def record_media_builds(monkeypatch) -> list[vsdx.Media]:
    """Record every Media built for the duration of a test."""
    built: list[vsdx.Media] = []
    real_media = vsdx.Media

    class RecordingMedia(real_media):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            built.append(self)
            super().__init__()

    monkeypatch.setattr(vsdx, "Media", RecordingMedia)
    return built


def test_create_shape_after_close_builds_no_second_donor(vsdx_copy, monkeypatch):
    built = record_media_builds(monkeypatch)
    vis = vsdx.VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    vis.create_shape(page, "PALETTE_PROCESS", 1.0, 1.0, text="A")
    assert len(built) == 1

    vis.close_vsdx()
    with pytest.raises(vsdx.VisioFileNotOpen):
        vis.create_shape(page, "PALETTE_PROCESS", 2.0, 2.0, text="B")

    assert len(built) == 1, "a closed document built a second donor pair that nothing will close"
    # the pair that does exist was closed, so no donor outlives the document
    assert built[0]._media_vsdx is None and built[0]._palette_vsdx is None
    assert vis._media is None


def test_connect_shapes_after_close_builds_no_donor(vsdx_copy, monkeypatch):
    built = record_media_builds(monkeypatch)
    vis = vsdx.VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    shapes = page.child_shapes

    vis.close_vsdx()
    with pytest.raises(vsdx.VisioFileNotOpen):
        page.connect_shapes(shapes[0], shapes[1])

    assert built == []
    assert vis._media is None
