"""`tools/check_api_documented.py` fails when an exported name is missing from the reference (#424).

The tool runs in CI's build job, after the wheel is measured and the docs are
built. These pin how it compares pyright's report with the inventory, so a
missing name fails, a private one is not asked for, and an empty report or
inventory cannot pass as "nothing missing".
"""

import importlib.util
import os
import zlib

import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "tools")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(TOOLS, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load("check_api_documented")


def _report(*symbols: tuple[str, bool]) -> dict:
    return {"typeCompleteness": {"symbols": [{"name": name, "isExported": exported} for name, exported in symbols]}}


def _inventory(*lines: str) -> bytes:
    header = (
        b"# Sphinx inventory version 2\n"
        b"# Project: vsdxkit\n"
        b"# Version: 0\n"
        b"# The remainder of this file is compressed using zlib.\n"
    )
    return header + zlib.compress("".join(f"{line}\n" for line in lines).encode())


def test_every_exported_name_documented_passes():
    status, lines = tool.verdict({"vsdxkit.document.Document"}, {"vsdxkit.document.Document", "vsdxkit.document"})
    assert status == 0
    assert lines == ["ok: all 1 exported public names are in the API reference"]


def test_an_exported_name_missing_from_the_reference_fails():
    status, lines = tool.verdict({"vsdxkit.shapes.Shape.xml", "vsdxkit.shapes.Shape"}, {"vsdxkit.shapes.Shape"})
    assert status == 1
    assert lines == [
        "FAIL: vsdxkit.shapes.Shape.xml is exported but not in the API reference",
        "1 exported name(s) undocumented",
    ]


def test_an_empty_report_cannot_pass():
    status, lines = tool.verdict(set(), {"vsdxkit.document.Document"})
    assert status == 2
    assert lines == ["error: the report exports no public name, so there is nothing to check"]


def test_an_empty_inventory_cannot_pass():
    status, lines = tool.verdict({"vsdxkit.document.Document"}, set())
    assert status == 2
    assert lines == ["error: the inventory documents no Python name, so the docs build measured nothing"]


def test_only_public_exported_names_are_asked_for():
    report = _report(
        ("vsdxkit.document.Document", True),
        ("vsdxkit.document.Document.__init__", True),
        ("vsdxkit._xmlio.PartTree", True),
        ("vsdxkit.shapes._PageSeam", True),
        ("vsdxkit.document.helper", False),
    )
    assert tool.exported_names(report) == {"vsdxkit.document.Document"}


def test_a_report_without_symbols_exports_nothing():
    assert tool.exported_names({}) == set()
    assert tool.exported_names({"typeCompleteness": {}}) == set()


def test_the_inventory_gives_every_python_name_and_nothing_else():
    pytest.importorskip("sphinx", reason="sphinx is in the docs group; CI's build job has it")
    inventory = _inventory(
        "vsdxkit.shapes py:module 0 api/vsdxkit/shapes/index.html#module-$ -",
        "vsdxkit.shapes.Shape py:class 1 api/vsdxkit/shapes/index.html#$ -",
        "vsdxkit.shapes.Shape.xml py:property 1 api/vsdxkit/shapes/index.html#$ -",
        "quickstart std:doc -1 quickstart.html Quickstart",
    )
    assert tool.documented_names(inventory) == {"vsdxkit.shapes", "vsdxkit.shapes.Shape", "vsdxkit.shapes.Shape.xml"}
