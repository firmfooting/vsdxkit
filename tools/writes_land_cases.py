"""Write the files the Visio harness checks the writes-land package against (#300, #319, #430).

Usage:
    python tools/writes_land_cases.py <out-dir>
    python tools/writes_land_cases.py check <out-dir>

Each case is one ``.vsdx`` in <out-dir>. ``EXPECTED.txt`` there says, one line
per case, what Visio must show, for a person to read; ``expected.json`` says
the same thing as data, for ``check`` to judge without a person reading
anything. ``check`` asks a Windows Visio what it shows for each written cell,
both on open and after ``Cell.Trigger()`` forces it to recalculate: Visio shows
the cached value it opened with until something recalculates a cell, and a
stale formula left in place by a bug (a ``GUARD()``, a theme) wins only at
that point, so reading the open value alone would miss exactly the write this
checks for. The package is not merged until every check passes (CONTRIBUTING,
"When a change needs Visio").
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from vsdxkit.document import Document

_TESTS = Path(__file__).resolve().parent.parent / "tests"
"""The fixtures the cases start from."""


@dataclass(frozen=True)
class CellCheck:
    """One cell Visio must show `want` for, both on open and after it recalculates."""

    page: int
    """The 1-based page the shape sits on."""
    shape: int
    """The shape's Visio ID, page-scoped."""
    cell: str
    """A Visio universal cell name: PinX, LineColor, Char.Color, ..."""
    want: float | str
    """A number in internal units (inches), or text that must appear, spaces removed, in Visio's result string."""


@dataclass(frozen=True)
class GlueCheck:
    """The glue records Visio's Connects must hold for one connector's end, on one page."""

    page: int
    """The 1-based page the connector sits on."""
    connector: int
    """The connector's Visio ID, page-scoped."""
    records: frozenset[tuple[str, int]]
    """Every (from_cell, to_shape) pair Visio must report for this connector on this page."""


@dataclass(frozen=True)
class Case:
    """One written file: the line a person reads, and what Visio must show for the write to have landed."""

    line: str
    """The sentence written into EXPECTED.txt for a person to read."""
    cells: tuple[CellCheck, ...]
    """Every cell Visio must show a value for."""
    glue: tuple[GlueCheck, ...] = ()
    """Every glue record Visio must hold, for a case that touches a connector's end."""
    stem: str = ""
    """The file's name without `.vsdx`; `expected.json`'s key for this case. Set from the path the case wrote."""


def _copy(fixture: str, out: Path, case: str) -> tuple[Document, Path]:
    """`fixture` copied into `out` as `case`.vsdx, and opened."""
    target = out / f"{case}.vsdx"
    shutil.copy(_TESTS / fixture, target)
    return Document.open(target), target


def colours(out: Path) -> Case:
    """Case 1: colours set on a master instance whose master's cells are theme formulas."""
    document, path = _copy("fixtures/com_reference/s05_swimlanes_cfflow.vsdx", out, "01_colours")
    shape = document.pages[0].shapes.require_id("35")
    shape.line_color = "#FF0000"
    shape.fill_color = "#00FF00"
    shape.text_color = "#0000FF"
    document.save(path)
    shape_id = int(shape.ID)
    return Case(
        "01_colours: shape 35 has a red line, a green fill and blue text",
        (
            CellCheck(1, shape_id, "LineColor", "RGB(255,0,0)"),
            CellCheck(1, shape_id, "FillForegnd", "RGB(0,255,0)"),
            CellCheck(1, shape_id, "Char.Color", "RGB(0,0,255)"),
        ),
        stem=path.stem,
    )


def text_colour(out: Path) -> Case:
    """Case 1b: text colour written over a Character colour formula."""
    document, path = _copy("test12_colors.vsdx", out, "01b_text_colour")
    shape = document.pages[0].shapes.require_id("2")
    shape.text_color = "#0000FF"
    document.save(path)
    return Case(
        "01b_text_colour: shape 2's text is blue",
        (CellCheck(1, int(shape.ID), "Char.Color", "RGB(0,0,255)"),),
        stem=path.stem,
    )


def guarded(out: Path) -> Case:
    """Case 2: a position and a size written over GUARD formulas."""
    document, path = _copy("test1.vsdx", out, "02_guarded")
    shape = document.pages[0].shapes.require_id("1")
    shape.set_cell_formula("Width", "GUARD(1)")
    shape.set_cell_formula("PinX", "GUARD(1)")
    shape.width = 2.5
    shape.x = 3.0
    document.save(path)
    shape_id = int(shape.ID)
    return Case(
        "02_guarded: shape 1 is 2.5 in wide with its pin at x = 3.0 in",
        (
            CellCheck(1, shape_id, "Width", 2.5),
            CellCheck(1, shape_id, "PinX", 3.0),
        ),
        stem=path.stem,
    )


