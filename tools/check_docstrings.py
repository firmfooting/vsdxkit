"""Fail on any definition in src/vsdxkit that has no documentation.

Every module, class, function, method and property needs a docstring that is
not blank. Every assignment or annotation in a module body or a class body
needs a string literal as the statement straight after it: that covers module
constants, class attributes, dataclass fields, Protocol members and enum
members. The string after is the form the generated reference renders:
sphinx-autoapi reads it, and reads no comment, ``#:`` included.

Private names, dunder methods, nested functions and ``@override`` methods are
not exempt: a docstring is for the next reader of the code as much as for the
reference. Exempt:

- a property's setter and deleter, which share the getter's docstring;
- an ``@overload`` stub, documented by the implementation after it;
- a name bound by ``import``;
- the body of an ``if TYPE_CHECKING:`` block, whose ``else:`` branch is checked.

Prints ``file:line kind name`` for each gap, and exits 1 if there is one.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

PACKAGE = Path("src") / "vsdxkit"
"""Where the modules live, relative to the repository root the gate runs from."""

Definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
"""A statement that defines a class or a function, and so needs a docstring."""


@dataclass(frozen=True)
class Gap:
    """One definition without documentation: where it is and what it is."""

    path: Path
    """The module the definition is in."""
    line: int
    """The line the definition starts on."""
    kind: str
    """``module``, ``class``, ``function``, ``method``, ``property``, ``constant`` or ``attribute``."""
    name: str
    """The definition's dotted name inside its module; ``<locals>`` marks a nested one."""

    def __str__(self) -> str:
        """The gap as ``file:line kind name``, a form an editor can jump to."""
        return f"{self.path}:{self.line} {self.kind} {self.name}"


def _decorator_names(node: Definition) -> set[str]:
    """The last dotted part of each decorator: ``property``, ``setter``, ``overload``, ..."""
    names = set()
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def _has_docstring(node: ast.Module | Definition) -> bool:
    """Whether `node` opens with a docstring that is not blank."""
    return bool((ast.get_docstring(node) or "").strip())


def _is_type_checking(node: ast.If) -> bool:
    """Whether `node` is ``if TYPE_CHECKING:`` or ``if typing.TYPE_CHECKING:``."""
    test = node.test
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _is_string(node: ast.stmt | None) -> bool:
    """Whether `node` is a bare string literal that is not blank."""
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Constant):
        return False
    return isinstance(node.value.value, str) and bool(node.value.value.strip())


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    """The plain names an assignment binds; an attribute or subscript target binds none.

    A ``type X = ...`` statement needs Python 3.12 and the package supports
    3.10, so ``src/vsdxkit`` holds none, and this module runs on 3.10 too.
    """
    if isinstance(node, ast.Assign):
        return [target.id for target in node.targets if isinstance(target, ast.Name)]
    return [node.target.id] if isinstance(node.target, ast.Name) else []


def _function_kind(decorators: set[str], in_class: bool) -> str:
    """``property``, ``method`` or ``function``: what a reader calls this ``def``."""
    if decorators & {"property", "cached_property"}:
        return "property"
    return "method" if in_class else "function"


def _nested_definitions(node: ast.AST) -> Iterator[Definition]:
    """The classes and functions defined inside `node`'s code, not inside those."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield child
        else:
            yield from _nested_definitions(child)


def _gaps_in_body(path: Path, body: Sequence[ast.stmt], owner: str, in_class: bool) -> Iterator[Gap]:
    """The gaps among the statements of a module or class body; `owner` prefixes their names."""
    for position, node in enumerate(body):
        following = body[position + 1] if position + 1 < len(body) else None
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            if not _is_string(following):
                kind = "attribute" if in_class else "constant"
                yield from (Gap(path, node.lineno, kind, f"{owner}{name}") for name in _assigned_names(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield from _gaps_in_definition(path, node, owner, in_class)
        elif isinstance(node, ast.If):
            if not _is_type_checking(node):
                yield from _gaps_in_body(path, node.body, owner, in_class)
            yield from _gaps_in_body(path, node.orelse, owner, in_class)


def _gaps_in_definition(path: Path, node: Definition, owner: str, in_class: bool) -> Iterator[Gap]:
    """The gaps in one class or function: its own docstring, then what it defines."""
    qualified = f"{owner}{node.name}"
    if isinstance(node, ast.ClassDef):
        if not _has_docstring(node):
            yield Gap(path, node.lineno, "class", qualified)
        yield from _gaps_in_body(path, node.body, f"{qualified}.", in_class=True)
        return
    decorators = _decorator_names(node)
    if decorators & {"setter", "deleter", "overload"}:
        return
    if not _has_docstring(node):
        yield Gap(path, node.lineno, _function_kind(decorators, in_class), qualified)
    for nested in _nested_definitions(node):
        yield from _gaps_in_definition(path, nested, f"{qualified}.<locals>.", in_class=False)


def gaps_in(path: Path) -> list[Gap]:
    """Every gap in one module, in source order."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    gaps = [] if _has_docstring(tree) else [Gap(path, 1, "module", path.stem)]
    gaps.extend(_gaps_in_body(path, tree.body, "", in_class=False))
    return sorted(gaps, key=lambda gap: gap.line)


def main(argv: list[str] | None = None) -> int:
    """Check every module under ``src/vsdxkit``, or the files named on the command line."""
    arguments = sys.argv[1:] if argv is None else argv
    paths = [Path(argument) for argument in arguments] or sorted(PACKAGE.glob("*.py"))
    if not paths:
        print(f"error: no modules under {PACKAGE}/; run from the repository root", file=sys.stderr)
        return 2
    gaps = [gap for path in paths for gap in gaps_in(path)]
    for gap in gaps:
        print(gap)
    if gaps:
        print(f"{len(gaps)} definition(s) without documentation")
        return 1
    print(f"ok: every definition in {len(paths)} module(s) is documented")
    return 0


if __name__ == "__main__":
    sys.exit(main())
