"""Fail if a public name of vsdx 0.8.0 is gone from vsdxkit and the migration guide does not name it.

The 0.8.0 surface is `tools/api-0.8.0.txt`. Each name is looked up where 1.0
keeps it: `vsdx` is `vsdxkit`, `VisioFile` is `vsdxkit.document.Document` and
`Container` is `vsdxkit.swimlanes.SwimlaneDiagram`. A name that is not found
there must appear in an inline literal or code block of
`docs/migration-1.0.rst`; a name imported from the package root must appear
as ``from vsdx import <name>``.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

SNAPSHOT = Path("tools") / "api-0.8.0.txt"
GUIDE = Path("docs") / "migration-1.0.rst"

# where 1.0 keeps a 0.8.0 class under another name
CLASS_RENAMES = {
    ("vsdxfile", "VisioFile"): ("document", "Document"),
    ("containers", "Container"): ("swimlanes", "SwimlaneDiagram"),
}

_INLINE_LITERAL = re.compile(r"``(.+?)``")
_IDENTIFIER = re.compile(r"[A-Za-z_]\w*")
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


def lookup(module_name: str, name: str) -> object | None:
    """The 1.0 object a 0.8.0 module-level name became, where 1.0 keeps it under that module."""
    module_name, name = CLASS_RENAMES.get((module_name, name), (module_name, name))
    try:
        module = importlib.import_module(f"vsdxkit.{module_name}")
    except ModuleNotFoundError:
        return None
    return getattr(module, name, None)


def moved(name: str, modules: list[str]) -> object | None:
    """The one class of this name that a 1.0 module defines, wherever it moved to."""
    found = []
    for module_name in modules:
        value = getattr(importlib.import_module(f"vsdxkit.{module_name}"), name, None)
        if isinstance(value, type) and value.__module__ == f"vsdxkit.{module_name}":
            found.append(value)
    return found[0] if len(found) == 1 else None


def unexplained(names: list[str], literals: list[str], modules: list[str]) -> list[str]:
    identifiers = {identifier for literal in literals for identifier in _IDENTIFIER.findall(literal)}
    root_imports = {
        imported.strip() for literal in literals for match in _ROOT_IMPORT.findall(literal) for imported in match.split(",")
    }
    missing = []
    for dotted in names:
        parts = dotted.split(".")[1:]
        if len(parts) == 1:
            if parts[0] not in root_imports:
                missing.append(f"{dotted} (as `from vsdx import {parts[0]}`)")
            continue
        module_name, name = parts[0], parts[1]
        owner = lookup(module_name, name)
        if len(parts) == 2:
            if owner is None and name not in identifiers:
                missing.append(dotted)
            continue
        # a member of a class that is gone is explained by the class's entry;
        # a member of a class that moved is looked for where it moved to
        owner = owner or moved(name, modules)
        if owner is not None and not hasattr(owner, parts[2]) and parts[2] not in identifiers:
            missing.append(dotted)
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
