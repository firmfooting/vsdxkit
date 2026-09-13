import os
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile

import pytest

from vsdx import VisioFile


def get_copy(basedir: str, filename: str, target_dir: str) -> str:
    src = os.path.join(basedir, filename)
    dst = os.path.join(target_dir, filename)
    shutil.copy(src, dst)
    return dst


def test_connect_shapes_dynamic_glue_formulas(basedir):
    with VisioFile(os.path.join(basedir, "test8_simple_connector.vsdx")) as vis:
        page = vis.pages[0]
        a = page.find_shape_by_text("Shape A")
        b = page.find_shape_by_text("Shape B")
        assert a is not None and b is not None
        connector = page.connect_shapes(a, b)
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
    with VisioFile(os.path.join(basedir, "test8_simple_connector.vsdx")) as vis:
        page = vis.pages[0]
        a = page.find_shape_by_text("Shape A")
        b = page.find_shape_by_text("Shape B")
        connector = page.connect_shapes(a, b)
        connects = {c.from_rel: c for c in page.connects if c.from_id == str(connector.ID)}
        assert "BeginX" in connects and "EndX" in connects
        begin = connects["BeginX"]
        assert begin.to_id == str(a.ID)
        assert begin.to_rel == "PinX"
        end = connects["EndX"]
        assert end.to_id == str(b.ID)
        assert end.to_rel == "PinX"


def test_connect_shapes_route_variants(basedir):
    with VisioFile(os.path.join(basedir, "test8_simple_connector.vsdx")) as vis:
        page = vis.pages[0]
        a = page.find_shape_by_text("Shape A")
        b = page.find_shape_by_text("Shape B")
        straight = page.connect_shapes(a, b, route="straight")
        assert straight.cells["ShapeRouteStyle"].value == "16"
        right = page.connect_shapes(a, b, route="rightangle")
        assert right.cells["ShapeRouteStyle"].value == "1"
        curved = page.connect_shapes(a, b, route="curved")
        assert curved.cells["ShapeRouteStyle"].value == "17"
        assert curved.cells["ConLineRouteExt"].value == "2"
        plain = page.connect_shapes(a, b)
        assert plain.cells["ShapeRouteStyle"].value == "0"


def test_connect_point_glue_requires_connection_points(basedir):
    with VisioFile(os.path.join(basedir, "test8_simple_connector.vsdx")) as vis:
        page = vis.pages[0]
        a = page.find_shape_by_text("Shape A")
        b = page.find_shape_by_text("Shape B")
        with pytest.raises(ValueError):
            page.connect_shapes(a, b, route="point")


def test_connect_shapes_combines_point_glue_and_curved_routing(basedir):
    fixture = os.path.join(basedir, "fixtures", "com_reference", "s05_swimlanes_cfflow.vsdx")
    with VisioFile(fixture) as vis:
        page = vis.pages[0]
        source = page.find_shape_by_id("90")
        target = page.find_shape_by_id("97")
        assert source is not None and target is not None

        connector = page.connect_shapes(source, target, route="point|curved", from_cp=0, to_cp=2)

        source_point = f"PAR(PNT(Sheet{source.ID}!Connections.X1,Sheet{source.ID}!Connections.Y1))"
        target_point = f"PAR(PNT(Sheet{target.ID}!Connections.X3,Sheet{target.ID}!Connections.Y3))"
        assert connector.cells["BeginX"].formula == source_point
        assert connector.cells["EndX"].formula == target_point
        assert connector.cells["ShapeRouteStyle"].value == "17"
        assert connector.cells["ConLineRouteExt"].value == "2"
        records = {connect.from_rel: connect for connect in page.connects if connect.from_id == str(connector.ID)}
        assert records["BeginX"].to_rel == "Connections.X1"
        assert records["EndX"].to_rel == "Connections.X3"