def glued_end(out: Path) -> Case:
    """Case 3: one end of a connector glued at both ends, written to."""
    document, path = _copy("test4_connectors.vsdx", out, "03_glued_end")
    connector = document.pages[0].shapes.require_id("6")
    begin_x = connector.begin_x or 0.0
    begin_y = connector.begin_y or 0.0
    connector.begin_x = begin_x - 1.0
    document.save(path)
    connector_id = int(connector.ID)
    return Case(
        "03_glued_end: connector 6's begin is free, 1 in left of where it was; its end is still glued to shape 2",
        (
            CellCheck(1, connector_id, "BeginX", begin_x - 1.0),
            CellCheck(1, connector_id, "BeginY", begin_y),
        ),
        (GlueCheck(1, connector_id, frozenset({("EndX", 2)})),),
        stem=path.stem,
    )


CASES: tuple[Callable[[Path], Case], ...] = (colours, text_colour, guarded, glued_end)
"""Every case, in the order its file is numbered."""


def _as_json(cases: list[Case]) -> dict[str, dict]:
    """`expected.json`'s payload: each case's line and expectations, keyed by its stem."""
    return {
        case.stem: {
            "line": case.line,
            "cells": [[c.page, c.shape, c.cell, c.want] for c in case.cells],
            "glue": [[g.page, g.connector, [list(record) for record in sorted(g.records)]] for g in case.glue],
        }
        for case in cases
    }


def _read_expected(path: Path) -> dict[str, Case]:
    """The inverse of `_as_json`: rebuild the `Case`s `check` needs to judge Visio's answer."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        stem: Case(
            data["line"],
            tuple(CellCheck(page, shape, cell, want) for page, shape, cell, want in data["cells"]),
            tuple(
                GlueCheck(page, connector, frozenset(tuple(record) for record in records))
                for page, connector, records in data["glue"]
            ),
            stem=stem,
        )
        for stem, data in raw.items()
    }


def _judge_cell(stem: str, check: CellCheck, got: dict | None) -> str | None:
    """None if Visio's answer for one cell matches `check`; otherwise the failure line."""
    prefix = f"{stem}: p{check.page} shape {check.shape} {check.cell}"
    if got is None:
        return f"{prefix}: Visio was not asked for this cell"
    if got.get("error"):
        return f"{prefix}: Visio could not read it: {got['error']}"
    if not got.get("exists", False):
        return f"{prefix}: Visio does not have this cell"
    if got.get("recalc_error"):
        return f"{prefix}: Visio could not recalculate it: {got['recalc_error']}"
    if isinstance(check.want, float):
        opened, recalculated = got.get("result_iu"), got.get("recalc_iu")
        ok = (
            isinstance(opened, int | float)
            and isinstance(recalculated, int | float)
            and math.isclose(opened, check.want, abs_tol=1e-6)
            and math.isclose(recalculated, check.want, abs_tol=1e-6)
        )
        shown = f"{opened!r} on open and {recalculated!r} after recalculating"
    else:
        wanted = check.want.replace(" ", "")
        opened = str(got.get("result_str", "")).replace(" ", "")
        recalculated = str(got.get("recalc_str", "")).replace(" ", "")
        ok = wanted in opened and wanted in recalculated
        shown = f"{got.get('result_str')!r} on open and {got.get('recalc_str')!r} after recalculating"
    if ok:
        return None
    return f"{prefix}: want {check.want!r}, Visio shows {shown}"


def _judge_glue(stem: str, glue: GlueCheck, connects: list[dict]) -> str | None:
    """None if Visio's Connects for one connector match `glue`; otherwise the failure line."""
    have = {
        (connect["from_cell"], connect["to_shape"])
        for connect in connects
        if connect.get("page") == glue.page and connect.get("from_shape") == glue.connector
    }
    if have == glue.records:
        return None
    return f"{stem}: p{glue.page} connector {glue.connector} glue: want {sorted(glue.records)}, Visio shows {sorted(have)}"


def judge(expected: dict[str, Case], payload: list[dict]) -> list[str]:
    """One line per check Visio's answer does not satisfy; empty means every write landed.

    A cell check passes only when Visio reports the cell exists, reading it
    raised no error either time, and both the value it shows on open and the
    value it shows after recalculating match what was written. A glue check
    passes only when the set of (from_cell, to_shape) records Visio's Connects
    holds for that connector, on that page, equals what was expected exactly.
    """
    by_stem: dict[str, dict] = {}
    for record in payload:
        path = str(record.get("path", ""))
        for stem in expected:
            if path.endswith(f"\\{stem}.vsdx") or path.endswith(f"/{stem}.vsdx"):
                by_stem[stem] = record
                break

    failures: list[str] = []
    for stem, case in expected.items():
        record = by_stem.get(stem)
        if record is None:
            failures.append(f"{stem}: Visio reported no document for this file")
            continue
        cells_by_key = {(cell["page"], cell["shape"], cell["cell"]): cell for cell in record.get("cells", [])}
        for check in case.cells:
            failure = _judge_cell(stem, check, cells_by_key.get((check.page, check.shape, check.cell)))
            if failure is not None:
                failures.append(failure)
        for glue in case.glue:
            failure = _judge_glue(stem, glue, record.get("connects", []))
            if failure is not None:
                failures.append(failure)
    return failures


