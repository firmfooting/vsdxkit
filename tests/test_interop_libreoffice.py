"""Round-trip a saved package through LibreOffice Draw.

libvisio, which backs LibreOffice's Visio import filter, is stricter about
namespace prefixes than Visio itself: a package whose parts arrive under
ElementTree's generated `ns0:` prefixes imports as an empty document or fails
outright (upstream dave-howard/vsdx#90, #35). Converting to PDF headlessly is
the cheapest end-to-end check that the package is still readable by something
other than this library.

Skipped unless `soffice` is on PATH, so it is opt-in locally and gated by a
dedicated CI job.
"""

import os
import shutil
import subprocess

import pytest

import vsdx

FIXTURES = os.path.dirname(os.path.realpath(__file__))

soffice = shutil.which("soffice") or shutil.which("libreoffice")

pytestmark = pytest.mark.skipif(soffice is None, reason="LibreOffice (soffice) is not on PATH")


def _assert_converts_to_pdf(document: str, tmp_path) -> None:
    """Convert a saved package to PDF headlessly and require a non-empty result."""
    profile = os.path.join(str(tmp_path), "profile")
    result = subprocess.run(
        [
            str(soffice),
            f"-env:UserInstallation=file://{profile}",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(tmp_path),
            document,
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    pdf = os.path.join(str(tmp_path), os.path.splitext(os.path.basename(document))[0] + ".pdf")
    assert result.returncode == 0, result.stderr
    assert os.path.exists(pdf), f"no PDF produced: {result.stdout}\n{result.stderr}"
    assert os.path.getsize(pdf) > 0


@pytest.mark.parametrize("filename", ["test1.vsdx", "test4_connectors.vsdx", "test3_house.vsdx"])
def test_edited_package_converts_in_libreoffice(filename, tmp_path):
    out = os.path.join(str(tmp_path), filename)
    with vsdx.VisioFile(os.path.join(FIXTURES, filename)) as vis:
        page = vis.pages[0]
        shape = page.child_shapes[0]
        shape.text = "converted by libreoffice"
        vis.save_vsdx(out)

    _assert_converts_to_pdf(out, tmp_path)


def test_created_connector_package_converts_in_libreoffice(tmp_path):
    """Cover the path that writes package wiring; the test above only edits shape text.

    ``Connect.create()`` imports the connector master, which adds a master part,
    a content-type override, a masters.xml.rels entry and a per-page
    relationship. tests/test_master_import_opc.py asserts that graph directly;
    this checks that a second implementation can still open the result.
    ``test3_house.vsdx`` ships one master, so the connector is imported rather
    than copied wholesale with the masters folder.
    """
    out = os.path.join(str(tmp_path), "created_connector.vsdx")
    with vsdx.VisioFile(os.path.join(FIXTURES, "test3_house.vsdx")) as vis:
        page = vis.pages[0]
        connector = vsdx.Connect.create(
            page=page,
            from_shape=page.find_shape_by_text("Shape to copy"),
            to_shape=page.find_shape_by_text("Shape to remove"),
        )
        connector.text = "created by vsdx"
        vis.save_vsdx(out)

    _assert_converts_to_pdf(out, tmp_path)
