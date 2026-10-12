"""The layout metrics tool measures every corpus entry and fails by name on a broken fixture."""

import importlib.util
import json
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent / "tools" / "layout_metrics.py"


def _tool():
    spec = importlib.util.spec_from_file_location("layout_metrics", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_corpus_entry_is_measured_with_every_column():
    rows = _tool().measure_all()
    assert set(rows) >= {"hub5", "chain25", "lanes3", "fanin", "rand-0"}
    assert set(rows["hub5"]) >= {"crossings", "aspect", "max_bends", "port_gap_violations", "seconds"}


def test_a_broken_fixture_fails_the_tool_by_name(monkeypatch):
    tool = _tool()

    def broken(stem):
        raise ImportError("hub5 is broken")

    monkeypatch.setattr(tool.corpus, "fixture_layout", broken)
    with pytest.raises(ImportError, match="hub5"):
        tool.measure_all()


def test_the_json_output_round_trips(capsys):
    assert _tool().main(["--json"]) == 0
    assert "hub5" in json.loads(capsys.readouterr().out)["metrics"]


def _rows(*names):
    return {n: {c: 1 for c in _tool().COLUMNS} for n in names}


@pytest.mark.parametrize("as_json", [False, True])
def test_every_mode_reports_every_case_and_every_metric(as_json):
    tool = _tool()
    metrics, dense = _rows("a", "b"), {"1-2-0-0-TB": {"seconds": 1.0, "outcome": "ok"}}
    out = tool.render(metrics, dense, None, as_json)
    if as_json:
        record = json.loads(out)
        assert record["metrics"] == metrics and record["dense"] == dense
    else:
        assert all(f"| {n} |" in out for n in metrics) and "1-2-0-0-TB" in out
        assert out.splitlines()[0].count("|") == len(tool.COLUMNS) + 2


def test_the_json_mode_keeps_the_dense_cells_when_asked(capsys, monkeypatch):
    tool = _tool()
    monkeypatch.setattr(tool, "measure_all", lambda: _rows("a"))
    monkeypatch.setattr(tool, "measure_dense", lambda: {"x": {"seconds": 1.0, "outcome": "ok"}})
    assert tool.main(["--json", "--dense"]) == 0
    assert json.loads(capsys.readouterr().out)["dense"] == {"x": {"seconds": 1.0, "outcome": "ok"}}


def test_a_case_or_metric_the_reference_lacks_is_marked_not_dropped():
    tool = _tool()
    now, before = _rows("a", "new"), _rows("a", "gone")
    del before["a"]["crossings"]
    table = tool._table(now, before)
    assert "| new | " + " | ".join("n/a -> 1" for _ in tool.COLUMNS) + " |" in table
    assert "| gone | " + " | ".join("1 -> n/a" for _ in tool.COLUMNS) + " |" in table
    assert "1 -> 1" not in table and "n/a -> 1" in table


def test_against_is_honoured_with_json(capsys, monkeypatch):
    tool = _tool()
    monkeypatch.setattr(tool, "measure_all", lambda: _rows("a"))
    monkeypatch.setattr(tool, "_reference", lambda ref: _rows("old"))
    assert tool.main(["--json", "--against", "v0"]) == 0
    assert json.loads(capsys.readouterr().out)["against"] == _rows("old")
