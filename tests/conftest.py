"""Shared pytest fixtures for the vsdx test suite."""

import functools
import os
import shutil
import subprocess
import zipfile

import pytest
from helpers.package_validator import describe_defects, validate_package

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


@functools.cache
def _inherited_defects() -> frozenset:
    """Defects an input already had, which the test that saved it did not cause.

    `tests/test5_master.vsdx` arrived from upstream declaring relationships and
    content type overrides for four `docProps` parts it does not contain (see
    issue #298). A test that opens it and saves reproduces them, which is the
    library behaving correctly: a writer whose contract is fidelity should not
    quietly repair its input.

    Excusing them by filename would be wrong, since an output is usually but not
    always named after its input, so the match is on the defects themselves.
    That is broader than it sounds: a defect from any other fixture whose text
    happens to coincide with one of these seven is excused too. Acceptable while
    this is the only non-conformant input in the corpus; revisit if a second
    appears.
    """
    return frozenset(validate_package(os.path.join(BASEDIR, "test5_master.vsdx")))


def _is_visio_package(path: str) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return "visio/pages/pages.xml" in archive.namelist()
    except (OSError, zipfile.BadZipFile):
        return False


@pytest.fixture(autouse=True)
def _packages_written_are_structurally_sound(request, tmp_path):
    """Validate every .vsdx a test leaves in tmp_path, whether it meant to or not.

    Most tests that write a package assert one thing about it and say nothing
    about the rest. This catches the rest: a duplicate shape id, glue naming a
    shape that is not there, a relationship pointing at a part that does not
    exist. It is free to the test author by design, because the defects it finds
    are the ones nobody thinks to check for.

    A test that means to produce a broken package says so:

        @pytest.mark.allow_invalid_package
    """
    # `tmp_path` is taken as an argument rather than looked up on demand: pytest
    # finalises fixtures in reverse dependency order, and a fixture that merely
    # asks for it at teardown finds it already gone.
    yield
    if request.node.get_closest_marker("allow_invalid_package"):
        return
    for directory, _, filenames in os.walk(str(tmp_path)):
        for filename in sorted(filenames):
            if not filename.endswith((".vsdx", ".vsdm")):
                continue
            path = os.path.join(directory, filename)
            if not _is_visio_package(path):
                # Several suites build deliberately hostile or synthetic archives
                # to exercise the zip reader - declared entry counts that lie,
                # members with absolute paths, two-file fixtures for the differ.
                # They are named .vsdx because that is what the code under test
                # accepts, but there is no document in them to have defects.
                continue
            inherited = _inherited_defects()
            defects = tuple(d for d in validate_package(path) if d not in inherited)
            if defects:
                raise AssertionError(
                    f"{filename} was written with {len(defects)} structural defect(s):\n"
                    + describe_defects(defects)
                    + "\n\nThese are defects on the file format's own terms. If this test means to "
                    "produce a broken package, mark it @pytest.mark.allow_invalid_package."
                )
