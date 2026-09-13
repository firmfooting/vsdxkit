import os
import shutil

from vsdxkit import VisioFile

SENTINELS = ["PALETTE_PROCESS", "PALETTE_DECISION", "PALETTE_START_END", "PALETTE_PARALLELOGRAM", "PALETTE_DATABASE"]


def test_palette_fixture_contains_all_sentinels(basedir):
    with VisioFile(os.path.join(basedir, "fixtures", "palette_extended.vsdx")) as vis:
        page = vis.pages[0]
        for sentinel in SENTINELS:
            assert page.find_shape_by_text(sentinel) is not None, sentinel


def test_palette_shape_copies_into_stock_template(tmp_path, basedir):
    dst = str(tmp_path / "target.vsdx")
    shutil.copy(os.path.join(basedir, "test8_simple_connector.vsdx"), dst)
    with VisioFile(os.path.join(basedir, "fixtures", "palette_extended.vsdx")) as palette:
        decision = palette.pages[0].find_shape_by_text("PALETTE_DECISION")
        with VisioFile(dst) as target:
            page = target.pages[0]
            target.copy_shape(decision.xml, page)
            target.save_vsdx(dst)
    with VisioFile(dst) as check:
        assert check.pages[0].find_shape_by_text("PALETTE_DECISION") is not None
