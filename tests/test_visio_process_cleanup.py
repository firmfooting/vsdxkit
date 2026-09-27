"""The Visio tools kill only the Visio their own script started (#463).

Each script names the process its COM object runs in, the owner of Visio's
main window, and on the way out kills that one if Quit left it running. A
caller whose script timed out kills the one the script wrote to its
`-ProcessIdFile`. Any other Visio, a developer's opened while a long run was
under way included, is theirs, with their unsaved work in it.
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


KILL = "Get-Process -Id {} -ErrorAction SilentlyContinue | Where-Object ProcessName -eq 'VISIO' | Stop-Process -Force"


class _Powershell:
    """Stands in for `subprocess.run`, over the VISIO processes Windows would have.

    `visio` maps each running Visio's ID to whether it has a visible window.
    The script starts invisible Visio `spawned`, names it in its file only if
    `named`, and times out. A listing reads `visio`; a kill removes its Visio
    unless it is `unkillable`, and is kept.
    """

    def __init__(self, process_id_file: Path, visio: dict[int, bool], spawned: int | None = None, *, named: bool = True):
        self.process_id_file = process_id_file
        self.visio = dict(visio)
        self.spawned = spawned
        self.named = named
        self.unkillable: set[int] = set()
        self.kills: list[str] = []

    def __call__(self, command, **kwargs):
        expression = command[-1]
        if "-ProcessIdFile" in expression:
            assert f"-ProcessIdFile '{self.process_id_file}'" in expression
            if self.spawned is not None:
                self.visio[self.spawned] = False
                if self.named:
                    self.process_id_file.write_text(f"{self.spawned}\r\n", encoding="ascii")
            raise subprocess.TimeoutExpired(command, kwargs.get("timeout", 0))
        if expression.startswith("Get-Process -Name VISIO"):
            invisible_only = "MainWindowHandle -eq 0" in expression
            ids = [pid for pid, visible in self.visio.items() if not (invisible_only and visible)]
            return subprocess.CompletedProcess(command, 0, "\n".join(map(str, ids)), "")
        self.kills.append(expression)
        killed = int(expression.split()[2])
        if killed not in self.unkillable:
            self.visio.pop(killed, None)
        return subprocess.CompletedProcess(command, 0, "", "")


def test_the_visio_a_script_started_is_read_from_the_file_it_wrote(verify, tmp_path):
    written = tmp_path / "visio.pid"
    assert verify._started_process_id(written) is None
    written.write_text("", encoding="utf-8")
    assert verify._started_process_id(written) is None
    written.write_text("4242\r\n", encoding="utf-8")
    assert verify._started_process_id(written) == 4242


def test_stopping_kills_the_named_visio_and_no_other(verify, tmp_path, monkeypatch):
    written = tmp_path / "visio.pid"
    written.write_text("4242", encoding="ascii")
    powershell = _Powershell(written, {7: True, 4242: False, 5151: True})
    monkeypatch.setattr(verify.subprocess, "run", powershell)

    assert verify._stop_started_visio(written, {7}) == "; so was the Visio it started, process 4242"
    assert powershell.kills == [KILL.format(4242)]
    assert set(powershell.visio) == {7, 5151}


def test_a_kill_that_did_not_take_is_not_reported_as_one(verify, tmp_path, monkeypatch):
    written = tmp_path / "visio.pid"
    written.write_text("4242", encoding="ascii")
    powershell = _Powershell(written, {4242: False})
    powershell.unkillable = {4242}
    monkeypatch.setattr(verify.subprocess, "run", powershell)

    assert "process 4242, could not be killed" in verify._stop_started_visio(written, set())


def test_stopping_before_the_script_named_its_visio_kills_the_one_invisible_visio_that_started(verify, tmp_path, monkeypatch):
    """COM activation can hang with VISIO.EXE started and the file not yet written; the script's Visio has no window."""
    powershell = _Powershell(tmp_path / "visio.pid", {7: True, 4242: False, 5151: True})
    monkeypatch.setattr(verify.subprocess, "run", powershell)

    assert verify._stop_started_visio(tmp_path / "visio.pid", {7}) == "; so was the Visio it started, process 4242"
    assert powershell.kills == [KILL.format(4242)]


