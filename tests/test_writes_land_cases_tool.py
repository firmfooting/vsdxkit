"""The writes-land Visio-check cases build, and each file opens again."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from vsdxkit.document import Document

TOOL = Path(__file__).resolve().parent.parent / "tools" / "writes_land_cases.py"


def _tool():
    spec = importlib.util.spec_from_file_location("writes_land_cases", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["writes_land_cases"] = module
    spec.loader.exec_module(module)
    return module


def _case_files(out: Path) -> list[Path]:
    """The case files in `out`, leaving out each one's `.before` baseline."""
    return sorted(path for path in out.glob("*.vsdx") if not path.name.endswith(".before.vsdx"))


_FROM_TEST5_MASTER = ("05_plain_line_text.vsdx", "05_plain_line_text.before.vsdx")
"""The files the tool writes from `test5_master.vsdx`, a case and its `.before` baseline; see `test_every_case_writes_a_file_that_opens`."""


@pytest.mark.allow_invalid_package("missing-part", files=_FROM_TEST5_MASTER)
def test_every_case_writes_a_file_that_opens(tmp_path):
    """`05_plain_line_text.vsdx` comes from `test5_master.vsdx`, which ships with seven `missing-part`
    defects of its own (KNOWN_NON_CONFORMANT in test_package_validator.py); conftest's provenance
    match goes by filename, and case 5 is named for the brief, not for its fixture, so the known
    defects need excusing here rather than being mistaken for ones this test introduced, as they
    do in its `.before` baseline, the fixture copied untouched. `files` keeps the exemption to
    those files, so a real `missing-part` regression in any other case would still be seen.
    """
    tool = _tool()

    assert tool.main([str(tmp_path)]) == 0

    files = _case_files(tmp_path)
    assert len(files) == len(tool.CASES)
    for path in files:
        Document.open(path)
        Document.open(path.with_name(f"{path.stem}.before.vsdx"))
    header, blank, *lines = (tmp_path / "EXPECTED.txt").read_text(encoding="utf-8").splitlines()
    assert ".before.vsdx" in header and "baseline" in header
    assert blank == ""
    assert len(lines) == len(tool.CASES)


def test_a_case_s_before_file_is_its_fixture_untouched(tmp_path):
    tool = _tool()

    tool.colours(tmp_path)

    fixture = TOOL.parent.parent / "tests" / "fixtures" / "com_reference" / "s05_swimlanes_cfflow.vsdx"
    assert (tmp_path / "01_colours.before.vsdx").read_bytes() == fixture.read_bytes()
    assert (tmp_path / "01_colours.vsdx").read_bytes() != fixture.read_bytes()


@pytest.mark.allow_invalid_package("missing-part", files=_FROM_TEST5_MASTER)
def test_check_sends_visio_only_the_cases_and_judges_only_them(tmp_path, monkeypatch):
    """The `.before` files sit in the same folder, but they are baselines for a person, not writes to check."""
    tool = _tool()
    tool.main([str(tmp_path)])
    expected = json.loads((tmp_path / "expected.json").read_text(encoding="utf-8"))
    asked = {}

    def ask_visio(_tools_dir, paths, cases, _visio_verify):
        asked["paths"], asked["stems"] = paths, list(cases)
        return []

    monkeypatch.setattr(tool, "_ask_visio", ask_visio)

    assert tool._check(tmp_path) == 1  # Visio reported nothing, so every case fails

    assert asked["stems"] == list(expected)
    assert [Path(path).name for path in asked["paths"]] == [f"{stem}.vsdx" for stem in expected]
    assert not any(".before" in stem for stem in expected)


@pytest.mark.allow_invalid_package("missing-part", files=_FROM_TEST5_MASTER)
def test_the_cases_are_in_file_name_order(tmp_path):
    """Also writes `05_plain_line_text.vsdx`; see the marker's rationale on `test_every_case_writes_a_file_that_opens`."""
    tool = _tool()
    tool.main([str(tmp_path)])

    stems = list(json.loads((tmp_path / "expected.json").read_text(encoding="utf-8")))

    assert stems == sorted(stems)
    assert stems == [path.stem for path in _case_files(tmp_path)]


def test_the_prop_over_formula_case_writes_the_value_without_the_formula(tmp_path):
    tool = _tool()
    tool.prop_over_formula(tmp_path)

    prop = Document.open(tmp_path / "02b_prop_over_formula.vsdx").pages[0].shapes.require_id("54").data_properties["Function"]

    assert prop.value == "Sales"
    assert prop.get_attribute("Value", "F") is None


def test_the_instance_geometry_case_writes_the_instance_and_leaves_the_master(tmp_path):
    """What 02c asks Visio to confirm, checked in the file: the copy still reads the master's X of 0."""
    tool = _tool()
    case = tool.instance_geometry(tmp_path)

    page = Document.open(tmp_path / "02c_instance_geometry.vsdx").pages[0]
    written, sibling = (page.shapes.require_id(str(check.shape)) for check in case.cells)

    assert (written.geometry.rows["1"].x, written.geometry.rows["1"].inherited) == (0.25, False)
    assert (sibling.geometry.rows["1"].x, sibling.geometry.rows["1"].inherited) == (0.0, True)
    assert written.master_shape.geometry.rows["1"].cells["X"].value == "0"


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


@pytest.mark.allow_invalid_package("missing-part", files=_FROM_TEST5_MASTER)
def test_every_case_says_what_visio_must_show(tmp_path):
    """A case with no checks is a case the check cannot fail on.

    Also writes `05_plain_line_text.vsdx`; see the marker's rationale on
    `test_every_case_writes_a_file_that_opens`.
    """
    tool = _tool()
    tool.main([str(tmp_path)])

    written = json.loads((tmp_path / "expected.json").read_text(encoding="utf-8"))

    assert len(written) == len(tool.CASES)
    assert all(case["cells"] or case["glue"] for case in written.values())
