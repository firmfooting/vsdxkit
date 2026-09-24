import json
import os
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile

import pytest

from vsdxkit.document import Document
from vsdxkit.glue import Glue, Routing


def _any_shape_containing(shapes, text: str):
    """The first shape whose text contains `text`, as the retired substring finder matched."""
    return next((shape for shape in shapes if text in shape.text), None)


def get_copy(basedir: str, filename: str, target_dir: str) -> str:
    src = os.path.join(basedir, filename)
    dst = os.path.join(target_dir, filename)
    shutil.copy(src, dst)
    return dst


def test_connect_shapes_dynamic_glue_formulas(basedir):
    vis = Document.open(os.path.join(basedir, "test8_simple_connector.vsdx"))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    assert a is not None and b is not None
    connector = page.connect(a, b)
    assert connector is not None

    beg_trigger = connector.cells.get("BegTrigger")
    end_trigger = connector.cells.get("EndTrigger")
    assert beg_trigger is not None and end_trigger is not None
    assert beg_trigger.formula == f"_XFTRIGGER(Sheet{a.ID}!EventXFMod)"
    assert end_trigger.formula == f"_XFTRIGGER(Sheet{b.ID}!EventXFMod)"

    walkglue_begin = "_WALKGLUE(BegTrigger,EndTrigger,WalkPreference)"
    walkglue_end = "_WALKGLUE(EndTrigger,BegTrigger,WalkPreference)"
    assert connector.cells["BeginX"].formula == walkglue_begin
    assert connector.cells["BeginY"].formula == walkglue_begin
    assert connector.cells["EndX"].formula == walkglue_end
    assert connector.cells["EndY"].formula == walkglue_end
    assert connector.cells["GlueType"].value == "2"
    assert connector.cells["ShapeRouteStyle"].value == "0"


def test_connect_shapes_glue_records(basedir):
    vis = Document.open(os.path.join(basedir, "test8_simple_connector.vsdx"))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    connector = page.connect(a, b)
    connects = {c.from_rel: c for c in page.connects if c.from_id == str(connector.ID)}
    assert "BeginX" in connects and "EndX" in connects
    begin = connects["BeginX"]
    assert begin.to_id == str(a.ID)
    assert begin.to_rel == "PinX"
    end = connects["EndX"]
    assert end.to_id == str(b.ID)
    assert end.to_rel == "PinX"


def test_connect_shapes_route_variants(basedir):
    vis = Document.open(os.path.join(basedir, "test8_simple_connector.vsdx"))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    straight = page.connect(a, b, routing=Routing.STRAIGHT)
    assert straight.cells["ShapeRouteStyle"].value == "16"
    right = page.connect(a, b, routing=Routing.RIGHT_ANGLE)
    assert right.cells["ShapeRouteStyle"].value == "1"
    curved = page.connect(a, b, routing=Routing.CURVED)
    assert curved.cells["ShapeRouteStyle"].value == "17"
    assert curved.cells["ConLineRouteExt"].value == "2"
    plain = page.connect(a, b)
    assert plain.cells["ShapeRouteStyle"].value == "0"


def test_connect_point_glue_requires_connection_points(basedir):
    vis = Document.open(os.path.join(basedir, "test8_simple_connector.vsdx"))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    with pytest.raises(ValueError):
        page.connect(a, b, glue=Glue.POINT)