def test_a_visio_the_developer_opened_is_never_taken_for_an_unnamed_one(verify, tmp_path, monkeypatch):
    """The only new Visio is not proof it is the script's: a developer's has a window, and is left alone (#464)."""
    powershell = _Powershell(tmp_path / "visio.pid", {7: True, 5151: True})
    monkeypatch.setattr(verify.subprocess, "run", powershell)

    assert verify._stop_started_visio(tmp_path / "visio.pid", {7}) == "; it had not started Visio"
    assert powershell.kills == []


def test_stopping_before_the_script_named_its_visio_kills_none_of_several_invisible_ones(verify, tmp_path, monkeypatch):
    """Which is the script's is not known: none is killed, and each is named."""
    powershell = _Powershell(tmp_path / "visio.pid", {7: True, 4242: False, 5151: False})
    monkeypatch.setattr(verify.subprocess, "run", powershell)

    message = verify._stop_started_visio(tmp_path / "visio.pid", {7})

    assert message.startswith("; invisible Visio processes 4242, 5151 started while it ran")
    assert powershell.kills == []


def test_an_observation_that_times_out_kills_only_the_visio_it_started(verify, tmp_path, monkeypatch):
    """It killed every Visio not running when it began, a developer's opened meanwhile included."""
    powershell = _Powershell(tmp_path / "visio.pid", {7: True}, spawned=4242)
    monkeypatch.setattr(verify.subprocess, "run", powershell)

    with pytest.raises(verify.VisioUnavailable, match="process 4242"):
        verify._observe_directory(str(tmp_path), timeout=1, allow_running=False)

    assert powershell.kills == [KILL.format(4242)]
    assert set(powershell.visio) == {7}


def test_a_cell_check_that_times_out_before_naming_its_visio_kills_only_that_one(verify, tmp_path, monkeypatch):
    tool = _load("writes_land_cases")
    powershell = _Powershell(tmp_path / "visio.pid", {7: True}, spawned=4242, named=False)
    monkeypatch.setattr(verify.subprocess, "run", powershell)
    monkeypatch.setattr(verify, "_staged", lambda paths: contextlib.nullcontext((str(tmp_path), {})))

    with pytest.raises(verify.VisioUnavailable, match="process 4242"):
        tool._ask_visio(TOOLS, [], {}, verify)

    assert powershell.kills == [KILL.format(4242)]
    assert set(powershell.visio) == {7}


@pytest.mark.parametrize("script", SCRIPTS)
def test_each_script_kills_only_the_visio_its_own_com_object_runs_in(script):
    """Not every Visio that started after the script did: the start-time rule took a developer's Visio too."""
    text = (TOOLS / script).read_text(encoding="utf-8")
    assert ". (Join-Path $PSScriptRoot 'visio_process.ps1')" in text
    assert "$ownProcessId = Register-OwnVisio -App $app -ProcessIdFile $ProcessIdFile" in text
    assert "[string]$ProcessIdFile" in text
    assert "Stop-OwnVisio -ProcessId $ownProcessId" in text
    # New-Object can start VISIO.EXE and throw before the script could name it (#464)
    assert "$ownProcessId = Find-StrandedVisio -Preexisting $preexisting" in text
    assert "function Get-VisioProcessIds" not in text, "one definition, in visio_process.ps1"
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
    # an unnamed Visio is taken only if it has no visible window, as a developer's has
    assert "$_.MainWindowHandle -eq 0" in text


def test_the_helper_type_is_added_once_per_powershell_session():
    """A script run twice from one prompt dot-sources the helper twice, and a type cannot be added twice."""
    text = (TOOLS / "visio_process.ps1").read_text(encoding="utf-8")
    assert "if (-not ('VsdxKit.Window' -as [type])) {" in text
