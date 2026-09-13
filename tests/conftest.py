"""Shared pytest fixtures for the vsdxkit test suite."""

import functools
import os
import shutil
import subprocess

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


def _is_package_file(filename: str) -> bool:
    return filename.lower().endswith((".vsdx", ".vsdm"))


@functools.cache
def _defects_by_fixture() -> tuple[tuple[str, frozenset], ...]:
    """Each fixture's own defects, longest name first, for provenance matching."""
    found = []
    for name in os.listdir(BASEDIR):
        if not _is_package_file(name):
            continue
        defects = frozenset(validate_package(os.path.join(BASEDIR, name)))
        if defects:
            found.append((os.path.splitext(name)[0], defects))
    return tuple(sorted(found, key=lambda entry: -len(entry[0])))


def _inherited_by(filename: str, request) -> frozenset:
    """Defects the input already had, for an output derived from that input.

    A test that opens a non-conformant fixture and saves reproduces its defects,
    which is the library behaving correctly - a writer whose contract is
    fidelity should not quietly repair its input. Blaming the test that saved it
    would make the check unusable.

    Provenance is established two ways, because neither alone is enough. Most
    outputs are named after their input, which `vsdx_copy` and the save helpers
    both do; but a test that writes to a fixed name like `out.vsdx` keeps no
    trace of where it came from, and there the fixture name is usually the test
    parameter instead.

    Both are narrow on purpose. An earlier version subtracted one fixture's
    defects from every output whatever its provenance, and because every fixture
    came off the same Visio generator the relationship ids coincide exactly - so
    a package that had silently lost all four of its `docProps` parts came back
    clean, in every test. An exemption that cannot say which input it is
    excusing excuses everything.
    """
    stem = os.path.splitext(filename)[0]
    named = {stem}
    callspec = getattr(request.node, "callspec", None)
    for value in () if callspec is None else callspec.params.values():
        if isinstance(value, str) and _is_package_file(value):
            named.add(os.path.splitext(value)[0])

    inherited: frozenset = frozenset()
    for fixture_stem, defects in _defects_by_fixture():
        if fixture_stem in named or stem.startswith(fixture_stem):
            inherited |= defects
    return inherited


@pytest.fixture(autouse=True)
def _packages_written_are_structurally_sound(request, tmp_path):
    """Validate every .vsdx a test leaves in tmp_path, whether it meant to or not.

    Most tests that write a package assert one thing about it and say nothing
    about the rest. This catches the rest: a duplicate shape id, glue naming a
    shape that is not there, a relationship pointing at a part that does not
    exist. It is free to the test author by design, because the defects it finds
    are the ones nobody thinks to check for.

    Every `.vsdx` and `.vsdm` is checked, with no sniffing for "is this really a
    Visio package". A sniff has to read some part, and every part it could read
    is one whose absence is itself a defect - gating on `visio/pages/pages.xml`
    means a package that lost it switches the check off instead of failing it.
    So the exceptions are declared, not inferred:

        @pytest.mark.allow_invalid_package
        @pytest.mark.allow_invalid_package("stale-sheet-reference")

    Tests that deliberately write a broken or synthetic archive say so, and the
    marker is enforced by `--strict-markers`, so a typo is an error rather than
    a silent no-op. Naming kinds excuses only those, which is what a test that
    reaches one known shortfall wants: a bare marker on such a test switches off
    every other rule for it too, and the next defect it writes goes unreported.
    """
    # `tmp_path` is taken as an argument rather than looked up on demand: pytest
    # finalises fixtures in reverse dependency order, and a fixture that merely
    # asks for it at teardown finds it already gone.
    yield
    marker = request.node.get_closest_marker("allow_invalid_package")
    if marker is not None and not marker.args:
        return
    excused_kinds = frozenset(marker.args) if marker is not None else frozenset()
    for directory, _, filenames in os.walk(str(tmp_path)):
        for filename in sorted(filenames):
            if not _is_package_file(filename):
                continue
            path = os.path.join(directory, filename)
            inherited = _inherited_by(filename, request)
            defects = tuple(d for d in validate_package(path) if d not in inherited and d.kind not in excused_kinds)
            if defects:
                raise AssertionError(
                    f"{filename} was written with {len(defects)} structural defect(s):\n"
                    + describe_defects(defects)
                    + "\n\nThese are defects on the file format's own terms. If this test means to "
                    "produce a broken package, mark it @pytest.mark.allow_invalid_package."
                )