def test_connect_shapes_combines_point_glue_and_curved_routing(basedir):
    fixture = os.path.join(basedir, "fixtures", "com_reference", "s05_swimlanes_cfflow.vsdx")
    vis = Document.open(fixture)
    page = vis.pages[0]
    source = page.shapes.by_id("90")
    target = page.shapes.by_id("97")
    assert source is not None and target is not None

    connector = page.connect(source, target, glue=Glue.POINT, routing=Routing.CURVED, to_point=2)

    source_point = f"PAR(PNT(Sheet{source.ID}!Connections.X1,Sheet{source.ID}!Connections.Y1))"
    target_point = f"PAR(PNT(Sheet{target.ID}!Connections.X3,Sheet{target.ID}!Connections.Y3))"
    assert connector.cells["BeginX"].formula == source_point
    assert connector.cells["EndX"].formula == target_point
    assert connector.cells["ShapeRouteStyle"].value == "17"
    assert connector.cells["ConLineRouteExt"].value == "2"
    records = {connect.from_rel: connect for connect in page.connects if connect.from_id == str(connector.ID)}
    assert records["BeginX"].to_rel == "Connections.X1"
    assert records["EndX"].to_rel == "Connections.X3"


def test_a_routing_string_fails_before_mutating_page(basedir):
    """Fails if a 0.x route string is taken for a `Routing`, or refused only after the connector is made."""
    vis = Document.open(os.path.join(basedir, "test8_simple_connector.vsdx"))
    page = vis.pages[0]
    source = page.shapes.by_text("Shape A")
    target = page.shapes.by_text("Shape B")
    assert source is not None and target is not None
    before_shapes = len(page.all_shapes)
    before_connects = len(page.connects)

    with pytest.raises(TypeError, match="routing must be one of"):
        page.connect(source, target, routing="curved")  # type: ignore[arg-type]

    assert len(page.all_shapes) == before_shapes
    assert len(page.connects) == before_connects


def test_connector_round_trip_and_zip_validity(basedir):
    with tempfile.TemporaryDirectory() as tmp:
        src = get_copy(basedir, "test8_simple_connector.vsdx", tmp)
        vis = Document.open(src)
        page = vis.pages[0]
        a = page.shapes.by_text("Shape A")
        b = page.shapes.by_text("Shape B")
        connector = page.connect(a, b, routing=Routing.CURVED)
        conn_id = connector.ID
        vis.save(src)
        with zipfile.ZipFile(src) as z:
            assert z.testzip() is None
        vis2 = Document.open(src)
        page = vis2.pages[0]
        reopened = page.shapes.by_id(str(conn_id))
        assert reopened is not None
        assert reopened.cells["BegTrigger"].formula == f"_XFTRIGGER(Sheet{a.ID}!EventXFMod)"
        assert reopened.cells["EndTrigger"].formula == f"_XFTRIGGER(Sheet{b.ID}!EventXFMod)"
        assert reopened.cells["ShapeRouteStyle"].value == "17"


def test_delete_shape_cascades_connectors(basedir):
    with tempfile.TemporaryDirectory() as tmp:
        src = get_copy(basedir, "test4_connectors.vsdx", tmp)
        vis = Document.open(src)
        page = vis.pages[0]
        before_connects = len(list(page.connects))
        assert before_connects > 0
        doomed = page.shapes.by_id("2")
        assert doomed is not None
        page.delete_shape(doomed)
        vis.save(src)
        with zipfile.ZipFile(src) as z:
            assert z.testzip() is None
        vis2 = Document.open(src)
        page = vis2.pages[0]
        # shape 2 and both connectors attached to it (6 and 7) are gone
        assert page.shapes.by_id("2") is None
        remaining_ids = {str(s.ID) for s in page.all_shapes}
        assert "6" not in remaining_ids
        assert "7" not in remaining_ids
        # no Connect records may reference removed shapes
        for c in page.connects:
            assert c.from_id not in ("2", "6", "7")
            assert c.to_id not in ("2", "6", "7")


