"""Verify a release tag matches the version the package will publish.

Run by the release workflow before anything is built:

    python tools/check_version_tag.py "$GITHUB_REF"

PyPI accepts each version exactly once, so a tag that disagrees with
`vsdxkit.__version__` publishes an uncorrectable mistake. The tag may be given as
a bare version, a `v`-prefixed tag, or a full `refs/tags/...` ref.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# PEP 440 is broader than this, but a release of this project is a plain
# release or pre-release; anything else is a tag that should not be publishing.
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?(?:\.post\d+)?$")


def normalise(tag: str) -> str:
    """Reduce a ref, tag or bare version to the version it names."""
    name = tag.rsplit("/", 1)[-1].strip()
    return name[1:] if name.startswith("v") else name


def mismatch(tag: str, version: str) -> str | None:
    """Return why the tag cannot publish this version, or None if it can."""
    tagged = normalise(tag)
    if not VERSION_RE.match(tagged):
        return f"tag {tag!r} does not name a release version (expected e.g. v1.2.3 or v1.2.3rc1)"
    if tagged != version:
        return f"tag {tag!r} names version {tagged}, but the package declares {version}"
    return None


def packaged_version() -> str:
    """Read `vsdxkit.__version__` without importing the package's dependencies."""
    source = (Path(__file__).resolve().parent.parent / "src" / "vsdxkit" / "__init__.py").read_text(encoding="utf-8")
    found = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', source, re.MULTILINE)
    if found is None:
        raise SystemExit("could not find __version__ in src/vsdxkit/__init__.py")
    return found.group(1)


def main(argv: list[str]) -> int:
    if argv == ["--print-version"]:
        # so a caller needing the version does not re-implement the lookup
        print(packaged_version())
        return 0
    if len(argv) != 1:
        print("usage: check_version_tag.py <tag or refs/tags/... ref> | --print-version")
        return 2
    version = packaged_version()
    problem = mismatch(argv[0], version)
    if problem is not None:
        print(f"FAIL: {problem}")
        return 1
    print(f"ok: tag {argv[0]} matches vsdxkit.__version__ {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
