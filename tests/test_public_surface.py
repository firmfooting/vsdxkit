"""The 1.0 surface is decided: a name is user API on purpose, or it starts with an underscore (#424).

Private by default (Phase 7, decision 1). A module that is internal throughout
is renamed with a leading underscore, a public module's internals are
underscored in place or moved to an underscored module, and a dead name is
deleted. Each test here fails if one of those names comes back public, or if a
page a user reads still sends them to one.
"""

import ast
import importlib.util
import inspect
import re
from pathlib import Path

import pytest

import vsdxkit.document
import vsdxkit.geometry
import vsdxkit.pages
import vsdxkit.shapes
import vsdxkit.swimlanes
import vsdxkit.templating
from vsdxkit.geometry import GeometryCell, GeometryRow
from vsdxkit.shapes import DataProperty

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "vsdxkit"

# modules internal throughout, each renamed with a leading underscore
PRIVATE_MODULES = (
    "formulae",
    "inheritance",
    "logging_support",
    "masters",
    "media",
    "shape_part",
    "partnames",
    "relationships",
    "shape_tree",
    "xmlio",
    "connectors",
)

# a renamed module under its old name, or any dotted segment with one leading
# underscore; a dunder such as `__version__` is public
PRIVATE_REFERENCE = re.compile(rf"\bvsdxkit\.(?:(?:{'|'.join(PRIVATE_MODULES)})\b|(?:\w+\.)*_(?!_))")


def private_references(text: str) -> list[tuple[int, str]]:
    """Each line of `text` that names a private module or name, with its line number."""
    return [(number, line.strip()) for number, line in enumerate(text.splitlines(), start=1) if PRIVATE_REFERENCE.search(line)]


def _top_level_names(module: str) -> set[str]:
    """The names a module's own source binds at its top level, not the ones it imports."""
    names = set()
    for node in ast.parse((SOURCE / f"{module}.py").read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names |= {target.id for target in node.targets if isinstance(target, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _has(owner: object, name: str) -> bool:
    """Whether `owner` has `name`, as an attribute or as an annotation-only class member."""
    return hasattr(owner, name) or (inspect.isclass(owner) and name in inspect.get_annotations(owner))


@pytest.mark.parametrize("module", PRIVATE_MODULES)
def test_an_internal_module_is_private(module):
    """Fails if an internal module resolves under its public name again, or its private one is gone.

    For ``media`` this also covers the bundled-donor folder: were it still
    ``src/vsdxkit/media/``, ``vsdxkit.media`` would resolve as an empty
    namespace package.
    """
    assert importlib.util.find_spec(f"vsdxkit.{module}") is None
    assert importlib.util.find_spec(f"vsdxkit._{module}") is not None


@pytest.mark.parametrize(
    "line",
    [
        "from vsdxkit.formulae import calc_value",
        "``vsdxkit._formulae.func_map``",
        ":func:`vsdxkit.media.media_path`",
        "import vsdxkit.masters",
        "see vsdxkit.shapes._PageSeam",
    ],
)
def test_a_private_reference_is_found(line):
    assert private_references(f"Intro.\n{line}\n") == [(2, line)]


@pytest.mark.parametrize(
    "line",
    [
        "from vsdxkit.shapes import Shape",
        "``vsdx.formulae.calc_value``",
        ":class:`vsdxkit.shape_kind.ShapeKind`",
        "``vsdxkit.media_extra``",
        "vsdxkit.__version__",
    ],
)
def test_a_public_reference_is_not_found(line):
    assert private_references(line) == []


def test_no_page_a_user_reads_names_a_private_module_or_name():
    """Fails if the README or a docs page sends a reader to a private module or name.

    The migration guide is searched too: it spells each 0.8.0 name
    ``vsdx.<module>``, so a match there is something 1.0 recommends. The sdist
    carries the README and the guide, and not the other pages.
    """
    pages = [page for page in (ROOT / "README.md", *sorted((ROOT / "docs").glob("*.rst"))) if page.exists()]
    assert pages, "no README.md and no docs/*.rst beside the tests"
    found = [
        f"{page.relative_to(ROOT)}:{number}: {line}"
        for page in pages
        for number, line in private_references(page.read_text(encoding="utf-8"))
    ]
    assert found == []


@pytest.mark.parametrize(
    ("module", "public"),
    [("package", {"PackageLimits"}), ("glue", {"ConnectorOptions", "Glue", "Routing"})],
)
def test_a_split_module_defines_only_its_user_api(module, public):
    """Fails if the store, or the glue planners and records, move back beside the names users import."""
    assert {name for name in _top_level_names(module) if not name.startswith("_")} == public
    assert importlib.util.find_spec(f"vsdxkit._{module}") is not None


def test_only_the_root_defines_the_visio_namespace():
    """Fails if a module keeps its own copy of `vsdxkit.namespace` again, as `connectors` and `geometry` did."""
    copies = sorted(
        path.name for path in SOURCE.glob("*.py") if path.name != "__init__.py" and "namespace" in _top_level_names(path.stem)
    )
    assert copies == []


@pytest.mark.parametrize(
    ("owner", "name"),
    [
        (vsdxkit.document, "logger"),
        (vsdxkit.geometry, "logger"),
        (vsdxkit.shapes, "logger"),
        (vsdxkit.templating, "logger"),
        (vsdxkit.geometry, "GeometryOwner"),
        (GeometryRow, "create_row_xml"),
        (GeometryRow, "inherited_by"),
        (GeometryCell, "create_cell_xml"),
        (GeometryCell, "parent_xml"),
        (DataProperty, "inherited_by"),
        (vsdxkit.shapes, "is_connector"),
        (vsdxkit.shapes, "substitute"),
        (vsdxkit.pages, "PageLifecycle"),
        (vsdxkit.swimlanes, "CONTAINER_NAME"),
        (vsdxkit.document, "DRAWING_CONTENT_TYPE"),
        (vsdxkit.document, "MACRO_ENABLED_CONTENT_TYPE"),
    ],
    ids=lambda value: getattr(value, "__name__", value),
)
def test_an_internal_name_in_a_public_module_is_private(owner, name):
    """Fails if an internal of a public module or class loses its leading underscore."""
    assert not _has(owner, name)
    assert _has(owner, f"_{name}")
