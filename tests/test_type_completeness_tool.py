"""`tools/check_type_completeness.py` reads pyright's report and refuses one that measured the wrong thing (#117).

The tool itself runs in CI's build job, against the wheel. These pin how it
reads a report, so a pyright report that measured nothing, or measured the
source tree, cannot pass as a score.
"""

import importlib.util
import os
from pathlib import Path

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "tools")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(TOOLS, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load("check_type_completeness")


def _report(
    root: str,
    score: float,
    symbols: list[dict] | None = None,
    py_typed: str | None = "py.typed",
    exported_symbol_counts: dict[str, int] | None = None,
) -> dict:
    return {
        "typeCompleteness": {
            "packageRootDirectory": root,
            "pyTypedPath": py_typed,
            "completenessScore": score,
            "symbols": symbols or [],
            # pyright's real shape (confirmed against a report built from a
            # fresh wheel): a non-zero default so tests aimed at the other
            # checks in `problem_with` do not trip this one too.
            "exportedSymbolCounts": exported_symbol_counts
            or {"withKnownType": 1, "withAmbiguousType": 0, "withUnknownType": 0},
        }
    }


def _symbol(name: str, *, known: bool, ambiguous: bool = False, exported: bool = True, message: str = "") -> dict:
    diagnostics = [{"message": message}] if message else []
    return {
        "name": name,
        "isExported": exported,
        "isTypeKnown": known,
        "isTypeAmbiguous": ambiguous,
        "diagnostics": diagnostics,
    }


def test_a_score_at_the_threshold_passes():
    status, lines = tool.verdict(_report("/v/site-packages/vsdxkit", 0.955), fail_under=95.5)
    assert status == 0
    assert lines[0] == "type completeness: 95.50% (threshold 95.5%)"


def test_a_score_below_the_threshold_fails_and_names_what_is_unknown():
    symbols = [
        _symbol("vsdxkit.pages.Page", known=False),
        _symbol(
            "vsdxkit.shapes.logger",
            known=False,
            ambiguous=True,
            message='Type is missing type annotation\n  Inferred type is "Logger"',
        ),
        _symbol("vsdxkit.shapes.Shape", known=True),
        _symbol("vsdxkit.pages._private", known=False, exported=False),
    ]
    status, lines = tool.verdict(_report("/v/site-packages/vsdxkit", 0.94, symbols), fail_under=95.0)
    assert status == 1
    assert "  vsdxkit.pages.Page (unknown)" in lines
    assert "  vsdxkit.shapes.logger (ambiguous): Type is missing type annotation" in lines
    assert not any("Shape (" in line or "_private" in line for line in lines)
    assert lines[-1] == "FAIL: type completeness 94.00% is below 95.0%"


def test_the_threshold_compares_the_floored_score():
    """95.49% is not 95.5%: the threshold is stated to one decimal place, rounded down."""
    assert tool.floored(95.49) == 95.4
    status, _ = tool.verdict(_report("/v/site-packages/vsdxkit", 0.9549), fail_under=95.5)
    assert status == 1


def test_a_report_that_found_no_py_typed_is_refused(tmp_path):
    venv = tmp_path / "venv"
    report = _report(str(venv / "site-packages" / "vsdxkit"), 0.0, py_typed=None)
    assert tool.problem_with(report, venv) == "pyright found no py.typed, so it measured nothing"


def test_a_report_on_the_source_tree_is_refused(tmp_path):
    """pyright run from the repository measures `src/`, which is not what ships."""
    venv = tmp_path / "venv"
    report = _report(str(Path("repo") / "src" / "vsdxkit"), 1.0)
    problem = tool.problem_with(report, venv)
    assert problem is not None and "not the wheel installed in" in problem


def test_a_report_on_the_installed_wheel_is_accepted(tmp_path):
    venv = tmp_path / "venv"
    report = _report(str(venv / "lib" / "python3.12" / "site-packages" / "vsdxkit"), 1.0)
    assert tool.problem_with(report, venv) is None


def test_a_report_with_zero_exported_symbols_is_refused(tmp_path):
    """A wheel with a good py.typed path and root still scores a vacuous 100% if nothing is exported."""
    venv = tmp_path / "venv"
    report = _report(
        str(venv / "lib" / "python3.12" / "site-packages" / "vsdxkit"),
        1.0,
        exported_symbol_counts={"withKnownType": 0, "withAmbiguousType": 0, "withUnknownType": 0},
    )
    assert tool.problem_with(report, venv) == "pyright counted zero exported symbols, so the score is vacuous"
