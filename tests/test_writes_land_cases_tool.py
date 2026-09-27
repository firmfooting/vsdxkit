"""The writes-land Visio-check cases build, and each file opens again."""

import importlib.util
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
