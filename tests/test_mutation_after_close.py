"""Mutating a closed document raises instead of editing state that can never be saved.

`save_vsdx` refuses a closed document; the operations that build the state it
would have written did not, so the failure surfaced at the save, or never
(issue #242). `create_shape` and `Connect.create` were also the only way to
make a `Media` that nothing would ever close.
"""

import xml.etree.ElementTree as ET
from collections.abc import Callable

import pytest

import vsdxkit

BASE = "test4_connectors.vsdx"

Mutation = Callable[[vsdxkit.VisioFile, vsdxkit.Page, vsdxkit.Shape, vsdxkit.Shape], object]


@pytest.fixture
def closed_document(vsdx_copy):
    """Handles taken while open, so each test mutates through a live reference."""
    vis = vsdxkit.VisioFile(vsdx_copy(BASE))
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
    with pytest.raises(vsdxkit.VisioFileNotOpen):
        mutation(vis, page, shape_a, shape_b)


@pytest.mark.parametrize("mutation", PAGE_MUTATIONS.values(), ids=list(PAGE_MUTATIONS))
def test_page_mutation_after_close_raises(closed_document, mutation):
    vis, page, shape_a, shape_b, _ = closed_document
    with pytest.raises(vsdxkit.VisioFileNotOpen):
        mutation(vis, page, shape_a, shape_b)


def test_add_connect_after_close_raises(closed_document):
    """Kept out of the table: the Connect has to be taken before the close."""
    _, page, _, _, connect = closed_document
    with pytest.raises(vsdxkit.VisioFileNotOpen):
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

    with pytest.raises(vsdxkit.VisioFileNotOpen):
        mutation(vis, page, shape_a, shape_b)

    assert [ET.tostring(p.xml.getroot()) for p in vis.pages] == before
    assert vis.get_page_names() == page_names


def test_deprecated_name_aliases_are_guarded(closed_document):
    _, page, _, _, _ = closed_document
    with pytest.deprecated_call(), pytest.raises(vsdxkit.VisioFileNotOpen):
        page.set_name("renamed")
    with pytest.deprecated_call(), pytest.raises(vsdxkit.VisioFileNotOpen):
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
    source = vsdxkit.VisioFile(vsdx_copy(BASE))
    destination = vsdxkit.VisioFile(vsdx_copy("test1.vsdx"))
    from_closed_source = source.pages[0].child_shapes[0]
    into_closed_destination = destination.pages[0].child_shapes[0]

    source.close_vsdx()
    copied = from_closed_source.copy(destination.pages[0])
    assert destination.pages[0].find_shape_by_id(str(copied.ID)) is not None

    destination.close_vsdx()
    with pytest.raises(vsdxkit.VisioFileNotOpen):
        into_closed_destination.copy(destination.pages[0])


def record_media_builds(monkeypatch) -> list[vsdxkit.Media]:
    """Record every Media built for the duration of a test."""
    built: list[vsdxkit.Media] = []
    real_media = vsdxkit.Media

    class RecordingMedia(real_media):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            built.append(self)
            super().__init__()

    monkeypatch.setattr(vsdxkit, "Media", RecordingMedia)
    return built


def test_create_shape_after_close_builds_no_second_donor(vsdx_copy, monkeypatch):
    built = record_media_builds(monkeypatch)
    vis = vsdxkit.VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    vis.create_shape(page, "PALETTE_PROCESS", 1.0, 1.0, text="A")
    assert len(built) == 1

    vis.close_vsdx()
    with pytest.raises(vsdxkit.VisioFileNotOpen):
        vis.create_shape(page, "PALETTE_PROCESS", 2.0, 2.0, text="B")

    assert len(built) == 1, "a closed document built a second donor pair that nothing will close"
    # the pair that does exist was closed, so no donor outlives the document
    assert built[0]._media_vsdx is None and built[0]._palette_vsdx is None
    assert vis._media is None


