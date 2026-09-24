"""Fail if a public name of vsdx 0.8.0 is gone from vsdxkit and the migration guide does not name it.

The 0.8.0 surface is `tools/api-0.8.0.txt`. Each name is looked up where 1.0
keeps it: `vsdx` is `vsdxkit`, `VisioFile` is `vsdxkit.document.Document` and
`Container` is `vsdxkit.swimlanes.SwimlaneDiagram`. A module keeps a name
only if its own source defines it at the top level: a name it imports for its
own use has moved. A class keeps a member it or a vsdxkit base defines, or
assigns on ``self``. A name that is not kept must be named, qualified, in an
inline literal or code block of
`docs/migration-1.0.rst`, so an entry for one owner's name never stands in for
another's:

- a root name as ``from vsdx import <name>``;
- a module-level name as ``<module>.<name>``;
- a member as ``<owner>.<member>``, where the owner is the class or the name
  the guide gives its instances, such as ``page`` for ``Page``.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
import sys
import textwrap
from functools import cache
from pathlib import Path

SNAPSHOT = Path("tools") / "api-0.8.0.txt"
GUIDE = Path("docs") / "migration-1.0.rst"

# where 1.0 keeps a 0.8.0 class under another name
CLASS_RENAMES = {
    ("vsdxfile", "VisioFile"): ("document", "Document"),
    ("containers", "Container"): ("swimlanes", "SwimlaneDiagram"),
}

# how the guide may name the owner of a member, beyond the class's own name
# and its lower-cased form; a mixin's members were called on the VisioFile
OWNER_NAMES = {
    "VisioFile": {"vis"},
    "JinjaTemplatingMixin": {"VisioFile", "vis"},
    "MastersImportMixin": {"VisioFile", "vis"},
}

_INLINE_LITERAL = re.compile(r"``(.+?)``")
# `a.b`, `a().b` and `a[0].b`, overlapping, so `vsdx.xmlio.to_float` gives
# (vsdx, xmlio) and (xmlio, to_float)
_QUALIFIED = re.compile(r"(?<!\w)(?=(\w+)(?:\([^()]*\)|\[[^\]]*\])?\.(\w+))")
_ROOT_IMPORT = re.compile(r"from vsdx import ([\w, ]+)")


def guide_literals(text: str) -> list[str]:
    """The inline literals of the guide, and the lines of its code blocks."""
    literals = _INLINE_LITERAL.findall(text)
    in_block = False
    for line in text.splitlines():
        if line.strip().startswith(".. code-block::"):
            in_block = True
        elif in_block and line and not line[0].isspace():
            in_block = False
        elif in_block:
            literals.append(line)
    return literals


def vsdxkit_modules() -> list[str]:
    return [path.stem for path in sorted((Path("src") / "vsdxkit").glob("*.py")) if not path.stem.startswith("_")]


@cache
def defined_names(module_name: str) -> frozenset[str]:
    """The names a vsdxkit module's own source binds at its top level: not the ones it imports."""
    path = Path("src") / "vsdxkit" / f"{module_name}.py"
    if not path.is_file():
        return frozenset()
    names = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names |= {target.id for target in node.targets if isinstance(target, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return frozenset(names)


def lookup(module_name: str, name: str) -> object | None:
    """The 1.0 object a 0.8.0 module-level name became, where 1.0 keeps it under that module."""
    module_name, name = CLASS_RENAMES.get((module_name, name), (module_name, name))
    if name not in defined_names(module_name):
        return None
    return getattr(importlib.import_module(f"vsdxkit.{module_name}"), name, None)


def instance_attributes(owner: type) -> set[str]:
    """The public names the methods of `owner`, and of its vsdxkit bases, assign on ``self``."""
    names = set()
    for klass in owner.__mro__:
        if not klass.__module__.startswith("vsdxkit."):
            continue
        for node in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(klass)))):
            targets = (
                node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
            )
            for target in targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                    names.add(target.attr)
    return {name for name in names if not name.startswith("_")}


def keeps(owner: object, member: str) -> bool:
    return hasattr(owner, member) or (isinstance(owner, type) and member in instance_attributes(owner))


def moved(name: str, modules: list[str]) -> object | None:
    """The one class of this name that a 1.0 module defines, wherever it moved to."""
    found = []
    for module_name in modules:
        value = getattr(importlib.import_module(f"vsdxkit.{module_name}"), name, None)
        if isinstance(value, type) and value.__module__ == f"vsdxkit.{module_name}":
            found.append(value)
    return found[0] if len(found) == 1 else None


def owner_names(class_name: str) -> set[str]:
    return {class_name, class_name[0].lower() + class_name[1:], *OWNER_NAMES.get(class_name, ())}


def unexplained(names: list[str], literals: list[str], modules: list[str]) -> list[str]:
    qualified = {pair for literal in literals for pair in _QUALIFIED.findall(literal)}
    root_imports = {
        imported.strip() for literal in literals for match in _ROOT_IMPORT.findall(literal) for imported in match.split(",")
    }
    root = importlib.import_module("vsdxkit")
    missing = []
    for dotted in names:
        parts = dotted.split(".")[1:]
        if len(parts) == 1:
            if not hasattr(root, parts[0]) and parts[0] not in root_imports:
                missing.append(f"{dotted} (as `from vsdx import {parts[0]}`)")
            continue
        module_name, name = parts[0], parts[1]
        owner = lookup(module_name, name)
        if len(parts) == 2:
            if owner is None and (module_name, name) not in qualified:
                missing.append(f"{dotted} (as `{module_name}.{name}`)")
            continue
        member = parts[2]
        # a member of a class that moved is looked for where it moved to
        owner = owner or moved(name, modules)
        if owner is not None and keeps(owner, member):
            continue
        if not any((qualifier, member) in qualified for qualifier in owner_names(name)):
            missing.append(f"{dotted} (as `{name}.{member}`)")
    return missing


def main() -> int:
    if not SNAPSHOT.is_file() or not GUIDE.is_file():
        print(f"error: {SNAPSHOT} or {GUIDE} not found; run from the repository root", file=sys.stderr)
        return 2
    names = [line for line in SNAPSHOT.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    missing = unexplained(names, guide_literals(GUIDE.read_text(encoding="utf-8")), vsdxkit_modules())
    for dotted in missing:
        print(f"FAIL: {dotted} is gone in 1.0 and {GUIDE} does not name it")
    if missing:
        print(f"{len(missing)} removed name(s) missing from the migration guide")
        return 1
    print(f"ok: every 0.8.0 name that 1.0 removes is in {GUIDE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
