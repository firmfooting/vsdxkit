"""Derive the bundled cross-functional flowchart from Visio's own capture of one.

    python tools/make_cff_donor.py tests/fixtures/com_reference/s05_swimlanes_cfflow.vsdx src/vsdxkit/_bundled/cff.vsdx

Keeps the CFF container, the Swimlane List, the three lanes, the Phase List and the Separator, and removes the
sample flowchart and the tips Visio's template puts on the page. Every shape ID then moves up by ID_OFFSET, so
the IDs a copy takes on a page never equal an ID that a donor formula still names, and the formulas follow. The file is then cleaned and written in the fixed member form, as ``tools/make_blank_template.py``
does, so deriving twice gives one file with nothing of the saving machine in it.
"""

from __future__ import annotations

import re
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from make_blank_template import clean, write

from vsdxkit._shape_tree import remap_sheet_references
from vsdxkit.document import Document

ID_OFFSET = 1000
"""How far every kept shape's ID is moved up."""
KEPT = ("CFF Container", "Swimlane List", "Swimlane", "Swimlane.9", "Swimlane.15", "Phase List", "Separator")
"""The NameU of each top-level shape the donor keeps."""


_GONE = re.compile(r",\s*Sheet\.(\d+)!SheetRef\(\)")
"""One argument of a ``DEPENDSON`` call in a ``Relationships`` formula: a shape the formula lists as related."""


def _forget_removed(root: ET.Element, present: set[str]) -> None:
    """Take every shape that is no longer on the page out of the ``Relationships`` formulas, which list related shapes by ID."""
    for cell in root.iter():
        formula = cell.attrib.get("F")
        if cell.tag.endswith("}Cell") and formula and "SheetRef()" in formula:
            cell.attrib["F"] = _GONE.sub(lambda m: m.group(0) if m.group(1) in present else "", formula)


def derive(source: Path, target: Path) -> int:
    """Write the donor made from `source` to `target`, and return how many shapes it holds."""
    document = Document.open(source)
    page = document.pages[0]
    for shape in list(page.children):
        if shape.is_attached and shape.xml.attrib.get("NameU") not in KEPT:
            shape.delete()
    root = page.xml.getroot()
    elements = [e for e in root.iter() if e.tag.endswith("}Shape")]
    _forget_removed(root, {e.attrib["ID"] for e in elements})
    id_map = {e.attrib["ID"]: int(e.attrib["ID"]) + ID_OFFSET for e in elements}
    remap_sheet_references(root, id_map)
    for e in elements:
        e.attrib["ID"] = str(id_map[e.attrib["ID"]])
    with tempfile.TemporaryDirectory() as folder:
        saved = Path(folder) / "donor.vsdx"
        document.save(saved)
        with zipfile.ZipFile(saved) as archive:
            members = {i.filename: archive.read(i) for i in archive.infolist() if not i.is_dir()}
    write(clean(members), target)
    return len(elements)


def main(argv: list[str] | None = None) -> int:
    """Derive the donor named by the two arguments."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    print(f"wrote {args[1]}: {derive(Path(args[0]), Path(args[1]))} shapes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
