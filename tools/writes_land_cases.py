"""Write the files the Visio harness checks the writes-land package against (#300, #319, #430).

Usage: python tools/writes_land_cases.py <out-dir>

Each case is one ``.vsdx`` in <out-dir>, and ``EXPECTED.txt`` there says, one
line per case, what Visio must show. On Windows with desktop Visio, run
``python tools/visio_verify.py check <out-dir>/<case>.vsdx`` for each file, and
open the ones whose line names something to look at. The package is not
merged until every check agrees (CONTRIBUTING, "When a change needs Visio").
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from vsdxkit.document import Document

_TESTS = Path(__file__).resolve().parent.parent / "tests"
"""The fixtures the cases start from."""


def _copy(fixture: str, out: Path, case: str) -> tuple[Document, Path]:
    """`fixture` copied into `out` as `case`.vsdx, and opened."""
    target = out / f"{case}.vsdx"
    shutil.copy(_TESTS / fixture, target)
    return Document.open(target), target


def colours(out: Path) -> str:
    """Case 1: colours set on a master instance whose master's cells are theme formulas."""
    document, path = _copy("fixtures/com_reference/s05_swimlanes_cfflow.vsdx", out, "01_colours")
    shape = document.pages[0].shapes.require_id("35")
    shape.line_color = "#FF0000"
    shape.fill_color = "#00FF00"
    shape.text_color = "#0000FF"
    document.save(path)
    return "01_colours: shape 35 has a red line, a green fill and blue text"


def text_colour(out: Path) -> str:
    """Case 1b: text colour written over a Character colour formula."""
    document, path = _copy("test12_colors.vsdx", out, "01b_text_colour")
    document.pages[0].shapes.require_id("2").text_color = "#0000FF"
    document.save(path)
    return "01b_text_colour: shape 2's text is blue"


def guarded(out: Path) -> str:
    """Case 2: a position and a size written over GUARD formulas."""
    document, path = _copy("test1.vsdx", out, "02_guarded")
    shape = document.pages[0].shapes.require_id("1")
    shape.set_cell_formula("Width", "GUARD(1)")
    shape.set_cell_formula("PinX", "GUARD(1)")
    shape.width = 2.5
    shape.x = 3.0
    document.save(path)
    return "02_guarded: shape 1 is 2.5 in wide with its pin at x = 3.0 in"


def glued_end(out: Path) -> str:
    """Case 3: one end of a connector glued at both ends, written to."""
    document, path = _copy("test4_connectors.vsdx", out, "03_glued_end")
    connector = document.pages[0].shapes.require_id("6")
    connector.begin_x = (connector.begin_x or 0.0) - 1.0
    document.save(path)
    return "03_glued_end: connector 6's begin is free, 1 in left of where it was; its end is still glued to shape 2"


CASES: tuple[Callable[[Path], str], ...] = (colours, text_colour, guarded, glued_end)
"""Every case, in the order its file is numbered."""


def main(argv: list[str] | None = None) -> int:
    """Write every case into the folder named by the one argument; 2 for a usage error."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(args[0])
    out.mkdir(parents=True, exist_ok=True)
    lines = [case(out) for case in CASES]
    (out / "EXPECTED.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
