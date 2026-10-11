"""Page.create_swimlanes: a cross-functional flowchart made on a page, as Visio's own is."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from helpers.package_validator import validate_package

from vsdxkit import namespace
from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError
from vsdxkit.shape_kind import ShapeKind
from vsdxkit.swimlanes import LANE_PITCH_INCHES, MAX_LANES, ROW_HEADING_TEXT, SwimlaneDiagram

BANDS = [("Requester", 1.5), ("Reviewer", 2.0), ("Archive", 1.0)]


def _page(document: Document):
    page = document.pages[0]
    page.width, page.height = 12.0, 8.0
    return page


def _diagram() -> tuple[Document, SwimlaneDiagram]:
    document = Document.new()
    return document, _page(document).create_swimlanes(BANDS, left=0.5, top=7.0, width=10.0)


def _user(shape, row: str) -> str:
    return next(r for r in shape.xml.iter() if r.tag.endswith("}Row") and r.attrib.get("N") == row)[0].attrib["V"]


def test_the_lanes_stack_down_from_the_top_in_the_order_given_each_as_tall_as_asked():
    _, diagram = _diagram()
    wanted = [(0.5, 5.5, 10.5, 7.0), (0.5, 3.5, 10.5, 5.5), (0.5, 2.5, 10.5, 3.5)]
    for lane, bounds in zip(diagram.lanes, wanted, strict=True):
        assert lane.bounds == pytest.approx(bounds)


def test_each_lane_is_labelled_in_its_row_and_in_the_text_it_shows():
    _, diagram = _diagram()
    for lane, (label, _height) in zip(diagram.lanes, BANDS, strict=True):
        assert _user(lane, ROW_HEADING_TEXT) == label
        assert [part.text for part in lane.children if part.text] == [label]


def test_the_container_counts_the_lanes_and_each_lane_spells_the_count():
    _, diagram = _diagram()
    assert _user(diagram.container, "numLanes") == "3"
    assert all("/stg4=3," in _user(lane, "visCFFSettings") for lane in diagram.lanes)
    bigger = _page(Document.new()).create_swimlanes([(f"L{i}", 1.0) for i in range(5)], left=0.5, top=7.0, width=10.0)
    assert _user(bigger.container, "numLanes") == "5"
    assert all("/stg4=5," in _user(lane, "visCFFSettings") for lane in bigger.lanes)


def test_the_container_stands_a_title_bar_above_the_first_lane():
    _, diagram = _diagram()
    left, bottom, right, top = diagram.container.bounds
    assert (left, bottom, right) == pytest.approx((0.5, 2.5, 10.5))
    assert top == pytest.approx(7.0 + 0.5905511811023622)


def test_a_lanes_band_and_heading_follow_the_lanes_size():
    _, diagram = _diagram()
    for lane, (_label, height) in zip(diagram.lanes, BANDS, strict=True):
        band, heading = lane.children
        assert (band.width, band.height) == pytest.approx((10.0, height))
        assert heading.width == pytest.approx(height), (
            "the heading runs along the lane's side, so it is as long as the lane is tall"
        )
        assert heading.y == pytest.approx(height / 2)


def test_a_shape_centred_in_a_lane_belongs_to_it(tmp_path):
    document, diagram = _diagram()
    page = document.pages[0]
    shape = page.create_shape(ShapeKind.PROCESS, x=4.0, y=4.5, text="x")
    assert diagram.lane_for(shape).ID == diagram.lanes[1].ID


def test_no_reference_in_a_formula_names_a_shape_that_is_not_there(tmp_path):
    document, _ = _diagram()
    path = document.save(tmp_path / "lanes.vsdx")
    assert validate_package(str(path)) == ()


def test_the_diagram_reads_back_after_a_save(tmp_path):
    document, _ = _diagram()
    again = Document.open(document.save(tmp_path / "lanes.vsdx")).pages[0].require_swimlanes()
    assert again.lanes[0].bounds == pytest.approx((0.5, 5.5, 10.5, 7.0))
    assert [_user(lane, ROW_HEADING_TEXT) for lane in again.lanes] == ["Requester", "Reviewer", "Archive"]


@pytest.mark.parametrize(
    ("bands", "width", "message"),
    [([], 10.0, "at least one lane"), ([("A", 0.0)], 10.0, "positive"), ([("A", 1.0)], -1.0, "positive")],
)
def test_a_diagram_that_cannot_exist_is_refused(bands, width, message):
    with pytest.raises(InvalidOperationError, match=message):
        _page(Document.new()).create_swimlanes(bands, left=0.5, top=7.0, width=width)


def test_a_second_diagram_on_a_page_is_refused():
    _, _diagram_made = _diagram()
    page = _diagram_made.container.page
    with pytest.raises(InvalidOperationError, match="already has"):
        page.create_swimlanes(BANDS, left=0.5, top=7.0, width=10.0)


def test_a_page_whose_shape_ids_leave_no_room_is_refused():
    document = Document.new()
    page = _page(document)
    for _ in range(3):
        page.create_shape(ShapeKind.PROCESS, x=1.0, y=1.0)
    page.shapes.by_id("3").xml.attrib["ID"] = "999"
    with pytest.raises(InvalidOperationError, match="IDs too high"):
        page.create_swimlanes(BANDS, left=0.5, top=7.0, width=10.0)


def test_the_bundled_donor_carries_nothing_of_the_machine_that_saved_it():
    """Fails if the cross-functional flowchart donor keeps an author, a machine path or a rendering of its page."""
    import zipfile
    from pathlib import Path

    from vsdxkit import _media

    with zipfile.ZipFile(Path(_media.media_path(_media.CFF))) as archive:
        names = archive.namelist()
        assert "docProps/thumbnail.emf" not in names and "docProps/custom.xml" not in names
        for name in names:
            data = archive.read(name)
            # Visio's own stencil paths under Program Files stay: they name its install, not a person
            for marker in (b"\\Users\\", "\\Users\\".encode("utf-16-le")):
                assert marker not in data, f"{name} contains {marker!r}"
            assert not re.search(rb"[\w.+-]+@[\w-]+\.[\w.]+", data), f"{name} contains an address"
        assert "<dc:creator></dc:creator>" in archive.read("docProps/core.xml").decode("utf-8")


REFERENCE = Path(__file__).resolve().parent / "fixtures" / "com_reference" / "s05_swimlanes_cfflow.vsdx"
"""Visio's own capture of a three-lane cross-functional flowchart."""
DRAWN = ("CFF Container", "Swimlane List", "Swimlane", "Phase List", "Separator")
"""The top-level shapes the creation copies from that capture."""


