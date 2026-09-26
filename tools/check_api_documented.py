"""Fail if a name the wheel exports is missing from the built API reference.

pyright's ``--verifytypes`` report, which ``tools/check_type_completeness.py
--report`` writes in CI's build job, lists every symbol the wheel exports. The
docs build writes ``objects.inv``, the index of every name the generated
reference documents. A public name in the first and not the second is exported
but undocumented. ``sphinx-build -W`` cannot see that: a name left out of the
reference is an absence, not a warning (#424).

A name with an underscore-prefixed segment is private, in its own name or its
module's, and is not checked; that includes dunders such as ``__init__``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def exported_names(report: dict[str, object]) -> set[str]:
    """The public names pyright's report counts as exported by the wheel."""
    completeness = report.get("typeCompleteness")
    if not isinstance(completeness, dict):
        return set()
    symbols = completeness.get("symbols")
    if not isinstance(symbols, list):
        return set()
    return {
        symbol["name"]
        for symbol in symbols
        if symbol.get("isExported") and not any(part.startswith("_") for part in symbol["name"].split("."))
    }


def documented_names(inventory: bytes) -> set[str]:
    """Every Python name an ``objects.inv`` holds, whatever its role."""
    # Sphinx is in the docs group only. The test job imports this module
    # without it, to check `verdict` and `exported_names`.
    from sphinx.util.inventory import InventoryFile

    data = InventoryFile.loads(inventory, uri="").data
    return {name for role, entries in data.items() if role.startswith("py:") for name in entries}


def verdict(exported: set[str], documented: set[str]) -> tuple[int, list[str]]:
    """The exit status and the lines to print: 0 when every exported name is documented."""
    if not exported:
        return 2, ["error: the report exports no public name, so there is nothing to check"]
    if not documented:
        return 2, ["error: the inventory documents no Python name, so the docs build measured nothing"]
    missing = sorted(exported - documented)
    if missing:
        return 1, [
            *(f"FAIL: {name} is exported but not in the API reference" for name in missing),
            f"{len(missing)} exported name(s) undocumented",
        ]
    return 0, [f"ok: all {len(exported)} exported public names are in the API reference"]


def main(argv: list[str] | None = None) -> int:
    """Compare the report with the inventory and print what is missing."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path, help="pyright's --verifytypes JSON, from check_type_completeness.py --report")
    parser.add_argument("inventory", type=Path, help="the objects.inv the docs build wrote")
    arguments = parser.parse_args(argv)
    report = json.loads(arguments.report.read_text(encoding="utf-8"))
    status, lines = verdict(exported_names(report), documented_names(arguments.inventory.read_bytes()))
    for line in lines:
        print(line)
    return status


if __name__ == "__main__":
    sys.exit(main())