def test_connect_shapes_after_close_builds_no_donor(vsdx_copy, monkeypatch):
    built = record_media_builds(monkeypatch)
    vis = vsdxkit.VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    shapes = page.child_shapes

    vis.close_vsdx()
    with pytest.raises(vsdxkit.VisioFileNotOpen):
        page.connect_shapes(shapes[0], shapes[1])

    assert built == []
    assert vis._media is None


def _page_xml(vis: vsdxkit.VisioFile) -> list[bytes]:
    """Every page's XML, master pages included.

    A write through a row a shape inherits lands on the *master* page, so a
    snapshot of `vis.pages` alone would not see it.
    """
    return [ET.tostring(page.xml.getroot()) for page in list(vis.pages) + list(vis.master_pages)]


def _geometry(shape: vsdxkit.Shape) -> vsdxkit.Geometry:
    """The shape's Geometry; fails the test if the fixture shape has none."""
    geometry = shape.geometry
    assert geometry is not None, "fixture shape has no Geometry section"
    return geometry


def _first_row(shape: vsdxkit.Shape) -> vsdxkit.GeometryRow:
    return next(iter(_geometry(shape).rows.values()))


SHAPE_MUTATIONS: dict[str, Mutation] = {
    "text": lambda vis, page, a, b: setattr(a, "text", "changed"),
    "set_cell_value": lambda vis, page, a, b: a.set_cell_value("PinX", 1.0),
    "set_cell_formula": lambda vis, page, a, b: a.set_cell_formula("PinX", "1"),
    "get_or_create_cell": lambda vis, page, a, b: a.get_or_create_cell("PinX", v="1"),
    "x": lambda vis, page, a, b: setattr(a, "x", 1.0),
    "y": lambda vis, page, a, b: setattr(a, "y", 1.0),
    "loc_x": lambda vis, page, a, b: setattr(a, "loc_x", 1.0),
    "loc_y": lambda vis, page, a, b: setattr(a, "loc_y", 1.0),
    "begin_x": lambda vis, page, a, b: setattr(a, "begin_x", 1.0),
    "begin_y": lambda vis, page, a, b: setattr(a, "begin_y", 1.0),
    "end_x": lambda vis, page, a, b: setattr(a, "end_x", 1.0),
    "end_y": lambda vis, page, a, b: setattr(a, "end_y", 1.0),
    "line_to_x": lambda vis, page, a, b: setattr(a, "line_to_x", 1.0),
    "line_to_y": lambda vis, page, a, b: setattr(a, "line_to_y", 1.0),
    "width": lambda vis, page, a, b: setattr(a, "width", 1.0),
    "height": lambda vis, page, a, b: setattr(a, "height", 1.0),
    "angle": lambda vis, page, a, b: setattr(a, "angle", 1.0),
    "line_weight": lambda vis, page, a, b: setattr(a, "line_weight", 0.5),
    "line_color": lambda vis, page, a, b: setattr(a, "line_color", "#ff0000"),
    "fill_color": lambda vis, page, a, b: setattr(a, "fill_color", "#ff0000"),
    "text_color": lambda vis, page, a, b: setattr(a, "text_color", "#ff0000"),
    "end_arrow": lambda vis, page, a, b: setattr(a, "end_arrow", 13),
    "line_style_id": lambda vis, page, a, b: setattr(a, "line_style_id", 4),
    "fill_style_id": lambda vis, page, a, b: setattr(a, "fill_style_id", 4),
    "text_style_id": lambda vis, page, a, b: setattr(a, "text_style_id", 4),
    "geometry": lambda vis, page, a, b: setattr(a, "geometry", None),
    "move": lambda vis, page, a, b: a.move(1.0, 1.0),
    "set_start_and_finish": lambda vis, page, a, b: a.set_start_and_finish((1.0, 1.0), (2.0, 2.0)),
    "apply_text_filter": lambda vis, page, a, b: a.apply_text_filter({"x": 1}),
    "find_replace": lambda vis, page, a, b: a.find_replace("Shape", "X"),
    "append_shape": lambda vis, page, a, b: a.append_shape(b),
}