def _outline(page) -> list[tuple[str, tuple[str, ...]]]:
    """Each drawn top-level shape's name and the names of its User rows, which is what Visio keys the ribbon tab on."""
    out = []
    for shape in page.children:
        name = re.sub(r"\.\d+$", "", shape.xml.attrib.get("NameU", ""))  # Visio numbers repeats: Swimlane.9
        if name in DRAWN:
            rows = [
                r.attrib["N"]
                for s in shape.xml.iter()
                if s.tag.endswith("}Section") and s.attrib.get("N") == "User"
                for r in s
                if r.tag.endswith("}Row")
            ]
            out.append((name, tuple(sorted(rows))))
    return sorted(out)


def test_a_created_diagram_has_the_shapes_and_user_rows_of_the_diagram_visio_drew():
    """The ribbon tab cannot be read back by a program; the shapes and rows it keys on can be compared with Visio's own."""
    _, diagram = _diagram()
    assert _outline(diagram.container.page) == _outline(Document.open(REFERENCE).pages[0])


def _vertices(shape) -> list[tuple[str, float]]:
    """The X and Y values of the shape's own geometry rows."""
    return [
        (c.attrib["N"], float(c.attrib["V"]))
        for section in shape.xml.iterfind('{*}Section[@N="Geometry"]')
        for c in section.iter()
        if c.tag.endswith("}Cell") and c.attrib.get("N") in ("X", "Y") and c.attrib.get("V")
    ]


def _outline_fits(shape) -> bool:
    """Whether no vertex of the shape's outline lies outside its own width and height."""
    return all(value <= (shape.width if axis == "X" else shape.height) + 1e-6 for axis, value in _vertices(shape))


def test_a_cell_a_sub_shape_only_inherited_is_written_as_inherited_not_as_the_masters_formula():
    """A master's formula names the master's shapes by Sheet.N; copied onto a page it would name whatever has that ID there."""
    _, diagram = _diagram()
    for lane in diagram.lanes:
        band = next(iter(lane.children))
        for name in ("PinY", "Height"):
            cell = next((c for c in band.xml if c.tag.endswith("}Cell") and c.attrib["N"] == name), None)
            assert cell is None or cell.attrib.get("F") == "Inh", f"{name} of a lane band is {cell.attrib}"


