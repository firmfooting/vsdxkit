"""Run the Python examples of docs/diagrams_as_code.rst and docs/swimlanes.rst's creation example, in order, in one namespace."""

import re
import textwrap
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs"
_BLOCK = re.compile(r"^\.\. code-block:: python\n\n((?:   .*\n|\n)+)", re.MULTILINE)


def _blocks(page: str) -> list[str]:
    return [textwrap.dedent(block) for block in _BLOCK.findall((DOCS / page).read_text(encoding="utf-8"))]


@pytest.mark.parametrize(("page", "count"), [("diagrams_as_code.rst", 3), ("swimlanes.rst", 4)])
def test_the_pages_have_the_examples_this_file_runs(page, count):
    assert len(_blocks(page)) >= count


def test_the_diagram_examples_run_and_the_files_they_write_open(tmp_path, monkeypatch):
    from vsdxkit.document import Document

    monkeypatch.chdir(tmp_path)
    namespace: dict[str, object] = {}
    for block in _blocks("diagrams_as_code.rst"):
        exec(block, namespace)
    document = Document.open(tmp_path / "intake.vsdx")
    assert [page.name for page in document.pages] == ["Intake"]
    assert document.pages[0].swimlanes is not None
    assert [page.name for page in Document.open(tmp_path / "handoff.vsdx").pages] == ["Intake", "Review"]


def test_the_swimlane_creation_example_runs(tmp_path, monkeypatch):
    from vsdxkit.document import Document

    monkeypatch.chdir(tmp_path)
    block = next(b for b in _blocks("swimlanes.rst") if "create_swimlanes" in b)
    exec(block, {})
    assert len(Document.open(tmp_path / "lanes.vsdx").pages[0].require_swimlanes().lanes) == 2
