"""Run the README's Python examples, in order, against real files.

A README is documentation that claims to be executable, and the claim decays
silently: an API changes, the example keeps its syntax highlighting, and the
first person to find out is someone following it. Nothing else in this suite
reads the README, so nothing else can notice.

The examples are run in one shared namespace and in document order, because
that is how a reader meets them - two of them continue from a variable an
earlier block defined, and running them in isolation would test something the
reader never does.
"""

import os
import re
import shutil
import zipfile

import pytest

import vsdx

README = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "README.md")

# The examples name files a reader would have. `test1.vsdx` carries the "Shape
# to remove" text the first example looks up by name, and the swimlane example
# needs a genuine Visio cross-functional flowchart, which only the COM reference
# corpus has. The template is a copy that the fixture below writes into, for the
# reason given there.
FILES_THE_EXAMPLES_NAME = {
    "diagram.vsdx": "test1.vsdx",
    "cross-functional-flow.vsdx": "fixtures/com_reference/s05_swimlanes_cfflow.vsdx",
    "template.vsdx": "test1.vsdx",
}

_PYTHON_BLOCK = re.compile(r"^```python\n(.*?)^```", re.MULTILINE | re.DOTALL)

# Pinned exactly; see test_the_readme_has_the_examples_this_file_checks.
EXAMPLES_IN_THE_README = 6


def python_blocks(markdown: str) -> list[str]:
    return _PYTHON_BLOCK.findall(markdown)


@pytest.fixture
def readme_workspace(tmp_path, basedir):
    """A directory holding the files the README's examples open by name."""
    for named, fixture in FILES_THE_EXAMPLES_NAME.items():
        shutil.copy(os.path.join(basedir, fixture), tmp_path / named)

    # The templating example renders a context of its own choosing, so the
    # template has to ask for those names. Taking an existing Jinja fixture
    # instead would fail on a variable the README never mentions, which says
    # nothing about whether the example works.
    template = str(tmp_path / "template.vsdx")
    with vsdx.VisioFile(template) as document:
        shape = document.pages[0].child_shapes[0]
        shape.text = "{{ project }} for {{ owner }}"
        document.save_vsdx(template)
    return tmp_path


def test_the_readme_has_the_examples_this_file_checks():
    """An exact count, because a block that stops being extracted is invisible.

    The fence has to be ``` followed by `python` at column 0; re-fence a block
    as ```py, or indent it inside a list, and it silently leaves the corpus
    while every assertion below still passes. The number is a fact about the
    README and should only change on purpose.
    """
    assert len(python_blocks(_readme())) == EXAMPLES_IN_THE_README


def test_every_readme_example_runs(readme_workspace, monkeypatch):
    """The examples still work against the library as it is today.

    Failure here means the README is wrong, not that the test is: the examples
    are the contract a new user is handed.
    """
    monkeypatch.chdir(readme_workspace)
    _run(python_blocks(_readme()))


def test_every_readme_example_does_what_it_says(readme_workspace, monkeypatch):
    """The examples have the effect the prose around them promises.

    Running them and catching exceptions is a weaker gate than it looks. Python
    lets any attribute be assigned to anything, so a reader's typo - writing
    `shape.txet` for `shape.text` - raises nothing and changes nothing, and a
    test watching only for exceptions calls that example fine.

    Each assertion below is aimed at the sentence the README puts next to the
    example, and at the thing that would still be true if the call were deleted.
    Checking that a shape named "Store" exists in the re-anchored file, for
    instance, proves nothing: the example creates it two lines earlier. What has
    to be checked is that a connector now ends on it.
    """
    monkeypatch.chdir(readme_workspace)
    _run(python_blocks(_readme()))

    assert "Renamed shape" in _texts(readme_workspace / "edited.vsdx"), "the editing example promises a renamed shape"
    assert _page_names(readme_workspace / "diagram.vsdx")[0] == "Current state", (
        "the in-place save example promises the source file's first page is renamed"
    )
    assert "Do the thing" in _texts(readme_workspace / "flow.vsdx"), (
        "the shape-creation example promises the shapes it creates"
    )
    assert _connector_count(readme_workspace / "flow.vsdx") == 2, (
        "the section is called 'Create shapes and connectors' and draws two of them"
    )
    assert _is_glued_to(readme_workspace / "reanchored.vsdx", "Store"), (
        "the re-anchor example promises a connector moved onto the new shape"
    )
    assert "Review" in _texts(readme_workspace / "with-review-lane.vsdx"), (
        "the swimlane example promises a lane with that heading"
    )
    assert "Check" in _texts(readme_workspace / "with-review-lane.vsdx"), (
        "the swimlane example promises the shape it adds to the lane"
    )


def _texts(path) -> set[str]:
    """Every shape's text, exactly, so a longer string does not match a shorter."""
    with vsdx.VisioFile(str(path)) as document:
        return {shape.text.strip() for page in document.pages for shape in page.all_shapes}


def _page_names(path) -> list[str]:
    with vsdx.VisioFile(str(path)) as document:
        return [page.name for page in document.pages]


def _connector_count(path) -> int:
    """Connectors, counted by the shapes that own glue rather than by records.

    Each connector contributes a record per glued end, so counting records
    reports two for one connector and invites an off-by-one in the test rather
    than in the code.
    """
    with vsdx.VisioFile(str(path)) as document:
        page = document.pages[0]
        return len({record.from_id for record in page.connects})


def _is_glued_to(path, text: str) -> bool:
    with vsdx.VisioFile(str(path)) as document:
        page = document.pages[0]
        target = page.find_shape_by_text(text)
        if target is None:
            return False
        return any(record.to_id == str(target.ID) for record in page.connects)


def _readme() -> str:
    with open(README, encoding="utf-8") as handle:
        return handle.read()


def _run(blocks: list[str]) -> None:
    """Execute the examples in one namespace, in the order a reader meets them."""
    shared: dict = {}
    for number, block in enumerate(blocks, start=1):
        try:
            exec(compile(block, f"README.md block {number}", "exec"), shared)
        except Exception as error:
            raise AssertionError(f"README example {number} failed with {type(error).__name__}: {error}\n\n{block}") from error


def _connect_records(path) -> list[str]:
    """The `<Connect>` records on the package's pages."""
    return re.findall(r"<Connect\b[^>]*>", _text_of(path))


def _text_of(path) -> str:
    """Every scrap of text the package's pages carry, as one string."""
    with zipfile.ZipFile(path) as archive:
        pages = [name for name in archive.namelist() if name.startswith("visio/pages/page")]
        return " ".join(archive.read(name).decode("utf-8", "replace") for name in pages)
