"""Fail if the installed wheel's public type completeness is below a threshold (#117).

Run by the CI build job against the wheel it built:

    python tools/check_type_completeness.py dist/*.whl --fail-under 100.0 --report type-completeness.json

It builds a throwaway venv outside the repository, installs the wheel and a
pinned pyright into it, and runs ``pyright --verifytypes vsdxkit
--ignoreexternal --outputjson`` from that venv's directory. Both halves
matter:

- pyright started inside the repository adds ``src/`` to its search paths and
  reads ``pyproject.toml``, so it measures the source tree instead of the
  wheel;
- the PyPI ``pyright`` wrapper resolves the package in whatever environment
  runs it, so a ``uvx pyright`` finds no ``vsdxkit`` at all and reports 0%.

The score is pyright's: the share of exported symbols whose type is known.
The threshold is a ratchet, like coverage: raise it when the score rises,
never lower it to make a red build green.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

# Renovate does not watch this file, so it does not bump this pin. Move it by
# hand when the dev dependency's pyright moves.
PYRIGHT = "pyright==1.1.414"
PACKAGE = "vsdxkit"


def score_of(report: dict[str, object]) -> float:
    """pyright's completeness score, as a percentage."""
    completeness = report["typeCompleteness"]
    assert isinstance(completeness, dict)
    return float(completeness["completenessScore"]) * 100


def floored(score: float) -> float:
    """The score rounded down to one decimal place, the form the threshold takes."""
    return math.floor(score * 10) / 10


def incomplete_symbols(report: dict[str, object]) -> list[str]:
    """Every exported symbol whose type pyright does not know, with its first diagnostic."""
    completeness = report["typeCompleteness"]
    assert isinstance(completeness, dict)
    lines = []
    for symbol in completeness["symbols"]:
        if not symbol["isExported"] or symbol["isTypeKnown"]:
            continue
        kind = "ambiguous" if symbol["isTypeAmbiguous"] else "unknown"
        diagnostics = symbol["diagnostics"]
        reason = diagnostics[0]["message"].splitlines()[0] if diagnostics else ""
        lines.append(f"{symbol['name']} ({kind}){': ' + reason if reason else ''}")
    return sorted(lines)


def problem_with(report: dict[str, object], venv: Path) -> str | None:
    """Why this report does not measure the installed wheel, or None if it does."""
    completeness = report.get("typeCompleteness")
    if not isinstance(completeness, dict):
        return "pyright wrote no typeCompleteness section"
    if not completeness.get("pyTypedPath"):
        return "pyright found no py.typed, so it measured nothing"
    root = Path(str(completeness.get("packageRootDirectory", "")))
    if not root.is_relative_to(venv):
        return f"pyright measured {root}, not the wheel installed in {venv}"
    # A report with pyTypedPath set and the right root can still count zero
    # exported symbols - an empty package, or a broken import - in which case
    # the score is 100% of nothing, not a clean bill of health.
    counts = completeness.get("exportedSymbolCounts")
    if not isinstance(counts, dict):
        return "pyright wrote no exportedSymbolCounts, so the score cannot be checked"
    exported = sum(int(counts.get(key, 0)) for key in ("withKnownType", "withAmbiguousType", "withUnknownType"))
    if exported == 0:
        return "pyright counted zero exported symbols, so the score is vacuous"
    return None


def verdict(report: dict[str, object], fail_under: float) -> tuple[int, list[str]]:
    """The exit status for this report against the threshold, and the lines to print."""
    score = score_of(report)
    lines = [f"type completeness: {score:.2f}% (threshold {fail_under:.1f}%)"]
    lines += [f"  {line}" for line in incomplete_symbols(report)]
    if floored(score) < fail_under:
        lines.append(f"FAIL: type completeness {score:.2f}% is below {fail_under:.1f}%")
        return 1, lines
    lines.append("ok")
    return 0, lines


def _python_in(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def measure(wheel: Path, workdir: Path) -> dict[str, object]:
    """Install `wheel` and pyright into a venv under `workdir`, and return pyright's report."""
    venv = workdir / "venv"
    # the interpreter running this script, so the score is measured on the
    # Python the job pins (UV_PYTHON in CI) and not whatever uv would pick
    subprocess.run(["uv", "venv", "--quiet", "--python", sys.executable, str(venv)], check=True)
    python = _python_in(venv)
    subprocess.run(["uv", "pip", "install", "--quiet", "--python", str(python), str(wheel), PYRIGHT], check=True)
    # pyright exits 1 whenever the score is below 100%, so the exit status says
    # nothing; the JSON on stdout is the result
    completed = subprocess.run(
        [
            "uv",
            "--directory",
            str(workdir),
            "run",
            "--no-project",
            "--python",
            str(python),
            "pyright",
            "--verifytypes",
            PACKAGE,
            "--ignoreexternal",
            "--outputjson",
        ],
        capture_output=True,
        text=True,
    )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError:
        print(completed.stderr, file=sys.stderr)
        raise
    assert isinstance(report, dict)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wheel", help="the wheel to measure; a glob such as dist/*.whl is expanded")
    parser.add_argument("--fail-under", type=float, required=True, help="the lowest passing score, in percent")
    parser.add_argument("--report", type=Path, help="also write pyright's JSON report here")
    args = parser.parse_args(argv)

    wheels = sorted(glob.glob(args.wheel))
    if len(wheels) != 1:
        print(f"error: expected one wheel for {args.wheel!r}, found {wheels}", file=sys.stderr)
        return 2
    wheel = Path(wheels[0]).resolve()
    with tempfile.TemporaryDirectory() as scratch:
        workdir = Path(scratch).resolve()
        report = measure(wheel, workdir)
        problem = problem_with(report, workdir / "venv")
    if args.report is not None:
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if problem is not None:
        print(f"error: {problem}", file=sys.stderr)
        return 2
    status, lines = verdict(report, args.fail_under)
    print("\n".join(lines))
    return status


if __name__ == "__main__":
    sys.exit(main())