def test_invalid_route_fails_before_mutating_page(basedir):
    with VisioFile(os.path.join(basedir, "test8_simple_connector.vsdx")) as vis:
        page = vis.pages[0]
        source = page.find_shape_by_text("Shape A")
        target = page.find_shape_by_text("Shape B")
        assert source is not None and target is not None
        before_shapes = len(page.all_shapes)
        before_connects = len(page.connects)

        with pytest.raises(ValueError, match="unknown connector route"):
            page.connect_shapes(source, target, route="diagonal")

        assert len(page.all_shapes) == before_shapes
        assert len(page.connects) == before_connects


def test_connector_round_trip_and_zip_validity(basedir):
    with tempfile.TemporaryDirectory() as tmp:
        src = get_copy(basedir, "test8_simple_connector.vsdx", tmp)
        with VisioFile(src) as vis:
            page = vis.pages[0]
            a = page.find_shape_by_text("Shape A")
            b = page.find_shape_by_text("Shape B")
            connector = page.connect_shapes(a, b, route="curved")
            conn_id = connector.ID
            vis.save_vsdx(src)
        with zipfile.ZipFile(src) as z:
            assert z.testzip() is None
        with VisioFile(src) as vis2:
            page = vis2.pages[0]
            reopened = page.find_shape_by_id(str(conn_id))
            assert reopened is not None
            assert reopened.cells["BegTrigger"].formula == f"_XFTRIGGER(Sheet{a.ID}!EventXFMod)"
            assert reopened.cells["EndTrigger"].formula == f"_XFTRIGGER(Sheet{b.ID}!EventXFMod)"
            assert reopened.cells["ShapeRouteStyle"].value == "17"


def test_delete_shape_cascades_connectors(basedir):
    with tempfile.TemporaryDirectory() as tmp:
        src = get_copy(basedir, "test4_connectors.vsdx", tmp)
        with VisioFile(src) as vis:
            page = vis.pages[0]
            before_connects = len(list(page.connects))
            assert before_connects > 0
            doomed = page.find_shape_by_id("2")
            assert doomed is not None
            page.delete_shape(doomed)
            vis.save_vsdx(src)
        with zipfile.ZipFile(src) as z:
            assert z.testzip() is None
        with VisioFile(src) as vis2:
            page = vis2.pages[0]
            # shape 2 and both connectors attached to it (6 and 7) are gone
            assert page.find_shape_by_id("2") is None
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
    with VisioFile(src) as vis:
        page = vis.pages[0]
        a = page.find_shape_by_property_label_value("Network Name", "House01")
        b = page.find_shape_by_property_label_value("Network Name", "Box01")
        assert a is not None and b is not None
        connector = page.connect_shapes(a, b)
        assert connector is not None
        # the connector now references a master that exists in THIS document
        assert vis.get_master_page_by_id(connector.master_page_ID) is not None
        vis.save_vsdx(src)
    with zipfile.ZipFile(src) as z:
        assert z.testzip() is None
        rels = z.read("visio/_rels/document.xml.rels").decode()
        # exactly one masters relationship, imported master part present
        assert rels.count("relationships/masters") == 1
        master_parts = [n for n in z.namelist() if n.startswith("visio/masters/master")]
        assert len(master_parts) >= 2  # original + imported
    with VisioFile(src) as vis2:
        page = vis2.pages[0]
        assert page.find_shape_by_text("") is not None  # reopen is valid
        connectors = [s for s in page.all_shapes if "BeginX" in s.cells]
        assert len(connectors) == 1


def test_master_import_is_idempotent(tmp_path, basedir):
    """Three connectors on an own-masters doc import the connector master once."""
    src = get_copy(basedir, "test3_house.vsdx", str(tmp_path))
    with VisioFile(src) as vis:
        page = vis.pages[0]
        a = page.find_shape_by_property_label_value("Network Name", "House01")
        b = page.find_shape_by_property_label_value("Network Name", "Box01")
        c = page.find_shape_by_id("1")
        assert a is not None and b is not None and c is not None
        connectors = [page.connect_shapes(a, b), page.connect_shapes(b, c), page.connect_shapes(c, a)]
        # all three connectors resolve to the one imported master
        master_ids = {connector.master_page_ID for connector in connectors}
        assert None not in master_ids, "connector was created without a master reference"
        assert len(master_ids) == 1
        vis.save_vsdx(src)
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
