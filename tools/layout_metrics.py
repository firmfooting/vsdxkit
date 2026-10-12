"""Measure the layout corpus: size, aspect, crossings, bends, port rules, shared runs and time.

Usage:
    python tools/layout_metrics.py [--json] [--dense] [--write FILE] [--against REF]

``--dense`` adds the dense random cells of ``dense_matrix.py`` at seed 0. ``--write`` records the numbers as the
baseline the ratchet test reads. ``--against REF`` measures the git revision REF (which must contain this tool) and
prints it beside the working tree with the difference per column. Timing is machine-specific, so the tool reports it
and the pytest suite never asserts on it.
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dense_matrix  # noqa: E402
import layout_corpus as corpus  # noqa: E402
from helpers import route_metrics as rm  # noqa: E402

COLUMNS = (
    "nodes",
    "edges",
    "width",
    "height",
    "aspect",
    "crossings",
    "max_bends",
    "port_gap_violations",
    "port_order_violations",
    "shared_runs",
    "fallbacks",
    "seconds",
)
"""The measured columns, in table order."""


def _row(layout, seconds: float) -> dict[str, float | int]:
    """The columns for one layout laid out in `seconds`."""
    return {
        "nodes": len(layout.nodes),
        "edges": len(layout.routes),
        "width": round(layout.width, 2),
        "height": round(layout.height, 2),
        "aspect": round(rm.aspect(layout), 3),
        "crossings": rm.crossings(layout),
        "max_bends": max((rm.bends(route) for route in layout.routes.values()), default=0),
        "port_gap_violations": len(rm.port_gap_violations(layout)),
        "port_order_violations": len(rm.port_order_violations(layout)),
        "shared_runs": len(rm.shared_runs(layout)),
        "fallbacks": getattr(layout, "fallbacks", 0),
        "seconds": round(seconds, 3),
    }


def measure_all() -> dict[str, dict[str, float | int]]:
    """Every corpus entry's columns by name; a fixture that fails to load raises, naming itself."""
    builders = {stem: (corpus.fixture_layout, stem) for stem in corpus.FIXTURES}
    builders.update({f"rand-{seed}": (corpus.random_layout, seed, 40, 60) for seed in range(5)})
    rows = {}
    for name, (build, *args) in builders.items():
        start = time.perf_counter()
        layout = build(*args)
        rows[name] = _row(layout, time.perf_counter() - start)
    return rows


def measure_dense() -> dict[str, dict[str, float | str]]:
    """Seconds and outcome of each dense cell at seed 0, keyed by its parameters."""
    out = {}
    for n, m, lanes, groups, direction in dense_matrix.CELLS:
        seconds, _steps, _searched, outcome = dense_matrix.measure(0, n, m, lanes, groups, direction)
        out[f"{n}-{m}-{lanes}-{groups}-{direction}"] = {"seconds": round(seconds, 2), "outcome": outcome}
    return out


MISSING = "n/a"
"""What a table cell shows for a case or column the reference revision does not have."""


def _table(rows: dict[str, dict[str, float | int]], other: dict[str, dict[str, float | int]] | None = None) -> str:
    """A markdown table of `rows`; with `other`, each cell reads `other -> rows` where they differ, `n/a` for a missing one."""
    lines = ["| case | " + " | ".join(COLUMNS) + " |", "| --- |" + " --- |" * len(COLUMNS)]
    for name in rows if other is None else sorted(set(rows) | set(other)):
        cells = []
        for column in COLUMNS:
            now = rows.get(name, {}).get(column, MISSING)
            before = now if other is None else other.get(name, {}).get(column, MISSING)
            cells.append(str(now) if before == now else f"{before} -> {now}")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render(
    metrics: dict[str, dict[str, float | int]],
    dense: dict[str, dict[str, float | str]],
    reference: dict[str, dict[str, float | int]] | None,
    as_json: bool,
) -> str:
    """The report in one mode: JSON always carries metrics, dense and (with a reference) the reference's metrics only, not its dense cells; the table prints dense below."""
    if as_json:
        record: dict = {"metrics": metrics, "dense": dense}
        if reference is not None:
            record["against"] = reference
        return json.dumps(record, indent=2, sort_keys=True)
    out = _table(metrics, reference)
    return out + ("\n\n" + json.dumps(dense, indent=2, sort_keys=True) if dense else "")


def _reference(ref: str) -> dict[str, dict[str, float | int]]:
    """The metrics of git revision `ref`, run from a throwaway export of its src, tests and tools."""
    with tempfile.TemporaryDirectory() as tmp:
        archive = subprocess.run(["git", "archive", ref, "src", "tests", "tools"], cwd=ROOT, capture_output=True, check=True)
        subprocess.run(["tar", "-x", "-C", tmp], input=archive.stdout, check=True)
        tool = Path(tmp) / "tools" / "layout_metrics.py"
        if not tool.exists():
            raise SystemExit(f"{ref} has no tools/layout_metrics.py; REF must contain Phase 0")
        env = {**os.environ, "PYTHONPATH": str(Path(tmp) / "src")}
        result = subprocess.run([sys.executable, str(tool), "--json"], capture_output=True, text=True, check=True, env=env)
        data = json.loads(result.stdout)
        return data.get("metrics", data)  # a Phase 0 revision prints the bare metrics


def main(argv: list[str] | None = None) -> int:
    """Print the corpus metrics, or write them as the baseline; 0 on success."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    parser.add_argument("--dense", action="store_true", help="also time the dense cells")
    parser.add_argument("--write", metavar="FILE", help="write the baseline file")
    parser.add_argument("--against", metavar="REF", help="compare with git revision REF")
    args = parser.parse_args(argv)
    metrics = measure_all()
    dense = measure_dense() if args.dense else {}
    if args.write:
        record = {"version": "0.10.0", "platform": platform.platform(), "metrics": metrics, "dense": dense}
        with open(args.write, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
    print(render(metrics, dense, _reference(args.against) if args.against else None, args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