def test_master_import_on_own_masters_document(tmp_path, basedir):
    """Connector creation on a doc with own masters imports the master."""
    src = get_copy(basedir, "test3_house.vsdx", str(tmp_path))
    vis = Document.open(src)
    page = vis.pages[0]
    a = page.shapes.by_property("Network Name", "House01")
    b = page.shapes.by_property("Network Name", "Box01")
    assert a is not None and b is not None
    connector = page.connect(a, b)
    assert connector is not None
    # the connector now references a master that exists in THIS document
    assert vis.get_master_page_by_id(connector.master_page_ID) is not None
    vis.save(src)
    with zipfile.ZipFile(src) as z:
        assert z.testzip() is None
        rels = z.read("visio/_rels/document.xml.rels").decode()
        # exactly one masters relationship, imported master part present
        assert rels.count("relationships/masters") == 1
        master_parts = [n for n in z.namelist() if n.startswith("visio/masters/master")]
        assert len(master_parts) >= 2  # original + imported
    vis2 = Document.open(src)
    page = vis2.pages[0]
    assert _any_shape_containing(page.shapes, "") is not None  # reopen is valid
    connectors = [s for s in page.all_shapes if "BeginX" in s.cells]
    assert len(connectors) == 1


def test_master_import_is_idempotent(tmp_path, basedir):
    """Three connectors on an own-masters doc import the connector master once."""
    src = get_copy(basedir, "test3_house.vsdx", str(tmp_path))
    vis = Document.open(src)
    page = vis.pages[0]
    a = page.shapes.by_property("Network Name", "House01")
    b = page.shapes.by_property("Network Name", "Box01")
    c = page.shapes.by_id("1")
    assert a is not None and b is not None and c is not None
    connectors = [page.connect(a, b), page.connect(b, c), page.connect(c, a)]
    # all three connectors resolve to the one imported master
    master_ids = {connector.master_page_ID for connector in connectors}
    assert None not in master_ids, "connector was created without a master reference"
    assert len(master_ids) == 1
    vis.save(src)
    with zipfile.ZipFile(src) as z:
        rels = z.read("visio/_rels/document.xml.rels").decode()
        assert rels.count("relationships/masters") == 1
        content_types = z.read("[Content_Types].xml").decode()
        assert content_types.count("visio/masters/masters.xml") == 1

        masters_root = ET.fromstring(z.read("visio/masters/masters.xml"))
        connector_masters = [m for m in masters_root if m.attrib.get("NameU") == "Dynamic connector"]
        assert len(connector_masters) == 1
        # one master part per declared master, so a re-import would leave an orphan
        master_parts = [n for n in z.namelist() if re.fullmatch(r"visio/masters/master\d+\.xml", n)]
        assert len(master_parts) == len(masters_root)


COM_REFERENCE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "fixtures", "com_reference")
S05 = os.path.join(COM_REFERENCE, "s05_swimlanes_cfflow.vsdx")
# every cell the manifest records that glue or routing sets, bar the two triggers
GLUE_CELLS = ("BeginX", "BeginY", "EndX", "EndY", "GlueType", "ObjType", "ShapeRouteStyle", "ConLineRouteExt", "ConFixedCode")
VISIO_ROLES = {"1": "A", "2": "B"}


