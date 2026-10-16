"""Copying a connector writes the Connect records for its glue (#313)."""

from helpers.connect_records import page_records

from vsdxkit.document import Document


def _records(page) -> set[tuple[str, str | None, str, str | None]]:
    """Every Connect record on the page, as (FromSheet, FromCell, ToSheet, ToCell)."""
    return {(c.from_id, c.from_rel, c.to_id, c.to_rel) for c in page_records(page)}


def test_a_copied_connector_is_glued_to_the_same_shapes(vsdx_copy, tmp_path):
    """The copy's formulas bind it to the original's endpoints, so the package must say so."""
    vis = Document.open(vsdx_copy("test7_with_connector.vsdx"))
    page = vis.pages[0]
    before = _records(page)
    original = [r for r in before if r[0] == "7"]
    assert original

    new_id = page.shapes.require_id("7").copy().ID

    assert _records(page) == before | {(new_id, *r[1:]) for r in original}
    vis.save(tmp_path / "out.vsdx")
