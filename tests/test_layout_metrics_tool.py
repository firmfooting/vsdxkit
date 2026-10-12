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
    assert "hub5" in json.loads(capsys.readouterr().out)