def _manifest_connectors(scenario: str) -> list[dict[str, str | None]]:
    with open(os.path.join(COM_REFERENCE, "manifest.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)
    (entry,) = [entry for entry in manifest["scenarios"] if entry["scenario"] == scenario]
    return [shape["cells"] for shape in entry["shapes"] if shape["one_d"]]


def _as_visio_records(cell) -> str | None:
    """A cell as the manifest records it: its formula, or its value where it has none."""
    return None if cell is None else cell.formula or cell.value


def _by_role(formula: str, roles: dict[str, str]) -> str:
    """The formula with each sheet reference named by the role of the shape it names.

    The engine writes `Sheet90!` where Visio writes `Sheet.1!`. The missing dot
    is #400, so this reads both. A reference to a shape outside
    `roles` keeps its id, so a stray one still shows.
    """
    return re.sub(r"Sheet\.?(\d+)!", lambda match: f"{roles.get(match.group(1), 'Sheet.' + match.group(1))}!", formula)


@pytest.mark.parametrize(
    ("routing", "scenario", "style"),
    [
        (Routing.DEFAULT, "s01_autoconnect_right", "0"),
        (Routing.RIGHT_ANGLE, "s03_route_variants", "1"),
        (Routing.STRAIGHT, "s03_route_variants", "16"),
        (Routing.CURVED, "s03_route_variants", "17"),
    ],
)
def test_each_routing_writes_what_visio_writes(routing, scenario, style):
    (expected,) = [cells for cells in _manifest_connectors(scenario) if cells["ShapeRouteStyle"] == style]
    vis = Document.open(S05)
    page = vis.pages[0]
    source, target = page.shapes.by_id("90"), page.shapes.by_id("97")
    connector = page.connect(source, target, routing=routing)
    written = {name: _as_visio_records(connector.cells.get(name)) for name in GLUE_CELLS}
    roles = {source.ID: "A", target.ID: "B"}
    triggers = {name: _by_role(connector.cells[name].formula, roles) for name in ("BegTrigger", "EndTrigger")}
    assert written == {name: expected[name] for name in GLUE_CELLS}
    assert triggers == {name: _by_role(str(expected[name]), VISIO_ROLES) for name in ("BegTrigger", "EndTrigger")}


def _s07_connector() -> tuple[dict[str, str], list[tuple[str, ...]]]:
    """The point-glued connector of s07 and its records, as Visio wrote them."""
    vis = Document.open(os.path.join(COM_REFERENCE, "s07_point_glue_masters.vsdx"))
    page = vis.pages[0]
    (connector,) = [shape for shape in page.shapes if "BeginX" in shape.cells]
    names = ("BegTrigger", "EndTrigger", "BeginX", "BeginY", "EndX", "EndY")
    cells = {name: _by_role(connector.cells[name].formula, VISIO_ROLES) for name in names}
    records = sorted(
        (c.from_rel, c.xml.attrib["FromPart"], VISIO_ROLES[c.to_id], c.to_rel, c.xml.attrib["ToPart"]) for c in page.connects
    )
    return cells, records


def test_point_glue_writes_what_visio_writes():
    expected_cells, expected_records = _s07_connector()
    vis = Document.open(S05)
    page = vis.pages[0]
    source, target = page.shapes.by_id("90"), page.shapes.by_id("97")
    connector = page.connect(source, target, glue=Glue.POINT, to_point=1)
    roles = {source.ID: "A", target.ID: "B"}
    cells = {name: _by_role(connector.cells[name].formula, roles) for name in expected_cells}
    records = sorted(
        (c.from_rel, c.xml.attrib["FromPart"], roles[c.to_id], c.to_rel, c.xml.attrib["ToPart"])
        for c in page.connects
        if c.from_id == connector.ID
    )
    assert cells == expected_cells
    assert records == expected_records


def test_point_glue_names_only_the_shapes_it_glues():
    """The donor's `BegTrigger` named its own shape 1: point glue left it there, and wrote `BeginTrigger`."""
    vis = Document.open(S05)
    page = vis.pages[0]
    source, target = page.shapes.by_id("90"), page.shapes.by_id("97")
    connector = page.connect(source, target, glue=Glue.POINT)
    named = {
        match.group(1)
        for cell in connector.cells.values()
        if cell.formula
        for match in re.finditer(r"Sheet\.?(\d+)!", cell.formula)
    }
    assert named == {source.ID, target.ID}
    assert "BeginTrigger" not in connector.cells


def test_point_glue_reaches_the_points_a_shape_inherits():
    """Shape 53 is a flowchart Decision: its four connection points are its master's."""
    vis = Document.open(S05)
    page = vis.pages[0]
    source, decision = page.shapes.by_id("90"), page.shapes.by_id("53")
    connector = page.connect(source, decision, glue=Glue.POINT, to_point=3)
    (record,) = [c for c in page.connects if c.from_id == connector.ID and c.from_rel == "EndX"]
    assert (record.to_id, record.to_rel) == ("53", "Connections.X4")
    with pytest.raises(ValueError, match="connection point"):
        page.connect(source, decision, glue=Glue.POINT, to_point=4)