CELL_MUTATIONS: dict[str, Mutation] = {
    "cell_value": lambda vis, page, a, b: setattr(a.cells["PinX"], "value", 1.0),
    "cell_formula": lambda vis, page, a, b: setattr(a.cells["PinX"], "formula", "1"),
}

GEOMETRY_MUTATIONS: dict[str, Mutation] = {
    "geometry_move": lambda vis, page, a, b: _geometry(a).move(1.0, 1.0),
    "geometry_set_move_to": lambda vis, page, a, b: _geometry(a).set_move_to(1.0, 1.0),
    "geometry_set_line_to": lambda vis, page, a, b: _geometry(a).set_line_to(1.0, 1.0),
    "geometry_row_x": lambda vis, page, a, b: setattr(_first_row(a), "x", 1.0),
    "geometry_row_y": lambda vis, page, a, b: setattr(_first_row(a), "y", 1.0),
    "geometry_row_type": lambda vis, page, a, b: setattr(_first_row(a), "row_type", "LineTo"),
    "geometry_row_index": lambda vis, page, a, b: setattr(_first_row(a), "index", "99"),
    "geometry_row_del_bool": lambda vis, page, a, b: setattr(_first_row(a), "del_bool", True),
    "geometry_cell_value": lambda vis, page, a, b: setattr(_geometry(a).cells[0], "value", "1"),
    "geometry_cell_formula": lambda vis, page, a, b: setattr(_geometry(a).cells[0], "formula", "1"),
    "geometry_cell_name": lambda vis, page, a, b: setattr(_geometry(a).cells[0], "name", "Renamed"),
}

SHAPE_LEVEL_MUTATIONS: dict[str, Mutation] = SHAPE_MUTATIONS | CELL_MUTATIONS | GEOMETRY_MUTATIONS


@pytest.mark.parametrize("mutation", SHAPE_LEVEL_MUTATIONS.values(), ids=list(SHAPE_LEVEL_MUTATIONS))
def test_shape_level_mutation_after_close_raises(closed_document, mutation):
    """Issue #329: the guard belongs to the operation, not to VisioFile and Page alone."""
    vis, page, shape_a, shape_b, _ = closed_document
    with pytest.raises(vsdxkit.VisioFileNotOpen):
        mutation(vis, page, shape_a, shape_b)


@pytest.mark.parametrize("mutation", SHAPE_LEVEL_MUTATIONS.values(), ids=list(SHAPE_LEVEL_MUTATIONS))
def test_a_refused_shape_level_mutation_changes_nothing(closed_document, mutation):
    vis, page, shape_a, shape_b, _ = closed_document
    before = _page_xml(vis)

    with pytest.raises(vsdxkit.VisioFileNotOpen):
        mutation(vis, page, shape_a, shape_b)

    assert _page_xml(vis) == before


def test_data_property_mutation_after_close_raises(vsdx_copy):
    """Kept out of the table: only this fixture carries data properties."""
    vis = vsdxkit.VisioFile(vsdx_copy("test6_shape_properties.vsdx"))
    page = vis.pages[0]
    shape = page.find_shape_by_id("1")
    assert shape is not None
    prop = shape.data_properties["my_property_label"]
    before = ET.tostring(page.xml.getroot())
    vis.close_vsdx()

    mutations: list[Callable[[], object]] = [
        lambda: setattr(prop, "value", "changed"),
        lambda: prop.set_attribute("Value", "V", "changed"),
        lambda: prop.remove_attribute("Value", "V"),
    ]
    for mutation in mutations:
        with pytest.raises(vsdxkit.VisioFileNotOpen):
            mutation()
    assert ET.tostring(page.xml.getroot()) == before


CFF_FIXTURE = "fixtures/com_reference/s05_swimlanes_cfflow.vsdx"


