"""The writes-land Visio-check cases build, and each file opens again."""

import importlib.util
import json
import sys
from pathlib import Path

from vsdxkit.document import Document

TOOL = Path(__file__).resolve().parent.parent / "tools" / "writes_land_cases.py"


def _tool():
    spec = importlib.util.spec_from_file_location("writes_land_cases", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["writes_land_cases"] = module
    spec.loader.exec_module(module)
    return module


def test_every_case_writes_a_file_that_opens(tmp_path):
    tool = _tool()

    assert tool.main([str(tmp_path)]) == 0

    files = sorted(tmp_path.glob("*.vsdx"))
    assert len(files) == len(tool.CASES)
    for path in files:
        Document.open(path)
    expected = (tmp_path / "EXPECTED.txt").read_text(encoding="utf-8").splitlines()
    assert len(expected) == len(tool.CASES)


def _payload(stem, cells, connects=()):
    return {"path": f"C:\\x\\{stem}.vsdx", "cells": list(cells), "connects": list(connects)}


def _cell(page, shape, cell, value, recalc):
    number = isinstance(value, float)
    return {
        "page": page,
        "shape": shape,
        "cell": cell,
        "exists": True,
        "formula": "",
        "result_iu": value if number else 0.0,
        "result_str": "" if number else value,
        "recalc_iu": recalc if number else 0.0,
        "recalc_str": "" if number else recalc,
    }


def test_judge_passes_a_value_visio_shows_on_open_and_after_recalculating():
    tool = _tool()
    expected = {"a": tool.Case("a", (tool.CellCheck(1, 3, "Width", 2.5), tool.CellCheck(1, 3, "LineColor", "RGB(255,0,0)")))}
    payload = [_payload("a", [_cell(1, 3, "Width", 2.5, 2.5), _cell(1, 3, "LineColor", "RGB(255, 0, 0)", "RGB(255, 0, 0)")])]

    assert tool.judge(expected, payload) == []


def test_judge_fails_a_value_a_stale_formula_replaces_on_recalculation():
    """Visio showed the written 2.5 on open, but the cell's GUARD(1) put 1 back: the write did not land."""
    tool = _tool()
    expected = {"a": tool.Case("a", (tool.CellCheck(1, 3, "Width", 2.5),))}
    payload = [_payload("a", [_cell(1, 3, "Width", 2.5, 1.0)])]

    [failure] = tool.judge(expected, payload)
    assert "Width" in failure and "1.0" in failure


def test_judge_fails_a_colour_a_theme_formula_replaces():
    tool = _tool()
    expected = {"a": tool.Case("a", (tool.CellCheck(1, 3, "LineColor", "RGB(255,0,0)"),))}
    payload = [_payload("a", [_cell(1, 3, "LineColor", "RGB(255, 0, 0)", "RGB(212, 159, 0)")])]

    assert len(tool.judge(expected, payload)) == 1


def test_judge_fails_glue_visio_still_holds():
    tool = _tool()
    expected = {"a": tool.Case("a", (), (tool.GlueCheck(1, 6, frozenset({("EndX", 2)})),))}
    connects = [
        {"page": 1, "from_shape": 6, "from_cell": "BeginX", "to_shape": 1, "to_cell": "PinX"},
        {"page": 1, "from_shape": 6, "from_cell": "EndX", "to_shape": 2, "to_cell": "PinX"},
    ]

    assert len(tool.judge(expected, [_payload("a", [], connects)])) == 1


def test_judge_fails_a_cell_visio_does_not_have_or_could_not_read():
    tool = _tool()
    expected = {"a": tool.Case("a", (tool.CellCheck(1, 3, "Width", 2.5), tool.CellCheck(1, 3, "Height", 1.0)))}
    missing = {"page": 1, "shape": 3, "cell": "Width", "exists": False}
    unreadable = {"page": 1, "shape": 3, "cell": "Height", "error": "no such shape"}

    assert len(tool.judge(expected, [_payload("a", [missing, unreadable])])) == 2


def test_judge_fails_a_case_visio_did_not_report():
    tool = _tool()
    expected = {"a": tool.Case("a", (tool.CellCheck(1, 3, "Width", 2.5),))}

    assert len(tool.judge(expected, [])) == 1


def test_judge_fails_closed_on_a_case_with_no_checks():
    """The check exists so a bad write can fail it; an empty case is one nothing Visio says can fail.

    The payload reports the file cleanly, with nothing wrong: an empty case
    must still fail on its own account, not merely inherit some other cause.
    """
    tool = _tool()
    expected = {"a": tool.Case("a", ())}

    [failure] = tool.judge(expected, [_payload("a", [])])
    assert "a" in failure


def test_judge_fails_every_check_when_visio_could_not_open_the_file():
    """A locked or corrupt file costs every check of its case, each line naming the error."""
    tool = _tool()
    expected = {"a": tool.Case("a", (tool.CellCheck(1, 3, "Width", 2.5),), (tool.GlueCheck(1, 6, frozenset({("EndX", 2)})),))}
    payload = [{"path": "C:\\x\\a.vsdx", "error": "the file is locked by another instance"}]

    failures = tool.judge(expected, payload)

    assert len(failures) == 2
    assert all("locked" in failure for failure in failures)


def test_judge_handles_a_single_document_collapsed_to_a_bare_dict():
    """ConvertTo-Json collapses a one-element array into a bare object; `_documents` undoes that."""
    tool = _tool()
    expected = {"a": tool.Case("a", (tool.CellCheck(1, 3, "Width", 2.5),))}
    payload = _payload("a", [_cell(1, 3, "Width", 2.5, 2.5)])

    assert tool.judge(expected, tool._documents(payload)) == []


def test_every_case_says_what_visio_must_show(tmp_path):
    """A case with no checks is a case the check cannot fail on."""
    tool = _tool()
    tool.main([str(tmp_path)])

    written = json.loads((tmp_path / "expected.json").read_text(encoding="utf-8"))

    assert len(written) == len(tool.CASES)
    assert all(case["cells"] or case["glue"] for case in written.values())
