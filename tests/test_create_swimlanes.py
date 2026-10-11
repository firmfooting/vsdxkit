"""Page.create_swimlanes: a cross-functional flowchart made on a page, as Visio's own is."""

import re
from pathlib import Path

import pytest
from helpers.package_validator import validate_package

from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError
from vsdxkit.shape_kind import ShapeKind
from vsdxkit.swimlanes import ROW_HEADING_TEXT, SwimlaneDiagram

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
        ([("A", 1.0)], 22.0),
        ([("a" * 23, 2.0)], 10.0),
    ],
)
def test_a_diagram_inside_the_sizes_visio_was_checked_on_is_made(bands, width):
    assert len(_make(bands, width).lanes) == len(bands)


@pytest.mark.parametrize(
    "bands, width, message",
    [
        ([(f"L{n}", 1.0) for n in range(6)], 10.0, "more than the 5"),
        ([("A", 1.0)], 4.9, "width of 4.9"),
        ([("A", 1.0)], 22.1, "width of 22.1"),
        ([("A", 0.4)], 10.0, "lane height of 0.4"),
        ([("A", 6.1)], 10.0, "lane height of 6.1"),
        ([("a" * 24, 2.0)], 10.0, "24 characters"),
        ([("a" * 12, 1.0)], 10.0, "12 characters"),
        ([("", 1.0)], 10.0, "must not be empty"),
    ],
)
def test_a_diagram_just_outside_those_sizes_is_refused_naming_the_limit(bands, width, message):
    with pytest.raises(InvalidOperationError, match=message):
        _make(bands, width)
