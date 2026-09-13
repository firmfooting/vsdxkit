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
from helpers.visio_observation import PLACEMENT_CELLS, SCHEMA_VERSION, observation_from_package

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
    so this fails when a change to the library alters the shapes, groups, glue or
    placement in output a real Visio has already vouched for.
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


def _agreeing_recording(package_path: str) -> dict:
    """A recording of the current schema that agrees with the package, to be spoilt.

    Built from the package rather than taken from the corpus on purpose. Its
    callers below are about what replay does with a *valid* recording that no
    longer matches; a real recording would make them fail for a different reason
    every time the schema moves, which is exactly when they need to work.

    What it cannot do is stand in for a recording. The "Visio" side here comes
    from the package, through the same reader, so its callers exercise the
    plumbing between replay and the comparison and say nothing about whether
    Visio agrees with any of it. Only `record` on the Windows desktop does that.
    """
    observation = observation_from_package(package_path)
    return {
        "schema": SCHEMA_VERSION,
        "status": "opened",
        "error": None,
        "source": {
            "name": os.path.basename(package_path),
            "sha256": observation.source_sha256,
            "transform": "none",
        },
        "pages": [
            {
                "index": page.index,
                "name": page.name,
                "background": page.background,
                "connects": [
                    {
                        "from_shape": connect.from_shape,
                        "from_cell": connect.from_cell,
                        "to_shape": connect.to_shape,
                        "to_cell": connect.to_cell,
                    }
                    for connect in page.connects
                ],
                "shapes": [
                    {
                        "id": shape.id,
                        "parent_id": shape.parent_id,
                        "name": shape.name,
                        "cells": [
                            {"name": cell.name, "formula": cell.formula, "result": cell.constant} for cell in shape.cells
                        ],
                    }
                    for shape in page.shapes
                ],
            }
            for page in observation.pages
        ],
    }


def test_a_recording_that_disagrees_with_the_package_fails_and_says_where(verify, basedir, tmp_path, capsys):
    """The path that matters, and the only one that ever reports a real defect.

    Everything else here checks that an untrustworthy recording is refused. This
    checks the opposite: a recording that is perfectly valid, describing output
    the writer no longer produces. Drop one shape from the recorded Visio view
    and replay has to notice, fail, and name the shape.
    """
    recording = _agreeing_recording(os.path.join(basedir, "test4_connectors.vsdx"))
    dropped = recording["pages"][0]["shapes"].pop()
    doctored = tmp_path / "doctored.json"
    doctored.write_text(json.dumps(recording), encoding="utf-8")

    exit_code = verify.command_replay([str(doctored)], corpus=basedir)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "DIFFER" in output
    assert f"shape {dropped['id']}" in output


def test_a_shape_that_moved_a_millimetre_fails_and_names_the_shape_and_the_cell(verify, basedir, tmp_path, capsys):
    """What the placement cells are for.

    Ids, grouping and glue are all identical when a rectangle slides a millimetre
    to the left, so every other check in this file passes on a file whose content
    has visibly moved.
    """
    fixture = os.path.join(basedir, "test4_connectors.vsdx")
    recording = _agreeing_recording(fixture)
    shape = recording["pages"][0]["shapes"][0]
    pin_x = next(cell for cell in shape["cells"] if cell["name"] == "PinX")
    # one millimetre in internal units, which are inches
    pin_x["result"] += 1 / 25.4
    pin_x["formula"] = repr(pin_x["result"])
    doctored = tmp_path / "moved.json"
    doctored.write_text(json.dumps(recording), encoding="utf-8")

    exit_code = verify.command_replay([str(doctored)], corpus=basedir)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "DIFFER" in output
    assert f"shape {shape['id']} cell PinX" in output


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


def test_a_recording_written_under_another_schema_is_refused_not_guessed_at(verify, tmp_path, basedir, capsys):
    """A recording outlives the code that reads it, and must not be reinterpreted.

    When the observation grows a field, every recording made before it is silent
    about that field. Reading one anyway would report agreement on a comparison
    that was never made - a green tick spent on nothing - so replay has to say so
    and fail, naming the command that fixes it.
    """
    with open(_recordings()[0], encoding="utf-8") as handle:
        recording = json.load(handle)
    recording["schema"] = 0
    older = tmp_path / "older.json"
    older.write_text(json.dumps(recording), encoding="utf-8")

    exit_code = verify.command_replay([str(older)], corpus=basedir)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "SCHEMA" in output
    assert "tools/visio_verify.py record" in output, "the failure has to give the command that fixes it"


def _observer_source() -> str:
    return pathlib.Path(TOOLS, "visio_observe.ps1").read_text(encoding="utf-8")


def test_the_two_sides_ask_for_the_same_placement_cells():
    """Both halves of a differential oracle have to be looking at the same cells.

    A cell named on one side only is not compared at all: the COM side would
    report something nobody reads, or the package side would report a cell the
    recording is silent about and every shape would fail on a cell that was never
    extracted. Nothing but this test links the two lists.
    """
    declaration = re.search(r"\$PlacementCells\s*=\s*@\((.*?)\)", _observer_source(), re.DOTALL)
    assert declaration, "no $PlacementCells list found; has the observer been renamed?"
    observed = tuple(re.findall(r"'([^']+)'", declaration.group(1)))

    assert observed == PLACEMENT_CELLS


def test_the_observer_and_the_reader_stamp_the_same_schema_version():
    """The stamp is what makes a stale recording refusable, so it has to be one number.

    If the observer writes a version the reader does not expect, every fresh
    recording is refused; if it writes one the reader expects but the payload no
    longer matches, nothing is refused at all.
    """
    stamped = re.search(r"^\$SchemaVersion\s*=\s*(\d+)", _observer_source(), re.MULTILINE)
    assert stamped, "no $SchemaVersion found; has the observer been renamed?"

    assert int(stamped.group(1)) == SCHEMA_VERSION