def test_container_mutation_after_close_raises(vsdx_copy):
    """`Page.add_swimlane` is guarded; the Container behind it was not."""
    vis = vsdxkit.VisioFile(vsdx_copy(CFF_FIXTURE))
    page = vis.pages[0]
    container = page.get_container()
    assert container is not None
    lane = container.lanes[0]
    member = container.members(lane)[0]
    before = ET.tostring(page.xml.getroot())
    vis.close_vsdx()

    named: list[tuple[Callable[[], object], str]] = [
        (lambda: container.add_swimlane("new lane"), "Container.add_swimlane()"),
        (lambda: container.set_lane_label(lane, "renamed"), "Container.set_lane_label()"),
        (lambda: container.add_shape_to_lane(member, container.lanes[1]), "Container.add_shape_to_lane()"),
    ]
    for mutation, method in named:
        with pytest.raises(vsdxkit.VisioFileNotOpen) as excinfo:
            mutation()
        assert method in str(excinfo.value)
    assert ET.tostring(page.xml.getroot()) == before


def test_moving_a_shape_into_a_group_after_close_raises(vsdx_copy):
    """`append_shape` raised on one branch only: its guard came from
    `renumber_shape_ids`, which a shape already on the page never reaches."""
    vis = vsdxkit.VisioFile(vsdx_copy("test10_nested_shapes.vsdx"))
    page = vis.pages[0]
    group = next(s for s in page.child_shapes if s.shape_type == "Group")
    moving = next(s for s in page.child_shapes if s.shape_type != "Group")
    before = ET.tostring(page.xml.getroot())
    vis.close_vsdx()

    with pytest.raises(vsdxkit.VisioFileNotOpen):
        group.append_shape(moving)
    assert ET.tostring(page.xml.getroot()) == before


def test_a_refused_append_shape_creates_no_shapes_container(vsdx_copy):
    """`find_or_create_shapes_tag` ran ahead of the raise, so an empty group
    gained a `<Shapes>` element from a call that did not happen.

    The guard at the top of `append_shape` is enough to satisfy this; the
    statement reorder underneath it is belt and braces for any later reason
    the allocation might refuse.
    """
    vis = vsdxkit.VisioFile(vsdx_copy("test10_nested_shapes.vsdx"))
    page = vis.pages[0]
    group = next(s for s in page.child_shapes if s.shape_type == "Group")
    # an empty group carries no <Shapes> child until something is put into it
    shapes_tag = group.xml.find(f"{vsdxkit.namespace}Shapes")
    assert shapes_tag is not None
    group.xml.remove(shapes_tag)
    # new to the page, so append_shape would allocate ids for it
    arriving = vsdxkit.Shape(xml=ET.fromstring(ET.tostring(shapes_tag[0])), parent=page, page=page)
    vis.close_vsdx()

    with pytest.raises(vsdxkit.VisioFileNotOpen):
        group.append_shape(arriving)
    assert group.xml.find(f"{vsdxkit.namespace}Shapes") is None


def test_materialising_an_inherited_data_property_after_close_raises(vsdx_copy):
    """The tables never reach `make_local`: no shape in test4_connectors
    inherits anything, so the whole materialisation path went untested and
    unguarded."""
    vis = vsdxkit.VisioFile(vsdx_copy("test_master_multiple_child_shapes.vsdx"))
    shape = vis.pages[0].find_shape_by_id("3")
    assert shape is not None
    prop = shape.data_properties["title"]
    assert prop.inherited, "fixture property is no longer inherited"
    before = _page_xml(vis)
    vis.close_vsdx()

    with pytest.raises(vsdxkit.VisioFileNotOpen):
        prop.make_local()
    with pytest.raises(vsdxkit.VisioFileNotOpen):
        prop.value = "changed"
    assert _page_xml(vis) == before


def test_materialising_an_inherited_geometry_row_after_close_raises(vsdx_copy):
    vis = vsdxkit.VisioFile(vsdx_copy(CFF_FIXTURE))
    shape = vis.pages[0].find_shape_by_id("36")
    assert shape is not None
    row = _geometry(shape).rows["1"]
    assert row.inherited, "fixture row is no longer inherited"
    before = _page_xml(vis)
    vis.close_vsdx()

    with pytest.raises(vsdxkit.VisioFileNotOpen):
        row.make_local()
    with pytest.raises(vsdxkit.VisioFileNotOpen):
        row.x = 1.0
    with pytest.raises(vsdxkit.VisioFileNotOpen):
        row.create_row_xml("LineTo", "99")
    assert _page_xml(vis) == before