def test_the_outline_of_every_sub_shape_fits_the_size_it_was_given():
    _, diagram = _diagram()
    shapes = [part for top in diagram.container.page.children for part in top.descendants]
    assert shapes and all(_outline_fits(shape) for shape in shapes)


def test_the_outline_of_a_top_level_shape_that_has_no_sub_shapes_fits_its_size_too():
    _, diagram = _diagram()
    bare = [top for top in diagram.container.page.children if not top.children and _vertices(top)]
    assert bare and all(_outline_fits(shape) for shape in bare)


def test_a_vertex_a_sub_shape_inherits_is_written_with_the_number_it_has_at_the_new_size():
    """Visio draws an inherited vertex from the master's cached number on open, so the file carries the right one."""
    _, diagram = _diagram()
    for lane, (_label, height) in zip(diagram.lanes, BANDS, strict=True):
        band = next(iter(lane.children))
        ys = [v for axis, v in _vertices(band) if axis == "Y"]
        assert ys and max(ys) == pytest.approx(height)


def test_a_sub_shape_with_no_geometry_of_its_own_gets_the_vertices_it_inherits_at_the_new_size():
    _, diagram = _diagram()
    for lane, (_label, height) in zip(diagram.lanes, BANDS, strict=True):
        heading = list(lane.children)[1]
        xs = [v for axis, v in _vertices(heading) if axis == "X"]
        assert xs and max(xs) == pytest.approx(height)


def test_a_headings_text_block_is_as_wide_as_its_heading_is_after_the_resize():
    """The text block's cells follow the heading's width through the master, so a stale one centres the label for the old size."""
    _, diagram = _diagram()
    for lane, (_label, height) in zip(diagram.lanes, BANDS, strict=True):
        heading = list(lane.children)[1]
        assert float(heading.cell_value("TxtWidth")) == pytest.approx(height)
        assert float(heading.cell_value("TxtPinX")) == pytest.approx(height / 2)


RECORDING = Path(__file__).resolve().parent / "fixtures" / "visio_observations" / "swimlanes.json"
"""What Visio computed for the ``swimlanes`` case, recorded by ``visio_verify.py record``."""


