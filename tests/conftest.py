"""Shared pytest fixtures for the vsdx test suite."""

import os
import shutil
import subprocess

import pytest

# resolve relative to this file, independent of pytest's working directory
BASEDIR = os.path.dirname(os.path.realpath(__file__))


@pytest.fixture(scope="session")
def basedir() -> str:
    """Return the tests directory, for building paths to the .vsdx fixtures.

    Take this fixture rather than deriving a path from ``os.getcwd()`` or from
    a relative ``__file__``. Both of those resolve only when pytest is invoked
    from the repository root, so a run started from an IDE, a parent directory
    or an unpacked sdist fails on missing files instead of on behaviour.
    """
    return BASEDIR


@pytest.fixture
def vsdx_copy(tmp_path):
    """Return a factory giving a fresh copy of a test file in tmp_path."""

    def _copy(filename: str) -> str:
        source = os.path.join(BASEDIR, filename)
        destination = os.path.join(str(tmp_path), filename)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy(source, destination)
        return destination

    return _copy


def _git_status() -> frozenset[str] | None:
    """Return `git status --porcelain` lines, or None if git cannot report.

    `--untracked-files=all` is what makes this usable as a leak detector. Git
    otherwise collapses an untracked directory to a single entry, so a file
    written into a directory that already existed would not show up. The flag
    also overrides a local `status.showUntrackedFiles=no`.
    """
    try:
        result = subprocess.run(
            ["git", "-C", BASEDIR, "status", "--porcelain", "--untracked-files=all"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None  # git is missing or did not finish
    if result.returncode != 0:
        return None  # not a checkout, e.g. running against an unpacked sdist
    return frozenset(line for line in result.stdout.splitlines() if line)


@pytest.fixture(scope="session", autouse=True)
def _hermetic_working_tree():
    """Fail the session if tests leave anything behind in the working tree.

    Tests write to tmp_path, so a run must not touch the checkout. Compares
    against a snapshot taken at session start rather than demanding a clean
    tree, so unrelated local edits do not fail every run. That also means a
    leak left on disk joins the next run's snapshot, so delete it or the next
    run goes green with the file still there.
    """
    before = _git_status()
    yield
    after = _git_status()
    if before is None or after is None:
        return
    new_entries = sorted(after - before)
    if new_entries:
        raise AssertionError(
            "the test run added these paths to the working tree:\n"
            + "\n".join(new_entries)
            + "\n\nDelete them, then make the test that wrote them use tmp_path. This error is "
            "raised at session teardown, so the test it is attached to is not necessarily the "
            "one that leaked; go by the paths above."
        )
