"""Distribution smoke test: the sdist carries a test suite that runs.

Run by the CI build job from the repository checkout, against the built sdist:

    python tools/smoke_sdist.py dist/*.tar.gz

The first check is the one that regresses in silence. With no MANIFEST.in the
default file list takes `tests/test*.py` and nothing else, so the archive ships
36 test modules with no conftest.py and no .vsdx fixtures -- a suite that errors
on every test that opens a document. Comparing the archive against the tracked
files means a fixture added under a directory the manifest does not graft fails
here rather than on a packager's machine.

The second check unpacks the archive and runs the suite from it, because two
file lists agreeing is not the same as the tests passing.
"""

from __future__ import annotations

import glob
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

# Directories whose tracked contents must reach the sdist in full. vsdx/ is not
# among them: the wheel smoke test already covers the package, and setuptools
# puts the package in the sdist with or without a manifest.
REQUIRED_TREES = ("tests", "tools")

failures: list[str] = []


def fail(message: str) -> None:
    failures.append(message)
    print(f"FAIL: {message}")


def ok(message: str) -> None:
    print(f"ok: {message}")


def tracked_files(repo_root: Path) -> set[str]:
    """Paths git tracks under the required trees, as forward-slash strings."""
    listed = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-z", *REQUIRED_TREES],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {entry for entry in listed.split("\0") if entry}


def members_below_root(archive: Path) -> set[str]:
    """Archive members with the leading `name-version/` component stripped."""
    with tarfile.open(archive) as tar:
        names = tar.getnames()
    return {name.split("/", 1)[1] for name in names if "/" in name}


def run_suite(archive: Path) -> None:
    """Unpack the sdist and run its own test suite from the unpacked root."""
    with tempfile.TemporaryDirectory() as workdir:
        with tarfile.open(archive) as tar:
            # filter="data" refuses absolute paths and traversal. It is the
            # default from 3.14 and a deprecation warning before that, but it
            # reached 3.10 and 3.11 only in a patch release, and this project
            # supports those minors from their .0.
            try:
                tar.extractall(workdir, filter="data")
            except TypeError:
                tar.extractall(workdir)  # the archive is one this repository just built
        roots = sorted(Path(workdir).iterdir())
        if len(roots) != 1:
            fail(f"sdist does not unpack to a single directory: {[path.name for path in roots]}")
            return
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "tests"],
                cwd=roots[0],
                capture_output=True,
                text=True,
                # The suite takes seconds. Output is captured, so a test that
                # hangs would otherwise sit silently until the runner's own
                # six-hour limit killed the job.
                timeout=1800,
            )
        except subprocess.TimeoutExpired:
            fail("the test suite did not finish within 30 minutes from the unpacked sdist")
            return
        tail = result.stdout.splitlines()[-25:]
        if result.returncode != 0:
            joined = "\n".join(tail)
            fail(f"the test suite does not pass from the unpacked sdist:\n{joined}\n{result.stderr.strip()}")
        else:
            ok(f"the test suite passes from the unpacked sdist: {tail[-1] if tail else 'no output'}")


def main() -> int:
    candidates = sorted(glob.glob(sys.argv[1] if len(sys.argv) > 1 else "dist/*.tar.gz"))
    if not candidates:
        fail("no sdist found")
        return 1
    if len(candidates) > 1:
        # A stale archive next to a fresh one would otherwise be verified in its
        # place, and report PASS for a version nobody is releasing.
        fail(f"{len(candidates)} sdists match; name the one to check: {candidates}")
        return 1
    archive = Path(candidates[0]).resolve()
    repo_root = Path(__file__).resolve().parent.parent

    shipped = members_below_root(archive)
    missing = sorted(tracked_files(repo_root) - shipped)
    trees = ", ".join(f"{tree}/" for tree in REQUIRED_TREES)
    if missing:
        fail(f"{len(missing)} tracked file(s) under {trees} are absent from the sdist: {missing[:10]}")
    else:
        ok(f"every tracked file under {trees} is in the sdist")

    # Named individually rather than left to the parity check above: these are
    # what the 0.7.0 sdist was missing, and naming them makes the report legible
    # to someone who has not read the manifest.
    for expected in ("tests/conftest.py", "CHANGELOG.md", "CONTRIBUTING.md"):
        if expected not in shipped:
            fail(f"{expected} is missing from the sdist")
    fixtures = sorted(name for name in shipped if name.startswith("tests/") and name.endswith((".vsdx", ".vsdm")))
    if len(fixtures) < 20:
        fail(f"sdist carries {len(fixtures)} test fixtures, expected the whole set")
    else:
        ok(f"sdist carries {len(fixtures)} .vsdx/.vsdm test fixtures")

    # Only worth the unpack-and-run cost once the archive is known to be whole;
    # an incomplete one fails above with a more useful message than pytest gives.
    if not failures:
        run_suite(archive)

    if failures:
        print(f"{len(failures)} sdist smoke failure(s)")
        return 1
    print("sdist smoke: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
