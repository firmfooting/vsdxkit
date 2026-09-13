"""Replay recorded Visio observations, on a machine with no Visio.

Visio runs on one Windows desktop; this suite runs everywhere. `tools/visio_verify.py
record` captures what Visio did with a fixture, and this file re-derives what the
fixture claims *today* and compares the two. A change to what the library writes
is therefore caught in ordinary CI, and only a change in what Visio does with
unchanged bytes needs the desktop again.

The recordings are evidence with an expiry date. The tests below exist mostly to
prove the expiry works: a harness that goes green on a comparison it did not make
is worse than no harness at all, because it is believed.
"""

import importlib.util
import json
import os
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
    """Guards every test below, all of which pass trivially over an empty list."""
    assert _recordings(), f"no recorded Visio observations in {RECORDINGS}"


def test_every_recorded_fixture_still_matches_what_visio_saw(verify, basedir, capsys):
    """The regression gate: what vsdxkit writes today still agrees with Visio.

    Fails if a change alters the shapes, groups or glue in a fixture that a real
    Visio has already been asked about.
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
    assert "record" in output, "the failure has to say how to fix it"


def test_a_recording_whose_fixture_is_gone_is_refused(verify, tmp_path, capsys):
    """A fixture can be renamed or deleted; its recording must not quietly survive."""
    shutil.copy(_recordings()[0], tmp_path / "orphan.json")

    exit_code = verify.command_replay([str(tmp_path / "orphan.json")], corpus=str(tmp_path))

    assert exit_code == 1
    assert "ORPHAN" in capsys.readouterr().out