def test_building_a_geometry_cell_after_close_raises_before_it_appends(vsdx_copy):
    """The constructor wrote the element and then raised on the name."""
    vis = vsdxkit.VisioFile(vsdx_copy(CFF_FIXTURE))
    shape = vis.pages[0].find_shape_by_id("36")
    assert shape is not None
    geometry = _geometry(shape)
    row = geometry.rows["1"]
    before = _page_xml(vis)
    vis.close_vsdx()

    with pytest.raises(vsdxkit.VisioFileNotOpen):
        vsdxkit.GeometryCell(parent=row, xml=None, name="X", value=1.0)
    assert "X" not in row.cells or row.cells["X"].parent is not row
    assert _page_xml(vis) == before


GUARD_NAMES: dict[str, tuple[Mutation, str]] = {
    "renumber_shape_ids": (
        lambda vis, page, a, b: vis.renumber_shape_ids(a.xml, page),
        "VisioFile.renumber_shape_ids()",
    ),
    "increment_sub_shape_ids": (
        lambda vis, page, a, b: vis.increment_sub_shape_ids(a, page),
        "VisioFile.increment_sub_shape_ids()",
    ),
    "increment_shape_ids": (
        lambda vis, page, a, b: vis.increment_shape_ids(a.xml, page),
        "VisioFile.increment_shape_ids()",
    ),
    "connect_create": (
        lambda vis, page, a, b: vsdxkit.Connect.create(page=page, from_shape=a, to_shape=b),
        "Connect.create()",
    ),
    # the chokepoint guards describe the write instead, since the setter the
    # caller used cannot be named from there
    "style_attribute": (
        lambda vis, page, a, b: setattr(a, "line_style_id", 4),
        "writing shape attribute 'LineStyle'",
    ),
    "shape_cell": (
        lambda vis, page, a, b: setattr(a, "x", 1.0),
        "writing shape cell 'PinX'",
    ),
}


@pytest.mark.parametrize(("mutation", "named"), GUARD_NAMES.values(), ids=list(GUARD_NAMES))
def test_a_guard_names_the_operation_that_refused(closed_document, mutation, named):
    """One guard covering a family reported the wrong method to four callers."""
    vis, page, shape_a, shape_b, _ = closed_document
    with pytest.raises(vsdxkit.VisioFileNotOpen) as excinfo:
        mutation(vis, page, shape_a, shape_b)
    assert named in str(excinfo.value)


def test_append_shape_names_itself_when_it_refuses(vsdx_copy):
    vis = vsdxkit.VisioFile(vsdx_copy("test10_nested_shapes.vsdx"))
    page = vis.pages[0]
    group = next(s for s in page.child_shapes if s.shape_type == "Group")
    moving = next(s for s in page.child_shapes if s.shape_type != "Group")
    vis.close_vsdx()

    with pytest.raises(vsdxkit.VisioFileNotOpen) as excinfo:
        group.append_shape(moving)
    assert "Shape.append_shape()" in str(excinfo.value)


def test_add_swimlane_names_itself_when_it_refuses(vsdx_copy):
    vis = vsdxkit.VisioFile(vsdx_copy(CFF_FIXTURE))
    container = vis.pages[0].get_container()
    assert container is not None
    vis.close_vsdx()

    with pytest.raises(vsdxkit.VisioFileNotOpen) as excinfo:
        container.add_swimlane("new lane")
    assert "Container.add_swimlane()" in str(excinfo.value)


def test_retarget_names_itself_when_it_refuses(closed_document):
    _, page, shape_a, shape_b, _ = closed_document
    connector = next(s for s in page.child_shapes if s.begin_x is not None)

    with pytest.raises(vsdxkit.VisioFileNotOpen) as excinfo:
        vsdxkit.Connect.retarget(page, connector, from_shape=shape_a, to_shape=shape_b)
    assert "Connect.retarget()" in str(excinfo.value)
