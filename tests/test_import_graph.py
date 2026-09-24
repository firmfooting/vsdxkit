"""Every import in the package points down, and none is hidden.

The 1.0 design (amended 2026-09-23) keeps one direction between modules: a
lower module never imports an upper one. Where a lower module needs an upper
object, it declares a `Protocol` that the upper class satisfies. This test
reads every `import` in `src/vsdxkit` with `ast` and fails:

- on a cycle among the imports;
- on an import that reaches a sibling module through the package root, either
  `from vsdxkit import <module>` or `vsdxkit.<module>` after `import vsdxkit`,
  which hides the edge from a reader;
- on a `vsdxkit` import under `if TYPE_CHECKING:`, which is an upward edge a
  type checker sees and the runtime does not;
- on an import inside a function, which is how a cycle is hidden.

`ALLOWED` lists the edges that break these rules today. The check fails both
ways, so the list only shrinks.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

SOURCE = Path(__file__).resolve().parents[1] / "src" / "vsdxkit"
PACKAGE = "vsdxkit"


class Edge(NamedTuple):
    importer: str
    imported: str
    # "module", "typing" (under TYPE_CHECKING), "function", or "root": the
    # import reached the module through the package root
    how: str


ALLOWED = {
    # 6b, the donors: media is reached through the document, not imported
    Edge("connectors", "media", "function"),
    Edge("connectors", "media", "root"),
    Edge("pages", "media", "function"),
    Edge("pages", "media", "root"),
    # 6b: each module imports its siblings by their own names
    Edge("document", "relationships", "root"),
    Edge("document", "xmlio", "root"),
    Edge("masters", "relationships", "root"),
    Edge("pages", "relationships", "root"),
    # 6c, the seams: each upward edge becomes a Protocol in the lower module
    Edge("connectors", "pages", "typing"),
    Edge("connectors", "shapes", "typing"),
    Edge("pages", "document", "typing"),
    Edge("shapes", "pages", "typing"),
    Edge("swimlanes", "pages", "typing"),
}


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _imports(tree: ast.Module) -> Iterator[tuple[ast.Import | ast.ImportFrom, str]]:
    """Each import statement, and where it sits: "module", "typing" or "function"."""

    def walk(nodes: list[ast.stmt], where: str) -> Iterator[tuple[ast.Import | ast.ImportFrom, str]]:
        for node in nodes:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                yield node, where
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield from walk(node.body, "function")
            elif isinstance(node, ast.If) and _is_type_checking(node.test):
                yield from walk(node.body, "typing" if where == "module" else where)
                yield from walk(node.orelse, where)
            else:
                for field in ("body", "orelse", "finalbody"):
                    yield from walk(getattr(node, field, []), where)
                for handler in getattr(node, "handlers", []):
                    yield from walk(handler.body, where)

    yield from walk(tree.body, "module")


def edges_of(importer: str, source: str, modules: set[str]) -> Iterator[Edge]:
    """The package-internal imports in one module's source.

    An import through the root yields two edges: the dependency itself, and a
    "root" edge that records how it was reached.
    """
    tree = ast.parse(source)
    root_names: set[str] = set()
    for node, where in _imports(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == PACKAGE:
                    root_names.add(alias.asname or PACKAGE)
                elif alias.name.startswith(f"{PACKAGE}."):
                    yield Edge(importer, alias.name.split(".")[1], where)
        elif node.level == 0 and node.module == PACKAGE:
            for alias in node.names:
                if alias.name in modules:
                    yield Edge(importer, alias.name, where)
                    yield Edge(importer, alias.name, "root")
        elif node.level == 0 and node.module is not None and node.module.startswith(f"{PACKAGE}."):
            yield Edge(importer, node.module.split(".")[1], where)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in root_names
            and node.attr in modules
        ):
            yield Edge(importer, node.attr, "module")
            yield Edge(importer, node.attr, "root")


def package_edges() -> set[Edge]:
    modules = {path.stem for path in SOURCE.glob("*.py") if path.stem != "__init__"}
    edges: set[Edge] = set()
    for module in sorted(modules):
        source = (SOURCE / f"{module}.py").read_text(encoding="utf-8")
        edges.update(edge for edge in edges_of(module, source, modules) if edge.imported != module)
    return edges


def violations(edges: set[Edge]) -> set[Edge]:
    return {edge for edge in edges if edge.how != "module"}


def cycle(edges: set[Edge]) -> list[str] | None:
    """One cycle among the edges, as a path that starts and ends on the same module, or None."""
    graph: dict[str, set[str]] = {}
    for edge in edges:
        if edge.how != "root":
            graph.setdefault(edge.importer, set()).add(edge.imported)
    done: set[str] = set()
    path: list[str] = []

    def visit(module: str) -> list[str] | None:
        if module in path:
            return [*path[path.index(module) :], module]
        if module in done:
            return None
        path.append(module)
        for imported in sorted(graph.get(module, ())):
            found = visit(imported)
            if found:
                return found
        path.pop()
        done.add(module)
        return None

    for module in sorted(graph):
        found = visit(module)
        if found:
            return found
    return None


def test_every_import_points_down_in_plain_sight():
    found = violations(package_edges())
    assert found - ALLOWED == set(), "imports that hide an edge or point up"
    assert ALLOWED - found == set(), "these are gone: remove them from ALLOWED"


def test_the_imports_form_no_cycle():
    """Every edge counts, whether typing-only or inside a function, except those still ALLOWED."""
    assert cycle(package_edges() - ALLOWED) is None


# the checker's own cases, on made-up modules

MODULES = {"alpha", "beta", "gamma"}


def test_a_type_checking_import_is_a_typing_edge():
    source = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from vsdxkit.beta import B\n"
    assert set(edges_of("alpha", source, MODULES)) == {Edge("alpha", "beta", "typing")}


def test_an_import_inside_a_function_is_a_function_edge():
    source = "class A:\n    def f(self):\n        from vsdxkit.beta import B\n        return B\n"
    assert set(edges_of("alpha", source, MODULES)) == {Edge("alpha", "beta", "function")}


def test_a_sibling_imported_from_the_root_is_a_root_edge():
    source = "from vsdxkit import beta, namespace\n"
    assert set(edges_of("alpha", source, MODULES)) == {Edge("alpha", "beta", "module"), Edge("alpha", "beta", "root")}


def test_a_sibling_reached_through_import_vsdxkit_is_a_root_edge():
    source = "import vsdxkit\nvalue = vsdxkit.beta.B\nprefix = vsdxkit.namespace\n"
    assert set(edges_of("alpha", source, MODULES)) == {Edge("alpha", "beta", "module"), Edge("alpha", "beta", "root")}


def test_a_cycle_through_every_kind_of_edge_is_found():
    edges = {Edge("alpha", "beta", "module"), Edge("beta", "gamma", "function"), Edge("gamma", "alpha", "typing")}
    assert cycle(edges) == ["alpha", "beta", "gamma", "alpha"]


def test_a_chain_is_not_a_cycle():
    assert cycle({Edge("alpha", "beta", "module"), Edge("beta", "gamma", "module")}) is None
