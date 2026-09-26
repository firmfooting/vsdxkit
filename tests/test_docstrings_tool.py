"""`tools/check_docstrings.py` finds every definition without documentation (#424).

The gate runs in the lint job over `src/vsdxkit`. These pin what it counts as
documented, so a blank docstring, a comment in place of a docstring, or a
definition the walk never reaches cannot pass.
"""

import importlib.util
import os
import sys
import textwrap
from pathlib import Path

import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "tools")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(TOOLS, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    # a dataclass looks its module up in sys.modules while it is built
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tool = _load("check_docstrings")


def _gaps(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "sample.py"
    path.write_text('"""A module."""\n\n' + textwrap.dedent(source), encoding="utf-8")
    return [f"{gap.kind} {gap.name}" for gap in tool.gaps_in(path)]


def test_a_documented_module_has_no_gaps(tmp_path):
    source = '''
        from typing import Protocol, overload

        LIMIT = 3
        """How many there may be."""


        class Seam(Protocol):
            """What a shape needs of its page."""

            name: str
            """The page's name."""

            def width(self) -> float:
                """The page's width, in inches."""
                ...


        class Thing:
            """A thing."""

            def __init__(self) -> None:
                """Make a thing with nothing in it."""

            @property
            def size(self) -> int:
                """How big it is."""
                return 1

            @size.setter
            def size(self, value: int) -> None:
                pass

            @overload
            def get(self, key: int) -> int: ...
            @overload
            def get(self, key: str) -> str: ...
            def get(self, key):
                """The value under `key`."""

                def inner():
                    """Nested, and documented."""

                return inner
        '''
    assert _gaps(tmp_path, source) == []


def test_a_module_without_a_docstring_is_a_gap(tmp_path):
    path = tmp_path / "bare.py"
    path.write_text("VALUE = 1\n", encoding="utf-8")
    assert [f"{gap.kind} {gap.name}" for gap in tool.gaps_in(path)] == ["module bare", "constant VALUE"]


@pytest.mark.parametrize(
    ("source", "gap"),
    [
        ("def run():\n    pass\n", "function run"),
        ('def run():\n    """"""\n', "function run"),
        ('def run():\n    """   """\n', "function run"),
        ("class Thing:\n    pass\n", "class Thing"),
        ('class Thing:\n    """A thing."""\n\n    def __repr__(self):\n        return ""\n', "method Thing.__repr__"),
        ('class Thing:\n    """A thing."""\n\n    def _private(self):\n        pass\n', "method Thing._private"),
        ('class Thing:\n    """A thing."""\n\n    @property\n    def size(self):\n        return 1\n', "property Thing.size"),
        (
            'from typing import override\n\nclass Thing:\n    """A thing."""\n\n    @override\n    def __str__(self):\n        return ""\n',
            "method Thing.__str__",
        ),
        ('def outer():\n    """Documented."""\n\n    def inner():\n        pass\n', "function outer.<locals>.inner"),
    ],
    ids=["no docstring", "empty", "blank", "class", "dunder", "private", "property", "override", "nested"],
)
def test_a_definition_without_a_docstring_is_a_gap(tmp_path, source, gap):
    assert _gaps(tmp_path, source) == [gap]


@pytest.mark.parametrize(
    ("source", "gap"),
    [
        ("LIMIT = 3\n", "constant LIMIT"),
        ("LIMIT = 3  # how many there may be\n", "constant LIMIT"),
        ("#: how many there may be\nLIMIT = 3\n", "constant LIMIT"),
        ('LIMIT = 3\n""""""\n', "constant LIMIT"),
        ("_logger: object = None\n", "constant _logger"),
        ('class Colour:\n    """A colour."""\n\n    RED = "red"\n', "attribute Colour.RED"),
        ('class Options:\n    """Options."""\n\n    size: int = 0\n', "attribute Options.size"),
        ('class Seam:\n    """A seam."""\n\n    name: str\n', "attribute Seam.name"),
    ],
    ids=["bare", "trailing comment", "sphinx comment", "empty string", "private", "enum member", "field", "protocol"],
)
def test_an_assignment_without_a_string_after_it_is_a_gap(tmp_path, source, gap):
    assert _gaps(tmp_path, source) == [gap]


def test_a_type_checking_block_is_exempt_and_its_else_branch_is_not(tmp_path):
    source = """
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            Tree = list[int]
        else:
            Tree = list
        """
    assert _gaps(tmp_path, source) == ["constant Tree"]


def test_the_gate_prints_file_line_kind_and_name(tmp_path, capsys):
    path = tmp_path / "sample.py"
    path.write_text('"""A module."""\n\nLIMIT = 3\n', encoding="utf-8")
    assert tool.main([str(path)]) == 1
    assert capsys.readouterr().out.splitlines() == [f"{path}:3 constant LIMIT", "1 definition(s) without documentation"]


def test_the_gate_passes_a_documented_module(tmp_path, capsys):
    path = tmp_path / "sample.py"
    path.write_text('"""A module."""\n', encoding="utf-8")
    assert tool.main([str(path)]) == 0
    assert capsys.readouterr().out == "ok: every definition in 1 module(s) is documented\n"
