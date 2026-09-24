import os
import shutil

from vsdxkit.vsdxfile import VisioFile

SENTINELS = ["PALETTE_PROCESS", "PALETTE_DECISION", "PALETTE_START_END", "PALETTE_PARALLELOGRAM", "PALETTE_DATABASE"]


def test_palette_fixture_contains_all_sentinels(basedir):
    vis = VisioFile(os.path.join(basedir, "fixtures", "palette_extended.vsdx"))
    page = vis.pages[0]
    for sentinel in SENTINELS:
        assert page.shapes.by_text(sentinel) is not None, sentinel


def test_palette_shape_copies_into_stock_template(tmp_path, basedir):
    dst = str(tmp_path / "target.vsdx")
    shutil.copy(os.path.join(basedir, "test8_simple_connector.vsdx"), dst)
    palette = VisioFile(os.path.join(basedir, "fixtures", "palette_extended.vsdx"))
    decision = palette.pages[0].shapes.require_text("PALETTE_DECISION")
    target = VisioFile(dst)
    page = target.pages[0]
    target.copy_shape(decision.xml, page)
    target.save_vsdx(dst)
    check = VisioFile(dst)
    assert check.pages[0].shapes.by_text("PALETTE_DECISION") is not None
