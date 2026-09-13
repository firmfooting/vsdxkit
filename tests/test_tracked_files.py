"""What may be tracked in the repository.

Generated build metadata is the specific thing guarded here, because it has
already got in once. `.gitignore` carried a rooted `/vsdxkit.egg-info/` rule,
the move to a src layout put setuptools' output at `src/vsdxkit.egg-info/`
instead, the rule stopped matching, and the directory was committed with the
rename. Nothing failed: the tree read as clean afterwards precisely because the
files were tracked.

It matters beyond tidiness. `PKG-INFO` pins a version, so a tracked copy goes
stale at the next release and then disagrees with `vsdxkit.__version__`; and
every local editable install or `python -m build` rewrites these files, dirtying
the working tree for anyone who runs one.
"""

import fnmatch
import os
import subprocess

import pytest

BASEDIR = os.path.dirname(os.path.realpath(__file__))

# Patterns matched against a repository-relative path, unanchored at the front
# so a nested copy is caught too - which is the whole failure being guarded.
GENERATED_ARTEFACTS = (
    "*.egg-info/*",
    "*.egg-info",
    "*.pyc",
    "*.pyo",
    "__pycache__/*",
    ".coverage",
    "coverage.xml",
    "*.orig",
    "*.rej",
)


def tracked_files() -> list[str] | None:
    """Every path git has under version control, or None if git cannot say."""
    try:
        result = subprocess.run(
            # `--full-name` and the `:/` pathspec together make this the whole
            # repository, spelled from its root. Run from `tests/`, a plain
            # `ls-files` lists that subtree only and spells it relative to
            # here - so the guard below would have looked straight past the
            # `src/` directory that prompted it.
            ["git", "-C", BASEDIR, "ls-files", "--full-name", "--", ":/"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None  # git is missing or did not finish
    if result.returncode != 0:
        return None  # not a checkout, e.g. running against an unpacked sdist
    return [line for line in result.stdout.splitlines() if line]


def test_no_generated_build_artefact_is_tracked():
    """Build output belongs to whoever ran the build, not to the repository."""
    paths = tracked_files()
    if paths is None:
        pytest.skip("not a git checkout")
    offenders = sorted(path for path in paths if any(fnmatch.fnmatch(path, pattern) for pattern in GENERATED_ARTEFACTS))
    assert offenders == [], (
        "these generated files are tracked:\n"
        + "\n".join(f"  {path}" for path in offenders)
        + "\n\nRemove them with `git rm -r --cached`, then check that .gitignore really "
        "excludes them - a rooted rule stops matching as soon as the directory moves."
    )


def test_the_listing_is_not_silently_empty():
    """Without this the guard above passes on a broken `git ls-files`."""
    paths = tracked_files()
    if paths is None:
        pytest.skip("not a git checkout")
    assert "pyproject.toml" in paths
    assert len(paths) > 100
