"""Rewrite the two layout digests, ``routes.sha256`` and ``builder_bytes.sha256``, and print old and new.

Usage:
    python tools/regen_digests.py

Run it at the end of a phase that moves a route, then read the diff of both files. A digest that differs on one
platform with no code change is a determinism defect, so never use this tool to silence it.
"""

import hashlib
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent.parent / "tests"
sys.path.insert(0, str(TESTS))

import layout_corpus  # noqa: E402
from helpers.route_metrics import layout_digest  # noqa: E402
from test_builder import _fixed_bytes  # noqa: E402

FIXTURES = TESTS / "fixtures"


def _rewrite(name: str, digest: str) -> None:
    """Replace the digest file `name` with `digest` (LF ending) and print `name: old -> new`."""
    path = FIXTURES / name
    old = path.read_text(encoding="utf-8").strip() if path.exists() else "(none)"
    path.write_text(f"{digest}\n", encoding="utf-8", newline="\n")
    print(f"{name}: {old} -> {digest}")


def main() -> int:
    """Regenerate both digests; always 0, because reading the diff is the caller's job."""
    _rewrite("routes.sha256", layout_digest(layout_corpus.all_layouts()))
    with tempfile.TemporaryDirectory() as tmp:
        _rewrite("builder_bytes.sha256", hashlib.sha256(_fixed_bytes(Path(tmp), "d")).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
