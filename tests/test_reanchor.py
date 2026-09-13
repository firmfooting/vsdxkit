"""Tests for connector retargeting (re-anchor)."""

import zipfile

import pytest

from vsdxkit import VisioFile

BASE = "test8_simple_connector.vsdx"


def test_retarget_both_ends(vsdx_copy):
    path = vsdx_copy(BASE)
    with VisioFile(path) as vis:
        page = vis.pages[0]
        a = page.find_shape_by_text("Shape A")
        b = page.find_shape_by_text("Shape B")
        connector = page.connect_shapes(a, b)
        # fresh shapes to retarget to
        c = vis.create_shape(page, "PALETTE_PROCESS", 7.0, 6.0, text="Target C")
        d = vis.create_shape(page, "PALETTE_PROCESS", 7.0, 3.0, text="Target D")

        page.reanchor_connector(connector, from_shape=c, to_shape=d)

        records = [rc for rc in page.connects if rc.from_id == str(connector.ID)]
        endpoints = {(rc.from_rel, rc.to_id) for rc in records}
        assert ("BeginX", str(c.ID)) in endpoints
        assert ("EndX", str(d.ID)) in endpoints
        # old records replaced, not duplicated
        assert len(records) == 2
        # triggers reference the new shapes
        assert f"Sheet{c.ID}!" in connector.cells["BegTrigger"].formula
        assert f"Sheet{d.ID}!" in connector.cells["EndTrigger"].formula
        vis.save_vsdx(path)
    assert zipfile.ZipFile(path).testzip() is None


def test_retarget_one_end_keeps_other(vsdx_copy):
    with VisioFile(vsdx_copy(BASE)) as vis:
        page = vis.pages[0]
        a = page.find_shape_by_text("Shape A")
        b = page.find_shape_by_text("Shape B")
        connector = page.connect_shapes(a, b)
        c = vis.create_shape(page, "PALETTE_PROCESS", 7.0, 6.0, text="Target C")

        page.reanchor_connector(connector, to_shape=c)  # keep begin at A

        records = [rc for rc in page.connects if rc.from_id == str(connector.ID)]
        endpoints = {(rc.from_rel, rc.to_id) for rc in records}
        assert ("BeginX", str(a.ID)) in endpoints  # kept
        assert ("EndX", str(c.ID)) in endpoints  # moved


def test_retarget_unconnected_connector_raises(vsdx_copy):
    with VisioFile(vsdx_copy(BASE)) as vis:
        page = vis.pages[0]
        a = page.find_shape_by_text("Shape A")
        b = page.find_shape_by_text("Shape B")
        connector = page.connect_shapes(a, b)
        for rc in list(page.connects):
            if rc.from_id == str(connector.ID):
                page.remove_connect_records([connector.ID])
                break
        with pytest.raises(ValueError):
            page.reanchor_connector(connector, to_shape=b)


def test_remove_connect_records_normalises_integer_ids(vsdx_copy):
    with VisioFile(vsdx_copy(BASE)) as vis:
        page = vis.pages[0]
        a = page.find_shape_by_text("Shape A")
        b = page.find_shape_by_text("Shape B")
        assert a is not None and b is not None
        connector = page.connect_shapes(a, b)
        connector_id = str(connector.ID)

        assert any(record.from_id == connector_id for record in page.connects)
        page.remove_connect_records([int(connector_id)])
        assert all(record.from_id != connector_id for record in page.connects)
