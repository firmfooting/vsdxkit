"""Run the Visio differential oracle: compare what a package claims to what Visio does.

    python tools/visio_verify.py check  out/probe.vsdx [...]   # live Visio, diff, report
    python tools/visio_verify.py record out/probe.vsdx [...]   # live Visio, save the observation
    python tools/visio_verify.py replay tests/fixtures/visio_observations/*.json

Visio is a slow, stateful, Windows-only oracle and the machine that has it is not
the machine CI runs on, so its answers are worth keeping. `record` saves what
Visio made of a file vsdxkit wrote; `replay` runs the writer again today and
compares its output to that recording, needing no Visio. A recording whose input
has changed is reported stale and fails, rather than passing on a comparison it
did not make.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))

from helpers.visio_observation import (
    SCHEMA_VERSION,
    Observation,
    compare,
    format_differences,
    observation_from_com_json,
    observation_from_package,
)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OBSERVER = os.path.join(HERE, "visio_observe.ps1")
RECORDINGS = os.path.join(REPO, "tests", "fixtures", "visio_observations")

# Visio is 32/64-bit Windows software; the harness drives it from wherever the
# repository is checked out, including WSL. PowerShell 7 first because its error
# records survive the trip intact, but the observer script is written to run
# under Windows PowerShell too, so a machine with only that still works.
_SHELLS = ("pwsh.exe", "powershell.exe", "pwsh", "powershell")


class VisioUnavailable(RuntimeError):
    pass


def _shell() -> str:
    for candidate in _SHELLS:
        found = shutil.which(candidate)
        if found:
            return found
    raise VisioUnavailable(f"no PowerShell found on PATH (tried {', '.join(_SHELLS)})")


def _windows_path(path: str) -> str:
    """Translate a path for the Windows process that will open it.

    Visio is given a path by a process that may not share this one's filesystem
    view. Under WSL that means `wslpath`; elsewhere the path is already right.
    """
    absolute = os.path.abspath(path)
    translator = shutil.which("wslpath")
    if translator is None:
        return absolute
    result = subprocess.run([translator, "-w", absolute], capture_output=True, text=True)
    if result.returncode != 0:
        raise VisioUnavailable(f"could not translate {absolute} for Windows: {result.stderr.strip()}")
    return result.stdout.strip()


def _quote(value: str) -> str:
    """Quote a path for PowerShell's parser.

    Single quotes, because PowerShell does no expansion inside them: a path
    holding `$` or a backtick is common enough on Windows, and inside double
    quotes it would be interpreted rather than opened. A literal single quote is
    escaped by doubling it.
    """
    return "'" + value.replace("'", "''") + "'"


def _windows_temp() -> str:
    """Return Windows' own temp directory, as this process can reach it."""
    result = subprocess.run(
        [_shell(), "-NoProfile", "-NonInteractive", "-Command", "[System.IO.Path]::GetTempPath()"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise VisioUnavailable(f"could not ask Windows for its temp directory: {result.stderr.strip()}")
    windows_temp = result.stdout.strip()
    translator = shutil.which("wslpath")
    if translator is None:
        return windows_temp
    translated = subprocess.run([translator, "-u", windows_temp], capture_output=True, text=True)
    if translated.returncode != 0:
        raise VisioUnavailable(f"could not translate {windows_temp!r} back: {translated.stderr.strip()}")
    return translated.stdout.strip()


@contextlib.contextmanager
def _staged(paths: list[str]):
    """Copy the files somewhere Visio will actually open them, and clean up after.

    Two reasons, and either alone would be enough. Visio rejects a UNC path -
    which is what a WSL checkout looks like from Windows - with "This file name
    is not valid", an error that says nothing about why. And an oracle should
    never be pointed at the repository: the files under test are fixtures, a
    crashed Visio holds whatever it has open, and the suite already fails a run
    that leaves anything behind in the working tree.
    """
    root = tempfile.mkdtemp(prefix="vsdxkit-visio-", dir=_windows_temp())
    try:
        staged: dict[str, str] = {}
        # Keyed by stem, not by full name: a recording is written to
        # `<stem>.json`, so `a.vsdx` and `a.vsdm` collide there even though
        # their filenames differ. Catching it here means the second never
        # silently overwrites the first.
        by_stem: dict[str, str] = {}
        for path in paths:
            name = os.path.basename(path)
            stem = os.path.splitext(name)[0]
            if stem in by_stem:
                raise VisioUnavailable(
                    f"{by_stem[stem]} and {path} would both be recorded as {stem}.json. "
                    "Recordings are keyed by filename stem, so rename one of them."
                )
            by_stem[stem] = path
            destination = os.path.join(root, name)
            shutil.copy2(path, destination)
            staged[name] = path
        yield root, staged
    finally:
        shutil.rmtree(root, ignore_errors=True)


# The subject of a recording. "roundtrip" is the default and the useful one:
# Visio is asked about a file *vsdxkit wrote*, so replaying the recording later
# re-runs today's writer and compares its output to what Visio vouched for.
# Recording a fixture as it sits in git instead ("none") freezes the bytes, and
# a frozen package can only yield the observation it yielded at record time - so
# that kind of recording proves the XML reader still reads the file the same
# way, and nothing whatever about what the library writes.
TRANSFORMS = ("roundtrip", "none")


def _apply_transform(transform: str, source: str, destination: str) -> str:
    """Produce the file Visio should look at, and return its path."""
    if transform == "none":
        return source
    if transform != "roundtrip":
        raise VisioUnavailable(f"unknown transform {transform!r}; expected one of {', '.join(TRANSFORMS)}")
    # imported here, not at module scope: `replay` is the only caller that runs
    # in CI, and it should fail on a broken library rather than on an import.
    import vsdx

    with vsdx.VisioFile(source) as document:
        document.save_vsdx(destination)
    return destination


# Exit codes the observer refuses with, kept in step with tools/visio_observe.ps1
# by test_the_drivers_exit_codes_match_the_observers.
_REFUSALS = {
    2: "no files to look at",
    3: "Visio is already running",
}


def _refusal(code: int, stderr: str) -> str:
    # Exit 0 with nothing on stdout means the observer died before it printed:
    # a terminating error unwinds past `exit $LASTEXITCODE`, which is then unset
    # and reads as success. Saying "exited 0" there sends the reader looking in
    # the wrong place entirely.
    reason = _REFUSALS.get(code) or ("the observer crashed before it reported" if code == 0 else f"the observer exited {code}")
    return f"{reason}.\n{stderr}" if stderr else reason


def observe(paths: list[str], *, timeout: int | None = None, allow_running: bool = False) -> dict:
    """Run Visio over copies of the given files and return the raw observation payload.

    The budget covers the whole batch, so it scales with the batch: one Visio
    start plus a per-file allowance. A fixed figure fails the corpus and is
    wastefully generous for one file.
    """
    budget = timeout if timeout is not None else 60 + 20 * len(paths)
    with _staged(paths) as (root, _):
        return _observe_directory(root, timeout=budget, allow_running=allow_running)


def _visio_pids() -> set[int]:
    result = subprocess.run(
        [
            _shell(),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-Process -Name VISIO -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return {int(line) for line in result.stdout.split() if line.strip().isdigit()}


def _reap_visio(before: set[int]) -> list[int]:
    """Kill Visio processes that were not running before we started."""
    leaked = sorted(_visio_pids() - before)
    for pid in leaked:
        subprocess.run(
            [_shell(), "-NoProfile", "-NonInteractive", "-Command", f"Stop-Process -Id {pid} -Force"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    return leaked


def _observe_directory(root: str, *, timeout: int, allow_running: bool) -> dict:
    before = _visio_pids()
    # -Command rather than -File: with -File every argument arrives as a separate
    # literal string, so a `string[]` parameter only ever receives its first
    # element and the rest fail to bind. -Command hands PowerShell one expression
    # to parse, which is the only way to pass it a list.
    #
    # The repository is usually a UNC path from Windows' point of view (that is
    # what a WSL checkout looks like), and the default RemoteSigned policy
    # refuses to run any script from one. The bypass applies to this child
    # process and nothing else; the script it runs is this repository's own.
    # `; exit $LASTEXITCODE` because `exit` inside a script invoked with `&` sets
    # that variable but not the shell's own status: without it every refusal
    # reaches Python as a generic exit 1, and the codes above would mean nothing.
    switches = " -AllowRunningVisio" if allow_running else ""
    expression = f"& {_quote(_windows_path(OBSERVER))} -Path {_quote(_windows_path(root))}{switches}; exit $LASTEXITCODE"
    command = [_shell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", expression]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as expired:
        # Killing PowerShell does not kill Visio: `New-Object -ComObject` starts
        # VISIO.EXE out of process, so the observer's own cleanup never runs and
        # an invisible Visio is left holding the staged files. Every later run
        # then refuses with "Visio is already running" - the exact misdiagnosis
        # the lifecycle rules exist to prevent, self-inflicted. Reap it here.
        killed = _reap_visio(before)
        raise VisioUnavailable(
            f"Visio did not answer within {timeout}s and was killed"
            + (f" (stranded process {', '.join(map(str, killed))} also killed)" if killed else "")
            + ". Raise --timeout if the corpus is large, or open one of the files by hand: a modal "
            "dialog Visio raises outside its alert mechanism blocks until something dismisses it."
        ) from expired
    payload = result.stdout.strip()
    if not payload:
        raise VisioUnavailable(_refusal(result.returncode, result.stderr.strip()))
    try:
        return json.loads(payload)
    except json.JSONDecodeError as error:
        raise VisioUnavailable(f"the Visio observer produced output that is not JSON: {error}\n{payload[:400]}") from error


def _records(payload: dict) -> list[dict]:
    if payload.get("schema") != SCHEMA_VERSION:
        raise VisioUnavailable(f"the observer speaks schema {payload.get('schema')!r}, this driver reads {SCHEMA_VERSION}")
    return list(payload.get("documents", []))


def _verdict(record: dict, package: Observation, visio: Observation) -> tuple[bool, str]:
    differences = compare(package, visio)
    name = record["source"]["name"]
    if differences:
        return False, f"DIFFER {name}: {len(differences)} difference(s)\n" + _indent(format_differences(differences))
    shapes = sum(len(page.shapes) for page in package.pages)
    return True, f"AGREE  {name}: {len(package.pages)} page(s), {shapes} shape(s) - Visio sees the same document"


def _indent(text: str) -> str:
    return "\n".join(f"    {line}" for line in text.splitlines())


def _report(record: dict, package_path: str) -> tuple[bool, str]:
    name = record["source"]["name"]
    if record["status"] == "locked":
        return False, (
            f"LOCKED {name}: Visio could not open it because something else holds it.\n"
            f"    This is not a corrupt file. Close Visio, or let the observer's cleanup run.\n"
            f"{_indent(record['error'])}"
        )
    if record["status"] != "opened":
        return False, f"ERROR  {name}: Visio refused the file.\n{_indent(record.get('error') or '')}"
    package = observation_from_package(package_path)
    if package.source_sha256 != record["source"]["sha256"]:
        # Visio was shown a staged copy; this is the file we just read. If the
        # two are not the same bytes then the difference list below describes
        # two different documents, and every entry in it is noise that reads
        # like a finding.
        return False, (
            f"MISMATCH {name}: Visio was shown {record['source']['sha256'][:12]} but "
            f"{package_path} hashes {package.source_sha256[:12]}. Refusing to compare them."
        )
    return _verdict(record, package, observation_from_com_json(record))


def command_check(paths: list[str], *, allow_running: bool = False) -> int:
    payload = observe(paths, allow_running=allow_running)
    by_name = {os.path.basename(path): path for path in paths}
    failures = 0
    for record in _records(payload):
        agreed, text = _report(record, by_name[record["source"]["name"]])
        print(text)
        failures += 0 if agreed else 1
    print(f"\n{len(by_name) - failures}/{len(by_name)} agree with Visio {payload['viewer']['version']}")
    return 1 if failures else 0


def command_record(
    paths: list[str], *, into: str = RECORDINGS, allow_running: bool = False, transform: str = "roundtrip"
) -> int:
    with tempfile.TemporaryDirectory(prefix="vsdxkit-transform-") as workspace:
        subjects = {}
        for path in paths:
            name = os.path.basename(path)
            subject = _apply_transform(transform, path, os.path.join(workspace, name))
            subjects[name] = (path, subject)
        payload = observe([subject for _, subject in subjects.values()], allow_running=allow_running)

        os.makedirs(into, exist_ok=True)
        written = 0
        for record in _records(payload):
            name = record["source"]["name"]
            origin = subjects[name][0]
            if record["status"] != "opened":
                print(f"SKIP   {name}: {record['status']} - {record.get('error')}", file=sys.stderr)
                continue
            # What is stored is the hash of the *input*, not of the file Visio
            # opened. The output changes whenever the writer changes, which is
            # the whole point; the input is what has to stay put for the
            # recording to still be about the same thing.
            record["source"] = {
                "name": name,
                "sha256": observation_from_package(origin).source_sha256,
                "transform": transform,
            }
            record["viewer"] = payload["viewer"]
            destination = os.path.join(into, f"{os.path.splitext(name)[0]}.json")
            with open(destination, "w", encoding="utf-8") as handle:
                json.dump(record, handle, indent=2, sort_keys=True)
                handle.write("\n")
            print(f"RECORD {name} ({transform}) -> {os.path.relpath(destination, REPO)}")
            written += 1
        return 0 if written else 1


def command_replay(recordings: list[str], *, corpus: str) -> int:
    """Re-derive each package's claim today and compare it to the recorded truth."""
    failures = 0
    for recording in recordings:
        with open(recording, encoding="utf-8") as handle:
            record = json.load(handle)
        name = record["source"]["name"]
        package_path = os.path.join(corpus, name)
        if not os.path.exists(package_path):
            print(f"ORPHAN {name}: recorded, but {package_path} no longer exists")
            failures += 1
            continue
        if observation_from_package(package_path).source_sha256 != record["source"]["sha256"]:
            print(
                f"STALE  {name}: the input has changed since Visio last saw it.\n"
                f"    Re-record on a Windows machine: python tools/visio_verify.py record {package_path}"
            )
            failures += 1
            continue
        transform = record["source"].get("transform", "none")
        with tempfile.TemporaryDirectory(prefix="vsdxkit-replay-") as workspace:
            # Re-run the writer *now*. This is what makes replay a gate on the
            # library rather than on its own reader: the bytes being described
            # were produced by today's code, not read back out of git.
            subject = _apply_transform(transform, package_path, os.path.join(workspace, name))
            agreed, text = _verdict(record, observation_from_package(subject), observation_from_com_json(record))
        print(text)
        failures += 0 if agreed else 1
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subcommands = parser.add_subparsers(dest="command", required=True)

    # An instance the developer already has open may hold a lock on the files
    # under test and carries settings this harness did not choose, so it is
    # refused by default rather than worked around silently.
    running = dict(
        action="store_true",
        dest="allow_running",
        help="proceed even if Visio is already running",
    )

    check = subcommands.add_parser("check", help="open in Visio now and report differences")
    check.add_argument("paths", nargs="+")
    check.add_argument("--allow-running-visio", **running)

    record = subcommands.add_parser("record", help="open in Visio now and save what it reported")
    record.add_argument("paths", nargs="+")
    record.add_argument("--into", default=RECORDINGS)
    record.add_argument(
        "--transform",
        default="roundtrip",
        choices=TRANSFORMS,
        help="what Visio is shown: the library's output for this file, or the file itself",
    )
    record.add_argument("--allow-running-visio", **running)

    replay = subcommands.add_parser("replay", help="compare today's packages to saved observations, without Visio")
    replay.add_argument("recordings", nargs="+")
    replay.add_argument("--corpus", default=os.path.join(REPO, "tests"), help="where the .vsdx files live")

    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "check":
            return command_check(arguments.paths, allow_running=arguments.allow_running)
        if arguments.command == "record":
            return command_record(
                arguments.paths,
                into=arguments.into,
                allow_running=arguments.allow_running,
                transform=arguments.transform,
            )
        return command_replay(arguments.recordings, corpus=arguments.corpus)
    except VisioUnavailable as error:
        print(f"Visio is not usable from here: {error}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
