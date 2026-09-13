"""Verify the changelog documents the version being released.

Run by the publish workflow before anything is uploaded:

    python tools/release_check.py 0.7.1

release-please writes the changelog section and bumps the version in the same
pull request, so on the automated path this can only fail if those two writes
disagree -- if the `extra-files` version bump stops matching, say. The check
does its real work on the other path: a manual run of the Publish workflow
republishes a tagged version, and nothing in that run has written a changelog
entry. PyPI takes a version exactly once, so check rather than trust.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHANGELOG = REPO_ROOT / "CHANGELOG.md"

# release-please writes "## [1.2.3](<compare url>) (2026-01-01)", where the
# version is a link label. Sections written before it took over the file are a
# bare "## 1.2.3" or Keep a Changelog's "## [1.2.3] - 2026-01-01", and those
# still have to parse: a manual publish may target a version from back then.
# Any other "## " line matches too, and that is deliberate -- an unrecognised
# heading still has to delimit the section above it.
HEADING_RE = re.compile(r"^##\s+\[?(?P<version>[^\]\s]+)\]?\s*(.*)$")


def section_for(version: str, changelog: Path | None = None) -> str | None:
    """Return the changelog body for a version, or None if it has no section.

    An existing but empty section returns the empty string, which callers must
    treat as a failure -- see `main`. The match is on the version alone, so a
    heading's link target and date are ignored.
    """
    path = DEFAULT_CHANGELOG if changelog is None else changelog
    lines = path.read_text(encoding="utf-8").splitlines()

    start: int | None = None
    for index, line in enumerate(lines):
        heading = HEADING_RE.match(line)
        if heading is None:
            continue
        if start is not None:
            return "\n".join(lines[start:index]).strip("\n")
        if heading.group("version") == version:
            start = index + 1
    if start is None:
        return None
    return "\n".join(lines[start:]).strip("\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="the version being released, e.g. 0.7.0")
    parser.add_argument("--changelog", type=Path, default=None, help="changelog path (defaults to the repo's)")
    args = parser.parse_args(argv)

    body = section_for(args.version, args.changelog)
    if body is None:
        print(
            f"FAIL: CHANGELOG.md has no section for {args.version}. "
            f"On the release-please path this means the release pull request bumped the version without "
            f"writing a changelog section; on a manual publish it means {args.version} was never released."
        )
        return 1
    if not body.strip():
        # An empty section passes a "does it exist" test but produces a release
        # with a blank body, which is the outcome this check exists to prevent.
        print(
            f"FAIL: the CHANGELOG.md section for {args.version} is empty. "
            f"A release cannot be published with no record of what changed."
        )
        return 1
    print(f"ok: CHANGELOG.md documents {args.version}")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
