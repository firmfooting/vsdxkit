"""The Visio tools kill only the Visio their own script started (#463).

Each script records the process its COM object runs in, `Application.ProcessID`,
and on the way out kills that one if Quit left it running. A caller whose
script timed out kills the one the script wrote to its `-ProcessIdFile`. Any
other Visio, a developer's opened while a long run was under way included,
is theirs, with their unsaved work in it.
"""

import contextlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
SCRIPTS = ("visio_cells.ps1", "visio_observe.ps1", "visio_export.ps1")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def verify(monkeypatch):
    """visio_verify, with PowerShell and the Windows paths it would translate to stubbed out: no Visio here."""
    module = _load("visio_verify")
    monkeypatch.setattr(module, "_shell", lambda: "powershell.exe")
    monkeypatch.setattr(module, "_windows_path", lambda path: path)
    return module


class _Powershell:
    """Stands in for `subprocess.run`: the script times out, having recorded Visio `process_id`; every other command is kept."""

    def __init__(self, process_id_file: Path, process_id: int | None):
        self.process_id_file = process_id_file
        self.process_id = process_id
        self.commands: list[str] = []

    def __call__(self, command, **kwargs):
        expression = command[-1]
        if "-ProcessIdFile" in expression:
            assert f"-ProcessIdFile '{self.process_id_file}'" in expression
            if self.process_id is not None:
                self.process_id_file.write_text(f"{self.process_id}\r\n", encoding="ascii")
            raise subprocess.TimeoutExpired(command, kwargs.get("timeout", 0))
        self.commands.append(expression)
        return subprocess.CompletedProcess(command, 0, "", "")


def test_the_visio_a_script_started_is_read_from_the_file_it_wrote(verify, tmp_path):
    written = tmp_path / "visio.pid"
    assert verify._started_process_id(written) is None
    written.write_text("", encoding="utf-8")
    assert verify._started_process_id(written) is None
    written.write_text("4242\r\n", encoding="utf-8")
    assert verify._started_process_id(written) == 4242


def test_stopping_kills_the_recorded_visio_and_no_other(verify, tmp_path, monkeypatch):
    written = tmp_path / "visio.pid"
    written.write_text("4242", encoding="ascii")
    powershell = _Powershell(written, None)
    monkeypatch.setattr(verify.subprocess, "run", powershell)

    assert verify._stop_started_visio(written) == 4242
    assert powershell.commands == [verify._stop_visio_command(4242)]


def test_stopping_before_the_script_recorded_a_visio_kills_nothing(verify, tmp_path, monkeypatch):
    """A script killed before its COM object existed started no Visio of its own."""
    powershell = _Powershell(tmp_path / "visio.pid", None)
    monkeypatch.setattr(verify.subprocess, "run", powershell)

    assert verify._stop_started_visio(tmp_path / "visio.pid") is None
    assert powershell.commands == []


def test_an_observation_that_times_out_kills_only_the_visio_it_started(verify, tmp_path, monkeypatch):
    """It killed every Visio not running when it began, a developer's opened meanwhile included."""
    powershell = _Powershell(tmp_path / "visio.pid", 4242)
    monkeypatch.setattr(verify.subprocess, "run", powershell)

    with pytest.raises(verify.VisioUnavailable, match="process 4242"):
        verify._observe_directory(str(tmp_path), timeout=1, allow_running=False)

    assert powershell.commands == [verify._stop_visio_command(4242)]


def test_a_cell_check_that_times_out_kills_only_the_visio_it_started(verify, tmp_path, monkeypatch):
    tool = _load("writes_land_cases")
    powershell = _Powershell(tmp_path / "visio.pid", 4242)
    monkeypatch.setattr(verify.subprocess, "run", powershell)
    monkeypatch.setattr(verify, "_staged", lambda paths: contextlib.nullcontext((str(tmp_path), {})))

    with pytest.raises(verify.VisioUnavailable, match="process 4242"):
        tool._ask_visio(TOOLS, [], {}, verify)

    assert powershell.commands == [verify._stop_visio_command(4242)]


def test_the_kill_stops_a_process_only_while_it_is_a_visio(verify):
    assert verify._stop_visio_command(4242) == (
        "Get-Process -Id 4242 -ErrorAction SilentlyContinue | Where-Object ProcessName -eq 'VISIO' | Stop-Process -Force"
    )


@pytest.mark.parametrize("script", SCRIPTS)
def test_each_script_kills_only_the_visio_its_own_com_object_runs_in(script):
    """Not every Visio that started after the script did: the start-time rule took a developer's Visio too."""
    text = (TOOLS / script).read_text(encoding="utf-8")
    assert ". (Join-Path $PSScriptRoot 'visio_process.ps1')" in text
    assert "$ownProcessId = Get-OwnProcessId -App $app" in text
    assert "[string]$ProcessIdFile" in text
    assert "Stop-OwnVisio -ProcessId $ownProcessId" in text
    assert "$app.ProcessID" not in text
    assert "StartTime" not in text
    assert "Stop-Process" not in text


def test_a_visio_is_named_by_the_process_that_owns_its_window():
    """Visio 16's `Application.ProcessID` names no process: 199300 against a VISIO.EXE of 39524.

    Killing by it missed the script's own Visio, and could kill whatever
    process had that ID. The owner of `WindowHandle32` is the VISIO.EXE, and
    is trusted, and killed, only while it is seen to be one.
    """
    text = (TOOLS / "visio_process.ps1").read_text(encoding="utf-8")
    assert "GetWindowThreadProcessId" in text
    assert "$App.WindowHandle32" in text
    assert "$process.ProcessName -ne 'VISIO'" in text
    assert "$leftover | Stop-Process -Force" in text
