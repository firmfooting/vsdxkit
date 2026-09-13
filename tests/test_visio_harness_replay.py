"""Replay recorded Visio observations, on a machine with no Visio.

Visio runs on one Windows desktop; this suite runs everywhere. `record` captures
what Visio made of a file vsdxkit wrote, and replay runs the writer again today
and compares its output to that recording. A change to what the library writes
is therefore caught in ordinary CI, and only a change in what Visio does with
unchanged bytes needs the desktop again.

Recording the writer's *output* is what makes this a gate at all. A recording of
a fixture as it sits in git would freeze the bytes, so the reader could only
return what it returned at record time and the comparison would prove nothing
about the library. The tests below check both that the gate fires and that a
recording which can no longer be trusted fails instead of passing.
"""

import importlib.util
import json
import os
import pathlib
import re
import shutil

import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "tools")
RECORDINGS = os.path.join(os.path.dirname(os.path.realpath(__file__)), "fixtures", "visio_observations")


def _load_verify():
    spec = importlib.util.spec_from_file_location("visio_verify", os.path.join(TOOLS, "visio_verify.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def verify():
    return _load_verify()


def _recordings() -> list[str]:
    if not os.path.isdir(RECORDINGS):
        return []
    return sorted(os.path.join(RECORDINGS, name) for name in os.listdir(RECORDINGS) if name.endswith(".json"))


def test_there_are_recordings_to_replay():
    """Guards every test below: without this they would fail obscurely or vacuously."""
    assert _recordings(), f"no recorded Visio observations in {RECORDINGS}"


def test_every_recorded_fixture_still_matches_what_visio_saw(verify, basedir, capsys):
    """The regression gate: what vsdxkit writes today still agrees with Visio.

    Each recording replays by running the writer over its input fixture again,
    so this fails when a change to the library alters the shapes, groups or glue
    in output a real Visio has already vouched for.
    """
    exit_code = verify.command_replay(_recordings(), corpus=basedir)

    assert exit_code == 0, capsys.readouterr().out


def test_a_recording_whose_file_has_changed_is_refused_as_stale(verify, tmp_path, basedir, capsys):
    """A recording describes one exact file, identified by hash.

    Replaying it against a different file compares today's package to a Visio run
    that never saw it. That is not a weaker check, it is a meaningless one, so it
    has to fail rather than pass.
    """
    with open(_recordings()[0], encoding="utf-8") as handle:
        recording = json.load(handle)
    recording["source"]["sha256"] = "0" * 64
    stale = tmp_path / "stale.json"
    stale.write_text(json.dumps(recording), encoding="utf-8")

    exit_code = verify.command_replay([str(stale)], corpus=basedir)

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "STALE" in output
    assert "tools/visio_verify.py record" in output, "the failure has to give the command that fixes it"


def test_a_recording_whose_fixture_is_gone_is_refused(verify, tmp_path, capsys):
    """A fixture can be renamed or deleted; its recording must not quietly survive."""
    shutil.copy(_recordings()[0], tmp_path / "orphan.json")

    exit_code = verify.command_replay([str(tmp_path / "orphan.json")], corpus=str(tmp_path))

    assert exit_code == 1
    assert "ORPHAN" in capsys.readouterr().out


def test_a_recording_that_disagrees_with_the_package_fails_and_says_where(verify, basedir, tmp_path, capsys):
    """The path that matters, and the only one that ever reports a real defect.

    Everything else here checks that an untrustworthy recording is refused. This
    checks the opposite: a recording that is perfectly valid, describing output
    the writer no longer produces. Drop one shape from the recorded Visio view
    and replay has to notice, fail, and name the shape.
    """
    recording = json.loads(pathlib.Path(_recordings()[0]).read_text(encoding="utf-8"))
    dropped = recording["pages"][0]["shapes"].pop()
    doctored = tmp_path / "doctored.json"
    doctored.write_text(json.dumps(recording), encoding="utf-8")

    exit_code = verify.command_replay([str(doctored)], corpus=basedir)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "DIFFER" in output
    assert f"shape {dropped['id']}" in output


def test_the_drivers_exit_codes_match_the_observers(verify):
    """The two halves agree on what each refusal code means.

    `visio_observe.ps1` refuses with a numeric code and `visio_verify.py` turns
    that number into a sentence. Nothing but this test links them, so a new
    refusal added on one side shows up on the other as "the observer exited 4".
    """
    observer = pathlib.Path(TOOLS, "visio_observe.ps1").read_text(encoding="utf-8")
    # The code is the last token of the call, whether the message is a single
    # quoted string on one line or a parenthesised expression spanning several.
    inline = re.findall(r"^\s*Write-Refusal\s+.*?\s(\d+)\s*$", observer, re.MULTILINE)
    wrapped = re.findall(r"^\s*\)\s+(\d+)\s*$", observer, re.MULTILINE)
    refused = {int(code) for code in inline + wrapped}

    assert refused, "no Write-Refusal call sites found; has the observer been renamed?"
    assert refused == set(verify._REFUSALS), (
        f"the observer refuses with {sorted(refused)} but the driver explains {sorted(verify._REFUSALS)}"
    )
