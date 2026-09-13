"""Verify the version pins in `.github/workflows/` say what they mean.

Runs in CI (lint job), and checks two things.

Every `uses: owner/repo@<40-hex sha>` line must carry a comment naming a tag
that resolves to exactly that commit, resolved live via `git ls-remote` — so a
Renovate bump that leaves a stale comment behind fails here instead of
misinforming review.

Every `astral-sh/setup-uv` step must also pin uv itself, to the same version as
every other such step. That pin is a `with:` input, which neither Renovate's
`python-deps` rule nor the digest check above looks at, so the copies of the
string were maintained by hand with nothing comparing them — and zizmor.yml had
never carried one, running its `uv sync --locked` under whatever uv was current
that day. This half needs no network.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

USES_RE = re.compile(
    r"^\s*-?\s*uses:\s*(?P<action>[\w.-]+/[\w.-]+(?:/[\w.-]+)*)@(?P<sha>[0-9a-f]{40})(?:\s+#\s*(?P<comment>\S+))?\s*$"
)

# `lead` is everything before the key, so its length is the column the step's
# own keys sit at. The `- ` is optional because `uses:` is only on the dash line
# in an unnamed step; a step written `- name: ...` carries it on the line below,
# and that spelling must not slip past the check.
SETUP_UV_RE = re.compile(r"^(?P<lead>\s*(?:-\s+)?)uses:\s*astral-sh/setup-uv@")
UV_VERSION_RE = re.compile(r"^\s*version:\s*[\"']?(?P<version>[^\"'\s#]+)")


def uv_pins(workflow: Path) -> list[tuple[int, str | None]]:
    """Locate every setup-uv step in a workflow and the uv version it pins.

    Returns the step's line number and its `version:` input, or None where the
    step declares none. Scanned line by line rather than parsed: the repository
    carries no YAML dependency, and a step's body is simply the run of lines
    indented at least as far as the step's own keys.
    """
    lines = workflow.read_text(encoding="utf-8").splitlines()
    found: list[tuple[int, str | None]] = []
    for index, line in enumerate(lines):
        step = SETUP_UV_RE.match(line)
        if step is None:
            continue
        key_column = len(step.group("lead"))
        pinned: str | None = None
        for body in lines[index + 1 :]:
            if body.strip() and len(body) - len(body.lstrip()) < key_column:
                break  # dedented out of the step
            version = UV_VERSION_RE.match(body)
            if version:
                pinned = version.group("version")
                break
        found.append((index + 1, pinned))
    return found


def uv_pin_failures(workflow_dir: Path) -> tuple[list[str], str]:
    """Report setup-uv steps with a missing uv pin, or one that is the odd one out.

    Returns the failures and a summary naming how many steps were checked, so a
    run that matched no steps at all cannot read as a pass.
    """
    pins: list[tuple[Path, int, str | None]] = []
    for workflow in sorted({*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")}):
        pins.extend((workflow, line_number, version) for line_number, version in uv_pins(workflow))

    failures = [
        f"{workflow}:{line_number}: astral-sh/setup-uv declares no `version:`, so the job runs whatever uv is current"
        for workflow, line_number, version in pins
        if version is None
    ]
    declared = sorted({version for _, _, version in pins if version is not None})
    if len(declared) > 1:
        sites = ", ".join(f"{workflow}:{line_number} ({version})" for workflow, line_number, version in pins)
        failures.append(f"setup-uv steps disagree on the uv version {declared}: {sites}")
    return failures, f"{len(pins)} setup-uv steps pin uv {declared}"


def resolved_tag_map(action: str) -> dict[str, set[str]]:
    """Map commit sha -> set of tag names for a GitHub action repository.

    ``action`` may include a subpath (``owner/repo/sub``); the git remote is
    always the first two path components.
    """
    repo = "/".join(action.split("/")[:2])
    output = subprocess.run(
        ["git", "ls-remote", f"https://github.com/{repo}", "refs/tags/*"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    raw: dict[str, str] = {}
    for line in output.splitlines():
        sha, ref = line.split(maxsplit=1)
        raw[ref.strip()] = sha
    commits_to_tags: dict[str, set[str]] = {}
    for ref, sha in raw.items():
        if not ref.startswith("refs/tags/"):
            continue
        if ref.endswith("^{}"):  # peeled commit of an annotated tag
            tag = ref[len("refs/tags/") : -len("^{}")]
        else:
            tag = ref[len("refs/tags/") :]
            if f"refs/tags/{tag}^{{}}" in raw:
                continue  # the peeled entry carries the commit sha
        commits_to_tags.setdefault(sha, set()).add(tag)
    return commits_to_tags


def main() -> int:
    workflow_dir = Path(".github/workflows")
    pins: list[tuple[Path, str, str, str | None]] = []
    for workflow in sorted({*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")}):
        for line_number, line in enumerate(workflow.read_text(encoding="utf-8").splitlines(), start=1):
            match = USES_RE.match(line)
            if match:
                pins.append((workflow, line_number, match.group("action"), match.group("comment"), match.group("sha")))  # type: ignore[arg-type]

    cache: dict[str, dict[str, set[str]]] = {}
    failures: list[str] = []
    for workflow, line_number, action, comment, sha in pins:  # type: ignore[misc]
        if action not in cache:
            cache[action] = resolved_tag_map(action)
        tags = cache[action].get(sha)
        if tags is None:
            failures.append(f"{workflow}:{line_number}: {action}@{sha[:12]} does not match any tag")
            continue
        if comment is None:
            failures.append(f"{workflow}:{line_number}: {action}@{sha[:12]} has no version annotation (tags: {sorted(tags)})")
        elif comment not in tags:
            failures.append(
                f"{workflow}:{line_number}: {action}@{sha[:12]} is annotated {comment} but resolves to {sorted(tags)}"
            )

    uv_failures, uv_summary = uv_pin_failures(workflow_dir)
    if failures or uv_failures:
        for failure in failures + uv_failures:
            print(f"FAIL: {failure}")
        return 1
    print(f"ok: {len(pins)} action pins match their annotations")
    print(f"ok: {uv_summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