def _ask_visio(tools_dir: Path, paths: list[str], expected: dict[str, Case], visio_verify) -> list[dict]:
    """Stage `paths`, run `visio_cells.ps1` over them, and return its parsed JSON."""
    with visio_verify._staged(paths) as (root, _by_name):
        request = {
            "files": [
                {
                    "path": visio_verify._windows_path(str(Path(root) / f"{stem}.vsdx")),
                    "cells": [{"page": c.page, "shape": c.shape, "cell": c.cell} for c in case.cells],
                }
                for stem, case in expected.items()
            ]
        }
        request_file = Path(root) / "request.json"
        request_file.write_text(json.dumps(request), encoding="utf-8")

        before = visio_verify._visio_pids()
        script = tools_dir / "visio_cells.ps1"
        # -Command rather than -File, and the ExecutionPolicy bypass, and
        # `; exit $LASTEXITCODE`: all for the reasons visio_verify._observe_directory
        # gives in its own comment - a UNC checkout path and a script-scoped
        # `exit` that otherwise never reaches the caller's own exit code.
        expression = (
            f"& {visio_verify._quote(visio_verify._windows_path(str(script)))} "
            f"-Request {visio_verify._quote(visio_verify._windows_path(str(request_file)))}; exit $LASTEXITCODE"
        )
        shell = visio_verify._shell()
        command = [shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", expression]
        timeout = 60 + 20 * len(paths)
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as expired:
            killed = visio_verify._reap_visio(before)
            raise visio_verify.VisioUnavailable(
                f"visio_cells.ps1 did not answer within {timeout}s and was killed"
                + (f" (stranded process {', '.join(map(str, killed))} also killed)" if killed else "")
            ) from expired

    payload_text = result.stdout.strip()
    if result.returncode != 0 or not payload_text:
        raise visio_verify.VisioUnavailable(
            f"visio_cells.ps1 exited {result.returncode}: {result.stderr.strip() or '(no output)'}"
        )
    try:
        return json.loads(payload_text)
    except json.JSONDecodeError as error:
        raise visio_verify.VisioUnavailable(
            f"visio_cells.ps1 produced output that is not JSON: {error}\n{payload_text[:400]}"
        ) from error


def _check(out: Path) -> int:
    """Ask Visio about every case already written into `out`, and judge its answer."""
    expected_file = out / "expected.json"
    if not expected_file.exists():
        print(f"no expected.json in {out}; run `python {sys.argv[0]} {out}` first", file=sys.stderr)
        return 2
    expected = _read_expected(expected_file)
    if not expected:
        print(f"{expected_file} names no cases", file=sys.stderr)
        return 2
    paths = [str(out / f"{stem}.vsdx") for stem in expected]
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        print(f"case file(s) not found: {', '.join(missing)}", file=sys.stderr)
        return 2

    tools_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(tools_dir))
    # Lazy: building cases must not need Visio's tooling to import cleanly.
    import visio_verify

    try:
        payload = _ask_visio(tools_dir, paths, expected, visio_verify)
    except visio_verify.VisioUnavailable as error:
        print(f"Visio is not usable from here: {error}", file=sys.stderr)
        return 2

    failures = judge(expected, payload)
    by_stem: dict[str, list[str]] = {stem: [] for stem in expected}
    for failure in failures:
        by_stem.setdefault(failure.split(": ", 1)[0], []).append(failure)
    for stem in expected:
        stem_failures = by_stem[stem]
        if stem_failures:
            for line in stem_failures:
                print(line)
        else:
            print(f"PASS {stem}")
    print(f"\n{len(failures)} failure(s)")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    """Write every case into `out`, or check what Visio shows for one already written; 2 for a usage error.

    ``main([out])`` writes every case into `out`, as ``EXPECTED.txt`` for a
    person and ``expected.json`` for ``check``. ``main(["check", out])`` asks a
    Windows Visio what it shows for each cell `out`'s cases wrote and judges
    it; see the module docstring for why each cell is read twice.
    """
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] == "check":
        if len(args) != 2:
            print(__doc__, file=sys.stderr)
            return 2
        return _check(Path(args[1]))
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(args[0])
    out.mkdir(parents=True, exist_ok=True)
    cases = [case(out) for case in CASES]
    lines = [case.line for case in cases]
    (out / "EXPECTED.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "expected.json").write_text(json.dumps(_as_json(cases), indent=2) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
