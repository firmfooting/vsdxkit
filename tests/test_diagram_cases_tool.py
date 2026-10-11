"""The diagram cases the Visio harness checks build, open again, and ask Visio about every shape."""

import importlib.util
import json
import sys
from pathlib import Path

from vsdxkit.document import Document

TOOL = Path(__file__).resolve().parent.parent / "tools" / "diagram_cases.py"


def _tool():
    spec = importlib.util.spec_from_file_location("diagram_cases", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["diagram_cases"] = module
    spec.loader.exec_module(module)
    return module


def test_every_case_writes_a_file_that_opens_and_is_asked_about_in_full(tmp_path):
    assert _tool().main([str(tmp_path)]) == 0

    expected = json.loads((tmp_path / "expected.json").read_text(encoding="utf-8"))
    assert {"copy_style_absent", "copy_style_clash"} <= set(expected)
    for stem, data in expected.items():
        document = Document.open(tmp_path / f"{stem}.vsdx")
        shapes = sum(len(page.shapes) for page in document.pages)
        asked = {(page, shape) for page, shape, _cell, _want in data["cells"]}
        assert len(asked) == shapes, f"{stem} asks about {len(asked)} of its {shapes} shapes"


def test_a_case_builds_the_same_bytes_every_time(tmp_path):
    tool = _tool()
    first, second = tmp_path / "a", tmp_path / "b"
    tool.main([str(first)])
    tool.main([str(second)])
    for path in sorted(first.glob("*.vsdx")):
        assert path.read_bytes() == (second / path.name).read_bytes()
