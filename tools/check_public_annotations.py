"""Fail if any public function, method or property lacks a return annotation.

Checker-independent completeness gate (the issue's "public type-completeness
gate"): AST-based, so it does not depend on how aggressively a type checker
infers from implementation bodies. Pyright infers; Mypy consumers receive Any;
this gate keeps the declared contract honest regardless.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

DUNDER_OK = {
    "__init__",
    "__enter__",
    "__exit__",
    "__repr__",
    "__str__",
    "__iter__",
    "__next__",
    "__len__",
    "__getitem__",
    "__contains__",
}


def public_definitions(package_dir: Path) -> list[tuple[Path, int, str]]:
    missing: list[tuple[Path, int, str]] = []
    for path in sorted(package_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_") or node.name in DUNDER_OK:
                continue
            if node.returns is None:
                missing.append((path, node.lineno, node.name))
    return missing


def main() -> int:
    package_dir = Path("src") / "vsdxkit"
    if not package_dir.is_dir():
        print(f"error: {package_dir}/ not found; run from the repository root", file=sys.stderr)
        return 2
    missing = public_definitions(package_dir)
    for path, lineno, name in missing:
        print(f"FAIL: {path}:{lineno}: public definition {name!r} has no return annotation")
    if missing:
        print(f"{len(missing)} public definition(s) missing return annotations")
        return 1
    print("ok: every public definition carries a return annotation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
