"""Run the Visio differential oracle: compare what a package claims to what Visio does.

    python tools/visio_verify.py check  out/probe.vsdx [...]   # live Visio, diff, report
    python tools/visio_verify.py record out/probe.vsdx [...]   # live Visio, save the observation
    python tools/visio_verify.py replay tests/fixtures/visio_observations/*.json

Why three verbs rather than one
-------------------------------
Visio is a slow, stateful, Windows-only oracle, and the machine that has it is
not the machine CI runs on. An oracle that expensive is worth recording: `record`
captures what Visio did, `replay` re-derives the package's claim from the file
today and compares it to that recording. So a change that alters what the library
writes is caught on Linux, in CI, with no Visio anywhere - what cannot be caught
that way is a change in what *Visio* does with the same bytes, and nothing can
catch that except running Visio again.

A recording is therefore evidence with an expiry date, and `replay` says so out
loud: an observation whose source file no longer hashes the same is reported as
stale and needs re-recording. It is never quietly treated as a pass. A harness
that goes green on a comparison it did not make is worse than no harness.
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
        for path in paths:
            name = os.path.basename(path)
            if name in staged:
                raise VisioUnavailable(
                    f"two inputs are both named {name!r} ({staged[name]} and {path}). "
                    "Observations are keyed by filename, so rename one of them."
                )
            destination = os.path.join(root, name)
            shutil.copy2(path, destination)
            staged[name] = path
        yield root, staged
    finally:
        shutil.rmtree(root, ignore_errors=True)


# Exit codes the observer refuses with, kept in step with tools/visio_observe.ps1.
# They exist so that "the machine is not in a state to be measured" never gets
# mistaken for "the file is bad" - a confusion that costs an afternoon, because
# a stranded Visio process reports as a corrupt file.
_REFUSALS = {
    2: "no files to look at",
    3: "Visio is already running",
}


def _refusal(code: int, stderr: str) -> str:
    reason = _REFUSALS.get(code, f"the observer exited {code}")
    return f"{reason}.\n{stderr}" if stderr else reason


def observe(paths: list[str], *, timeout: int = 300, allow_running: bool = False) -> dict:
    """Run Visio over copies of the given files and return the raw observation payload."""
    with _staged(paths) as (root, _):
        return _observe_directory(root, timeout=timeout, allow_running=allow_running)


def _observe_directory(root: str, *, timeout: int, allow_running: bool) -> dict:
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
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
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
    return _verdict(record, observation_from_package(package_path), observation_from_com_json(record))


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


def command_record(paths: list[str], *, into: str = RECORDINGS, allow_running: bool = False) -> int:
    payload = observe(paths, allow_running=allow_running)
    os.makedirs(into, exist_ok=True)
    written = 0
    for record in _records(payload):
        name = record["source"]["name"]
        if record["status"] != "opened":
            print(f"SKIP   {name}: {record['status']} - {record.get('error')}", file=sys.stderr)
            continue
        # the absolute path is the one field that is true only on the machine
        # that recorded it, so it does not go into a file other machines read
        record["source"].pop("path", None)
        record["viewer"] = payload["viewer"]
        destination = os.path.join(into, f"{os.path.splitext(name)[0]}.json")
        with open(destination, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(f"RECORD {name} -> {os.path.relpath(destination, REPO)}")
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
        package = observation_from_package(package_path)
        if package.source_sha256 != record["source"]["sha256"]:
            print(
                f"STALE  {name}: the file has changed since Visio last saw it.\n"
                f"    Re-record on a Windows machine: python tools/visio_verify.py record {package_path}"
            )
            failures += 1
            continue
        agreed, text = _verdict(record, package, observation_from_com_json(record))
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
    record.add_argument("--allow-running-visio", **running)

    replay = subcommands.add_parser("replay", help="compare today's packages to saved observations, without Visio")
    replay.add_argument("recordings", nargs="+")
    replay.add_argument("--corpus", default=os.path.join(REPO, "tests"), help="where the .vsdx files live")

    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "check":
            return command_check(arguments.paths, allow_running=arguments.allow_running)
        if arguments.command == "record":
            return command_record(arguments.paths, into=arguments.into, allow_running=arguments.allow_running)
        return command_replay(arguments.recordings, corpus=arguments.corpus)
    except VisioUnavailable as error:
        print(f"Visio is not usable from here: {error}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