def test_the_title_bars_pins_are_the_numbers_visio_computed_for_the_case():
    """The cached PinY of the container and of the title sub-shapes hang from the top edge, and Visio's recalculation agreed."""
    import importlib.util
    import json

    spec = importlib.util.spec_from_file_location(
        "swimlanes_case", Path(__file__).parent / "fixtures" / "diagrams" / "swimlanes.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    page = module.build().pages[0]
    recorded = {
        s["id"]: {c["name"]: c["result"] for c in s["cells"]}
        for s in json.loads(RECORDING.read_text("utf-8"))["pages"][0]["shapes"]
    }
    for shape_id in (1, 3, 6, 8):
        assert page.shapes.by_id(str(shape_id)).y == pytest.approx(recorded[shape_id]["PinY"]), shape_id


def _make(bands, width=10.0):
    return _page(Document.new()).create_swimlanes(bands, left=0.5, top=7.0, width=width)


@pytest.mark.parametrize(
    "bands, width",
    [
        ([(f"L{n}", 1.0) for n in range(5)], 10.0),
        ([("W", 0.5), ("W" * 30, 6.0)], 5.0),
        ([("A", 1.0)], 60.0),
        ([("a" * 22, 2.0)], 10.0),
        ([("a" * 11, 1.0)], 10.0),
    ],
)
def test_a_diagram_inside_the_sizes_visio_was_checked_on_is_made(bands, width):
    assert len(_make(bands, width).lanes) == len(bands)


@pytest.mark.parametrize(
    "bands, width, message",
    [
        ([(f"L{n}", 1.0) for n in range(6)], 10.0, "more than the 5"),
        ([("A", 1.0)], 4.9, "width of 4.9"),
        ([("A", 1.0)], 60.1, "width of 60.1"),
        ([("A", 0.4)], 10.0, "lane height of 0.4"),
        ([("A", 6.1)], 10.0, "lane height of 6.1"),
        ([("a" * 23, 2.0)], 10.0, "23 characters"),
        ([("a" * 12, 1.0)], 10.0, "12 characters"),
        ([("", 1.0)], 10.0, "must not be empty"),
    ],
)
def test_a_diagram_just_outside_those_sizes_is_refused_naming_the_limit(bands, width, message):
    with pytest.raises(InvalidOperationError, match=message):
        _make(bands, width)


@pytest.mark.parametrize("height", [0.5, 1.5, 6.0])
def test_a_lane_cannot_be_added_to_a_diagram_whose_lanes_are_not_one_pitch_tall(height):
    diagram = _make([("Top", height), ("Next", height)])
    page = diagram.container.page
    before = ET.tostring(page.xml.getroot())
    with pytest.raises(InvalidOperationError, match="every lane to be that tall"):
        diagram.add_lane("New")
    assert ET.tostring(page.xml.getroot()) == before


def test_a_lane_is_added_as_before_to_a_diagram_whose_lanes_are_one_pitch_tall():
    diagram = _make([("Top", LANE_PITCH_INCHES), ("Next", LANE_PITCH_INCHES)])
    diagram.add_lane("New")
    assert len(diagram.lanes) == 3
    assert diagram.lanes[0].bounds[3] == pytest.approx(7.0 + LANE_PITCH_INCHES)


NAN, INF = float("nan"), float("inf")


@pytest.mark.parametrize(
    "bands, left, top, width",
    [
        ([("A", 1.0)], NAN, 7.0, 10.0),
        ([("A", 1.0)], INF, 7.0, 10.0),
        ([("A", 1.0)], 0.5, NAN, 10.0),
        ([("A", 1.0)], 0.5, -INF, 10.0),
        ([("A", 1.0)], 0.5, 7.0, NAN),
        ([("A", 1.0)], 0.5, 7.0, INF),
        ([("A", NAN)], 0.5, 7.0, 10.0),
        ([("A", INF)], 0.5, 7.0, 10.0),
    ],
)
def test_a_diagram_with_a_non_finite_number_is_refused_and_the_page_is_left_alone(bands, left, top, width):
    page = _page(Document.new())
    before = ET.tostring(page.xml.getroot())
    with pytest.raises(InvalidOperationError):
        page.create_swimlanes(bands, left=left, top=top, width=width)
    assert ET.tostring(page.xml.getroot()) == before


def test_a_page_holding_a_deleted_diagrams_lanes_is_refused_and_left_alone():
    """Deleting the container leaves its flat sibling lanes behind, so the page has none and yet holds CFF shapes."""
    document, diagram = _diagram()
    page = document.pages[0]
    diagram.container.delete()
    before = ET.tostring(page.xml.getroot())
    with pytest.raises(InvalidOperationError, match="without a container"):
        page.create_swimlanes(BANDS, left=0.5, top=7.0, width=10.0)
    assert ET.tostring(page.xml.getroot()) == before


@pytest.mark.parametrize(
    "bands",
    [[(f"L{n}", 1.0) for n in range(6)], [("A", 0.4)], [("", 1.0)], [("a" * 12, 1.0)]],
)
def test_a_diagram_refused_for_its_size_leaves_the_page_byte_identical(bands):
    page = _page(Document.new())
    before = ET.tostring(page.xml.getroot())
    with pytest.raises(InvalidOperationError):
        page.create_swimlanes(bands, left=0.5, top=7.0, width=10.0)
    assert ET.tostring(page.xml.getroot()) == before


def _separator_style_names(document: Document) -> set[str | None]:
    """The names of the styles the imported Separator master's sub-shapes take, as this document resolves their IDs."""
    master = next(m for m in document._masters.pages if m.name == "Separator")
    names = {s.attrib["ID"]: s.attrib.get("NameU") for s in document._style_sheets()}
    return {
        names.get(e.attrib["LineStyle"]) for e in master.xml.getroot().iter(f"{namespace}Shape") if "LineStyle" in e.attrib
    }


def test_a_masters_styles_are_imported_with_it_where_the_destination_means_another_style_by_the_id():
    """The blank template's style 7 is Connector; the bundled flowchart's 7 is Flow Normal, which its Separator takes."""
    _, diagram = _diagram()
    document = diagram.container.page._document
    assert "Flow Normal" in _separator_style_names(document)


def test_a_masters_styles_are_imported_with_it_where_the_destination_lacks_the_id():
    document = Document.new()
    sheets = document._style_sheets()
    for sheet in list(sheets):
        if sheet.attrib.get("ID") == "7":
            sheets.remove(sheet)
    _page(document).create_swimlanes(BANDS, left=0.5, top=7.0, width=10.0)
    assert "Flow Normal" in _separator_style_names(document)


def _unique_ids(page) -> list[str]:
    """The UniqueID of every shape on the page, sub-shapes included."""
    return [e.attrib["UniqueID"] for e in page.xml.getroot().iter(f"{namespace}Shape") if "UniqueID" in e.attrib]


def test_every_shape_of_a_created_diagram_has_a_unique_id_of_its_own():
    _, diagram = _diagram()
    ids = _unique_ids(diagram.container.page)
    assert len(ids) > 3 * len(BANDS) and len(set(ids)) == len(ids)
    assert all(re.fullmatch(r"\{[0-9A-F]{8}(-[0-9A-F]{4}){3}-[0-9A-F]{12}\}", i) for i in ids)


def test_the_shapes_of_a_created_diagram_share_no_unique_id_with_the_donor():
    document, diagram = _diagram()
    donor = _unique_ids(document._cff_sources().container.page)
    assert donor and not set(donor) & set(_unique_ids(diagram.container.page))


def test_diagrams_on_two_pages_of_a_document_share_no_unique_id():
    document = Document.new()
    first = _page(document)
    second = document.pages.create("Second")
    second.width, second.height = 12.0, 8.0
    first.create_swimlanes(BANDS, left=0.5, top=7.0, width=10.0)
    second.create_swimlanes(BANDS, left=0.5, top=7.0, width=10.0)
    ids = _unique_ids(first) + _unique_ids(second)
    assert len(set(ids)) == len(ids)


def test_two_builds_of_a_created_diagram_save_the_same_bytes(tmp_path):
    first = _diagram()[0].save(tmp_path / "a.vsdx", deterministic=True)
    second = _diagram()[0].save(tmp_path / "b.vsdx", deterministic=True)
    assert first.read_bytes() == second.read_bytes()


def _relationship_lanes(diagram) -> list[str]:
    """The IDs the Swimlane List's Relationships formula names as its lanes."""
    cell = next(c for c in diagram._swimlane_list().xml if c.tag.endswith("}Cell") and c.attrib["N"] == "Relationships")
    return (
        re.findall(r"DEPENDSON\(2((?:,Sheet\.\d+!SheetRef\(\))*)\)", cell.attrib["F"])[0]
        .replace("!SheetRef()", "")
        .split(",Sheet.")[1:]
    )


def _check_metadata(diagram, count):
    assert len(diagram.lanes) == count
    assert _user(diagram.container, "numLanes") == str(count)
    assert all(f"/stg4={count}," in _user(lane, "visCFFSettings") for lane in diagram.lanes)
    assert _relationship_lanes(diagram) == [lane.ID for lane in diagram.lanes], "the lanes are listed top to bottom"


def test_a_lane_added_to_a_created_diagram_is_counted_in_the_metadata_the_machinery_keeps():
    diagram = _make([("Top", LANE_PITCH_INCHES), ("Next", LANE_PITCH_INCHES)])
    diagram.add_lane("New")
    _check_metadata(diagram, 3)
    ids = _unique_ids(diagram.container.page)
    assert len(set(ids)) == len(ids), "the added lane has a UniqueID of its own"


def test_a_lane_added_to_a_diagram_visio_drew_is_counted_too():
    """Before this was written, add_lane left numLanes, /stg4 and Relationships at the three lanes Visio drew."""
    diagram = Document.open(REFERENCE).pages[0].require_swimlanes()
    diagram.add_lane("New")
    assert _user(diagram.container, "numLanes") == "4"
    assert all("/stg4=4," in _user(lane, "visCFFSettings") for lane in diagram.lanes)
    assert _relationship_lanes(diagram) == [lane.ID for lane in diagram.lanes], "the lanes are listed top to bottom"


def test_the_sub_shapes_of_the_grown_container_and_list_follow_them_after_add_lane():
    diagram = _make([("Top", LANE_PITCH_INCHES), ("Next", LANE_PITCH_INCHES)])
    diagram.add_lane("New")
    for grown in (diagram.container, diagram._swimlane_list()):
        tops = [v for shape in (grown, *grown.descendants) for axis, v in _vertices(shape) if axis == "Y"]
        assert max(tops) == pytest.approx(grown.height)
    assert next(iter(diagram.container.children)).height == pytest.approx(diagram.container.height)


@pytest.mark.parametrize("drawn_by_visio", [False, True])
def test_the_list_and_container_keep_their_bottom_edge_and_gain_one_pitch_at_the_top_after_add_lane(drawn_by_visio):
    """A list pinned at its top edge and a container pinned at its middle both grow upwards, so the pin moves with the edge."""
    if drawn_by_visio:
        diagram = Document.open(REFERENCE).pages[0].require_swimlanes()
    else:
        diagram = _make([("Top", LANE_PITCH_INCHES), ("Next", LANE_PITCH_INCHES)])
    grown = (diagram._swimlane_list(), diagram.container)
    before = [shape.bounds for shape in grown]
    diagram.add_lane("New")
    for shape, (left, bottom, right, top) in zip(grown, before, strict=True):
        assert shape.bounds == pytest.approx((left, bottom, right, top + LANE_PITCH_INCHES))


def test_the_phase_list_and_separator_gain_one_pitch_at_the_top_after_add_lane_as_the_lanes_do():
    diagram = _make([("Top", LANE_PITCH_INCHES), ("Next", LANE_PITCH_INCHES)])
    phases = diagram._phase_shapes()
    assert len(phases) == 2
    before = [shape.bounds for shape in phases]
    diagram.add_lane()
    for shape, (left, bottom, right, top) in zip(phases, before, strict=True):
        assert shape.bounds == pytest.approx((left, bottom, right, top + LANE_PITCH_INCHES))


def test_diagrams_on_two_pages_with_one_name_share_no_unique_id():
    document = Document.new()
    first = _page(document)
    second = document.pages.create("Other")
    second.width, second.height = 12.0, 8.0
    second.name = first.name
    assert first.name == second.name
    first.create_swimlanes([("A", 1.0)], left=0.5, top=7.0, width=10.0)
    second.create_swimlanes([("A", 1.0)], left=0.5, top=7.0, width=10.0)
    ids = _unique_ids(first) + _unique_ids(second)
    assert len(set(ids)) == len(ids)


def test_a_diagrams_unique_ids_survive_a_save_and_reopen_and_a_later_diagram(tmp_path):
    document, diagram = _diagram()
    before = _unique_ids(diagram.container.page)
    reopened = Document.open(document.save(tmp_path / "a.vsdx"))
    assert _unique_ids(reopened.pages[0]) == before
    other = reopened.pages.create("Later")
    other.width, other.height = 12.0, 8.0
    other.create_swimlanes(BANDS, left=0.5, top=7.0, width=10.0)
    assert _unique_ids(reopened.pages[0]) == before
    ids = _unique_ids(reopened.pages[0]) + _unique_ids(other)
    assert len(set(ids)) == len(ids)


def test_a_unique_id_a_shape_already_holds_is_never_given_again_and_that_shape_keeps_it():
    """A shape copied from another document keeps its UniqueID, which can equal one derived here for the same page ID."""
    import uuid

    from vsdxkit.swimlanes import _UNIQUE_ID_NAMESPACE

    document = Document.new()
    page = _page(document)
    held = page.create_shape(ShapeKind.PROCESS, x=1.0, y=1.0)
    wanted = "{" + str(uuid.uuid5(_UNIQUE_ID_NAMESPACE, f"{page._page_id}/{int(held.ID) + 1}")).upper() + "}"
    held.xml.attrib["UniqueID"] = wanted
    diagram = page.create_swimlanes(BANDS, left=0.5, top=7.0, width=10.0)
    ids = _unique_ids(page)
    assert len(set(ids)) == len(ids)
    assert held.xml.attrib["UniqueID"] == wanted
    assert diagram.container.xml.attrib["UniqueID"] != wanted


def test_a_unique_id_held_on_another_page_is_not_given_again():
    document = Document.new()
    first = _page(document)
    other = document.pages.create("Other")
    shape = other.create_shape(ShapeKind.PROCESS, x=1.0, y=1.0)
    import uuid

    from vsdxkit.swimlanes import _UNIQUE_ID_NAMESPACE

    wanted = "{" + str(uuid.uuid5(_UNIQUE_ID_NAMESPACE, f"{first._page_id}/{1}")).upper() + "}"
    shape.xml.attrib["UniqueID"] = wanted
    first.create_swimlanes(BANDS, left=0.5, top=7.0, width=10.0)
    assert wanted not in _unique_ids(first)


def _derived(page, shape_id) -> str:
    """The UniqueID the code first derives for the shape with this ID on this page."""
    import uuid

    from vsdxkit.swimlanes import _UNIQUE_ID_NAMESPACE

    return "{" + str(uuid.uuid5(_UNIQUE_ID_NAMESPACE, f"{page._page_id}/{shape_id}")).upper() + "}"


def test_two_equivalent_builds_that_avoided_a_held_unique_id_save_the_same_bytes(tmp_path):
    def build(name):
        document = Document.new()
        page = _page(document)
        held = page.create_shape(ShapeKind.PROCESS, x=1.0, y=1.0)
        held.xml.attrib["UniqueID"] = _derived(page, int(held.ID) + 1)  # the container's, which is next
        diagram = page.create_swimlanes([("A", LANE_PITCH_INCHES)], left=0.5, top=7.0, width=10.0)
        assert diagram.container.xml.attrib["UniqueID"] != held.xml.attrib["UniqueID"]
        diagram.add_lane()
        return document.save(tmp_path / name, deterministic=True).read_bytes()

    assert build("a.vsdx") == build("b.vsdx")


def test_the_salt_is_used_for_a_lane_added_by_add_lane_too():
    document = Document.new()
    page = _page(document)
    diagram = page.create_swimlanes([("A", LANE_PITCH_INCHES)], left=0.5, top=7.0, width=10.0)
    next_id = max(int(s.ID) for s in page.shapes) + 1
    other = document.pages.create("Other")
    held = other.create_shape(ShapeKind.PROCESS, x=1.0, y=1.0)
    held.xml.attrib["UniqueID"] = _derived(page, next_id).lower()  # lower case: still the same ID
    new_lane = diagram.add_lane()
    assert int(new_lane.ID) == next_id
    assert new_lane.xml.attrib["UniqueID"].upper() != held.xml.attrib["UniqueID"].upper()
    ids = [i.upper() for i in _unique_ids(page) + _unique_ids(other)]
    assert len(set(ids)) == len(ids)


def test_the_lanes_are_listed_top_to_bottom_after_several_add_lane_calls():
    diagram = _make([("A", LANE_PITCH_INCHES), ("B", LANE_PITCH_INCHES)])
    for _ in range(3):
        diagram.add_lane()
        assert _relationship_lanes(diagram) == [lane.ID for lane in diagram.lanes]


def test_add_lane_refuses_a_lane_beyond_the_verified_count_and_leaves_the_page_as_it_was():
    document = Document.new()
    page = _page(document)
    pitch = LANE_PITCH_INCHES
    diagram = page.create_swimlanes([(f"L{i}", pitch) for i in range(MAX_LANES)], left=0.5, top=7.0, width=10.0)
    shapes = len(page.shapes)
    with pytest.raises(InvalidOperationError, match=rf"{MAX_LANES + 1} lanes is more than the {MAX_LANES}"):
        diagram.add_lane("Extra")
    assert len(page.shapes) == shapes
    assert len(diagram.lanes) == MAX_LANES


def test_add_lane_resizes_only_the_diagrams_own_phase_list_and_separator():
    diagram = _make([("Top", LANE_PITCH_INCHES), ("Next", LANE_PITCH_INCHES)])
    page = diagram.container.page
    own = {s.shape_name: s for s in page.children if s.shape_name in ("Phase List", "Separator")}
    decoys = []
    for name, shape in own.items():
        decoy = shape.copy(page)
        decoy.name = name
        for cell in decoy.xml.findall(f"{namespace}Cell"):
            if cell.attrib.get("N") == "Relationships":
                cell.attrib["F"] = "SUM(DEPENDSON(4))"
        decoys.append(decoy)
    before = {s.ID: s.height for s in (*decoys, *own.values())}
    diagram.add_lane("New")
    assert {s.ID: s.height for s in decoys} == {s.ID: before[s.ID] for s in decoys}
    assert all(s.height > before[s.ID] for s in own.values())


def test_a_main_child_grows_with_its_container_when_the_container_is_as_wide_as_it_is_tall():
    """#488: at 5.315 by 5.315 a cached height equal to the width was renewed as the width."""
    page = _page(Document.new())
    diagram = page.create_swimlanes(
        [("A", LANE_PITCH_INCHES), ("B", LANE_PITCH_INCHES)], left=0.5, top=7.0, width=5.314960629921242
    )
    for _ in range(3):
        diagram.add_lane()
        child = next(iter(diagram.container.children))
        assert child.height == pytest.approx(diagram.container.height)
