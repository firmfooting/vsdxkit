"""Write the diagrams the Visio harness checks copied masters and created swimlanes against (#40).

Usage:
    python tools/diagram_cases.py <out-dir>
    python tools/writes_land_cases.py check <out-dir>
    python tools/visio_shots.py run --builder tools/diagram_cases.py

Each case is one ``.vsdx`` built by a case file under ``tests/fixtures/diagrams``. For every shape on every
page, ``expected.json`` asks Visio for the placement cells and for the X and Y of each row of the first
geometry section. A case file may also define ``style_checks(document)``, which adds the style-dependent cells
Visio must show. ``writes_land_cases.py check`` reads each cell twice, on open and after ``Cell.Trigger()``
recalculates it, and ``visio_shots.py`` photographs the same cases. The run is not done until every check
passes (CONTRIBUTING, "When a change needs Visio").
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parent))

from writes_land_cases import Case, CellCheck, as_json

from vsdxkit import namespace
from vsdxkit.document import Document

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "diagrams"
"""Where the case files are: each defines ``build()``, the same function ``visio_verify.py record --transform build`` runs."""


def _load(name: str) -> ModuleType:
    """The case file `name` as a module."""
    spec = importlib.util.spec_from_file_location(f"diagram_case_{name}", FIXTURES / f"{name}.py")
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load the case file {name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _checks(document: Document) -> tuple[CellCheck, ...]:
    """The placement and outline cells Visio must show for every shape in `document`, as written."""
    checks: list[CellCheck] = []
    for number, page in enumerate(document.pages, start=1):
        for shape in page.shapes:
            shape_id = int(shape.ID)
            placement = (("PinX", shape.x), ("PinY", shape.y), ("Width", shape.width), ("Height", shape.height))
            checks += [CellCheck(number, shape_id, name, float(value)) for name, value in placement if value is not None]
            section = shape.xml.find(f'{namespace}Section[@N="Geometry"]')
            for row in [] if section is None else section.findall(f"{namespace}Row"):
                for cell in row.findall(f"{namespace}Cell"):
                    if cell.attrib["N"] in ("X", "Y") and "V" in cell.attrib:
                        checks.append(
                            CellCheck(
                                number, shape_id, f"Geometry1.{cell.attrib['N']}{row.attrib['IX']}", float(cell.attrib["V"])
                            )
                        )
    return tuple(checks)


def _case(out: Path, stem: str, line: str) -> Case:
    """Build case file `stem` into `out`/`stem`.vsdx, deterministically, and say what Visio must show for it."""
    module = _load(stem)
    built = module.build()
    if not isinstance(built, Document):
        raise SystemExit(f"{stem}.py build() returned {type(built).__name__}, not a Document")
    path = built.save(out / f"{stem}.vsdx", deterministic=True)
    extra = tuple(
        CellCheck(1, shape, cell, want) for shape, cell, want in getattr(module, "style_checks", lambda _d: ())(built)
    )
    return Case(line, _checks(Document.open(path)) + extra, stem=stem)


LINES: tuple[tuple[str, str], ...] = (
    (
        "copy_style_clash",
        "copy_style_clash: a shape copied from a document whose style 7 is another style; its sub-shapes show the source's line pattern and margins",
    ),
    (
        "copy_style_absent",
        "copy_style_absent: a shape copied into a document with no style 7; its sub-shapes show the source's line pattern and margins",
    ),
    (
        "swimlanes",
        "swimlanes: a three-lane cross-functional flowchart from create_swimlanes, a process in each lane; every shape where it was written",
    ),
    ("lanes_one", "lanes_one: a cross-functional flowchart of one lane; every shape where it was written"),
    ("lanes_two", "lanes_two: two lanes, a process in each; every shape where it was written"),
    ("lanes_four", "lanes_four: four lanes, one labelled with the widest letters; every shape where it was written"),
    (
        "lanes_extremes",
        "lanes_extremes: a 0.5 inch lane, a 6 inch lane and a 5 inch wide diagram; every shape where it was written",
    ),
    ("lanes_five", "lanes_five: five lanes, a process in each; every shape where it was written"),
    (
        "lanes_uneven",
        "lanes_uneven: lanes of different heights, three processes in one and none in another; every shape where it was written",
    ),
    (
        "lanes_style_clash",
        "lanes_style_clash: a diagram in a document whose style 7 is another style; the Separator shows Flow Normal's margins",
    ),
    (
        "lanes_style_absent",
        "lanes_style_absent: a diagram in a document with no style 7; the Separator shows Flow Normal's margins",
    ),
    ("lanes_add", "lanes_add: a created two-lane diagram with a lane added by add_lane; every shape where it was written"),
    ("lanes_wide", "lanes_wide: a diagram 22 inches wide on a page widened to 24; every shape where it was written"),
    (
        "lanes_wide_60_3",
        "lanes_wide_60_3: three lanes, a diagram 60 inches wide on a page widened to 61; every shape where it was written",
    ),
    (
        "lanes_wide_60_5",
        "lanes_wide_60_5: five lanes, a diagram 60 inches wide on a page widened to 61; every shape where it was written",
    ),
    ("every_kind", "every_kind: nine node kinds, six edge kinds, a long edge, a self-loop; every shape where it was written"),
    (
        "node_outlines",
        "node_outlines: a decision and a rounded node each with three edges at offset points; every line and arrowhead must touch the drawn outline",
    ),
    ("groups_and_lanes", "groups_and_lanes: three lanes, a group holding a group; every shape where it was written"),
    (
        "group_heading_top_down",
        "group_heading_top_down: a top-down edge into a grouped node, whose one-line heading must stay clear of the connector; every shape where it was written",
    ),
    ("two_pages", "two_pages: two pages and a page link; every shape on both pages where it was written"),
)
"""Every case file's name and what Visio must show for it."""


def _runner(stem: str, line: str) -> Callable[[Path], Case]:
    """The callable that writes case `stem` into a folder and returns it, the form ``visio_shots.py`` runs."""
    return lambda out: _case(out, stem, line)


CASES: tuple[Callable[[Path], Case], ...] = tuple(_runner(stem, line) for stem, line in LINES)
"""Every case, in order."""

__all__ = ["CASES", "as_json", "main"]


def main(argv: list[str] | None = None) -> int:
    """Write every case into the one directory named, with ``EXPECTED.txt`` and ``expected.json``; 2 for a usage error."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(args[0])
    out.mkdir(parents=True, exist_ok=True)
    cases = [build(out) for build in CASES]
    (out / "EXPECTED.txt").write_text("\n".join(case.line for case in cases) + "\n", encoding="utf-8", newline="\n")
    (out / "expected.json").write_text(json.dumps(as_json(cases), indent=2) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(case.line for case in cases))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
