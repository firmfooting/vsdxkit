"""The Visio tools kill only the Visio their own script started (#463).

Each script names the process its COM object runs in, the owner of Visio's
main window, and on the way out kills that one if Quit left it running. A
caller whose script timed out kills the one the script wrote to its
`-ProcessIdFile`. Any other Visio, a developer's opened while a long run was
under way included, is theirs, with their unsaved work in it.

A process is named by its ID and the time it started: Windows reuses IDs, so
once the script's Visio has gone its ID can be a later process's, another
Visio's among them.
"""

import contextlib
import importlib.util
import re
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


KILL = (
    "Get-Process -Id {} -ErrorAction SilentlyContinue | Where-Object {{ $_.ProcessName -eq 'VISIO' -and "
    "$_.StartTime.ToUniversalTime().Ticks -eq {} }} | Stop-Process -Force"
)
KILL_UNNAMED = KILL.replace(" }} |", " -and $_.MainWindowHandle -eq 0 }} |")
"""The kill of a Visio the script never named: taken for its own only while it still has no window."""


def _started(process_id: int) -> int:
    """When the fake's Visio `process_id` started, in ticks, unless a test says otherwise."""
    return process_id * 1000


class _Powershell:
    """Stands in for `subprocess.run`, over the VISIO processes Windows would have.

    `visio` maps each running Visio's ID to whether it has a visible window;
    each started at `_started` of its ID unless `started` says otherwise.
    The script starts invisible Visio `spawned`, names it in its file only if
    `named`, and times out. A listing reads `visio`; a kill removes the Visio
    with its ID and start time unless it is `unkillable`, or has a window where
    the kill asks for none, and is kept. Each Visio in `window_appears` shows
    its window as soon as it has been listed. While `hung`, every call after
    the script's times out as well.
    """

    def __init__(self, process_id_file: Path, visio: dict[int, bool], spawned: int | None = None, *, named: bool = True):
        self.process_id_file = process_id_file
        self.visio = dict(visio)
        self.started = {process_id: _started(process_id) for process_id in visio}
        self.spawned = spawned
        self.named = named
        self.unkillable: set[int] = set()
        self.window_appears: set[int] = set()
        self.hung = False
        self.script_ran = False
        self.kills: list[str] = []

    def __call__(self, command, **kwargs):
        expression = command[-1]
        if "-ProcessIdFile" in expression:
            assert f"-ProcessIdFile '{self.process_id_file}'" in expression
            self.script_ran = True
            if self.spawned is not None:
                self.visio[self.spawned] = False
                self.started[self.spawned] = _started(self.spawned)
                if self.named:
                    self.process_id_file.write_text(f"{self.spawned} {_started(self.spawned)}\r\n", encoding="ascii")
            raise subprocess.TimeoutExpired(command, kwargs.get("timeout", 0))
        if self.hung and self.script_ran:
            raise subprocess.TimeoutExpired(command, kwargs.get("timeout", 0))
        if expression.startswith("Get-Process -Name VISIO"):
            invisible_only = "MainWindowHandle -eq 0" in expression
            assert "$_.StartTime.ToUniversalTime().Ticks" in expression
            listed = [f"{pid} {self.started[pid]}" for pid, visible in self.visio.items() if not (invisible_only and visible)]
            for pid in self.window_appears & set(self.visio):
                self.visio[pid] = True
            return subprocess.CompletedProcess(command, 0, "\n".join(listed), "")
        self.kills.append(expression)
        process_id, started = map(int, re.search(r"-Id (\d+) .*\.Ticks -eq (\d+) ", expression).groups())
        windowless_only = "MainWindowHandle -eq 0" in expression
        if (
            self.started.get(process_id) == started
            and process_id not in self.unkillable
            and not (windowless_only and self.visio.get(process_id))
        ):
            self.visio.pop(process_id, None)
        return subprocess.CompletedProcess(command, 0, "", "")


def _visio(verify, process_id: int):
    return verify._Visio(process_id, _started(process_id))


def test_the_visio_a_script_started_is_read_from_the_file_it_wrote(verify, tmp_path):
    written = tmp_path / "visio.pid"
    assert verify._started_visio(written) is None
    written.write_text("", encoding="utf-8")
    assert verify._started_visio(written) is None
    written.write_text("4242\r\n", encoding="utf-8")
    assert verify._started_visio(written) is None, "an ID alone could be a later process's"
    written.write_text("4242 4242000\r\n", encoding="utf-8")
    assert verify._started_visio(written) == _visio(verify, 4242)


def test_stopping_kills_the_named_visio_and_no_other(verify, tmp_path, monkeypatch):
    written = tmp_path / "visio.pid"
    written.write_text("4242 4242000", encoding="ascii")
    powershell = _Powershell(written, {7: True, 4242: False, 5151: True})
    monkeypatch.setattr(verify.subprocess, "run", powershell)

    assert verify._stop_started_visio(written, {_visio(verify, 7)}) == "; so was the Visio it started, process 4242"
    assert powershell.kills == [KILL.format(4242, 4242000)]
    assert set(powershell.visio) == {7, 5151}


def test_a_later_process_with_the_named_visios_id_is_left_alone(verify, tmp_path, monkeypatch):
    """The script's Visio went, and Windows gave its ID to another Visio: that one is not the script's (#464)."""
    written = tmp_path / "visio.pid"
    written.write_text("4242 4242000", encoding="ascii")
    powershell = _Powershell(written, {4242: True})
    powershell.started[4242] = 9999000
    monkeypatch.setattr(verify.subprocess, "run", powershell)

    assert verify._stop_started_visio(written, set()) == "; the Visio it started, process 4242, had already ended"
    assert powershell.kills == []
    assert set(powershell.visio) == {4242}


def test_a_kill_that_did_not_take_is_not_reported_as_one(verify, tmp_path, monkeypatch):
    written = tmp_path / "visio.pid"
    written.write_text("4242 4242000", encoding="ascii")
    powershell = _Powershell(written, {4242: False})
    powershell.unkillable = {4242}
    monkeypatch.setattr(verify.subprocess, "run", powershell)

    assert "process 4242, could not be killed" in verify._stop_started_visio(written, set())


def test_stopping_before_the_script_named_its_visio_kills_the_one_invisible_visio_that_started(verify, tmp_path, monkeypatch):
    """COM activation can hang with VISIO.EXE started and the file not yet written; the script's Visio has no window."""
    powershell = _Powershell(tmp_path / "visio.pid", {7: True, 4242: False, 5151: True})
    monkeypatch.setattr(verify.subprocess, "run", powershell)

    assert (
        verify._stop_started_visio(tmp_path / "visio.pid", {_visio(verify, 7)})
        == "; so was the Visio it started, process 4242"
    )
    assert powershell.kills == [KILL_UNNAMED.format(4242, 4242000)]


def test_an_unnamed_visio_that_shows_a_window_before_the_kill_is_left_running(verify, tmp_path, monkeypatch):
    """A developer's Visio can be listed while it starts, before its window shows: the kill checks again (#464)."""
    powershell = _Powershell(tmp_path / "visio.pid", {7: True, 4242: False})
    powershell.window_appears = {4242}
    monkeypatch.setattr(verify.subprocess, "run", powershell)

    message = verify._stop_started_visio(tmp_path / "visio.pid", {_visio(verify, 7)})

    assert message.startswith("; Visio process 4242, taken for the one it started, showed a window")
    assert powershell.kills == [KILL_UNNAMED.format(4242, 4242000)]
    assert set(powershell.visio) == {7, 4242}


def test_a_visio_the_developer_opened_is_never_taken_for_an_unnamed_one(verify, tmp_path, monkeypatch):
    """The only new Visio is not proof it is the script's: a developer's has a window, and is left alone (#464)."""
    powershell = _Powershell(tmp_path / "visio.pid", {7: True, 5151: True})
    monkeypatch.setattr(verify.subprocess, "run", powershell)

    assert verify._stop_started_visio(tmp_path / "visio.pid", {_visio(verify, 7)}) == "; it had not started Visio"
    assert powershell.kills == []


def test_stopping_before_the_script_named_its_visio_kills_none_of_several_invisible_ones(verify, tmp_path, monkeypatch):
    """Which is the script's is not known: none is killed, and each is named."""
    powershell = _Powershell(tmp_path / "visio.pid", {7: True, 4242: False, 5151: False})
    monkeypatch.setattr(verify.subprocess, "run", powershell)

    message = verify._stop_started_visio(tmp_path / "visio.pid", {_visio(verify, 7)})

    assert message.startswith("; invisible Visio processes 4242, 5151 started while it ran")
    assert powershell.kills == []


def test_an_observation_that_times_out_kills_only_the_visio_it_started(verify, tmp_path, monkeypatch):
    """It killed every Visio not running when it began, a developer's opened meanwhile included."""
    powershell = _Powershell(tmp_path / "visio.pid", {7: True}, spawned=4242)
    monkeypatch.setattr(verify.subprocess, "run", powershell)

    with pytest.raises(verify.VisioUnavailable, match="process 4242"):
        verify._observe_directory(str(tmp_path), timeout=1, allow_running=False)

    assert powershell.kills == [KILL.format(4242, 4242000)]
    assert set(powershell.visio) == {7}


def test_a_cell_check_that_times_out_before_naming_its_visio_kills_only_that_one(verify, tmp_path, monkeypatch):
    tool = _load("writes_land_cases")
    powershell = _Powershell(tmp_path / "visio.pid", {7: True}, spawned=4242, named=False)
    monkeypatch.setattr(verify.subprocess, "run", powershell)
    monkeypatch.setattr(verify, "_staged", lambda paths: contextlib.nullcontext((str(tmp_path), {})))

    with pytest.raises(verify.VisioUnavailable, match="process 4242"):
        tool._ask_visio(TOOLS, [], {}, verify)

    assert powershell.kills == [KILL_UNNAMED.format(4242, 4242000)]
    assert set(powershell.visio) == {7}


def test_an_export_that_times_out_kills_only_the_visio_it_started(verify, tmp_path, monkeypatch, vsdx_copy):
    shots = _load("visio_shots")
    powershell = _Powershell(tmp_path / "staged" / "visio.pid", {7: True}, spawned=4242)
    monkeypatch.setattr(verify.subprocess, "run", powershell)
    (tmp_path / "staged").mkdir()
    monkeypatch.setattr(verify, "_staged", lambda paths: contextlib.nullcontext((str(tmp_path / "staged"), {})))
    job = ("candidate", shots._Case(stem="case", line="", page=1, triggers=()), vsdx_copy("test1.vsdx"))

    with pytest.raises(verify.VisioUnavailable, match=r"visio_export\.ps1 did not answer .* process 4242"):
        shots._shoot([job], 96, tmp_path / "work")

    assert powershell.kills == [KILL.format(4242, 4242000)]
    assert set(powershell.visio) == {7}


def test_a_cleanup_powershell_does_not_answer_still_gives_the_callers_message(verify, tmp_path, monkeypatch):
    """A machine wedged enough for the script to time out can hang the cleanup's own PowerShell too (#464)."""
    powershell = _Powershell(tmp_path / "visio.pid", {7: True}, spawned=4242)
    monkeypatch.setattr(verify.subprocess, "run", powershell)
    powershell.hung = True

    with pytest.raises(verify.VisioUnavailable, match=r"did not answer within 1s .* may still be running"):
        verify._observe_directory(str(tmp_path), timeout=1, allow_running=False)

    assert powershell.kills == []


@pytest.mark.parametrize("script", SCRIPTS)
def test_each_script_kills_only_the_visio_its_own_com_object_runs_in(script):
    """Not every Visio that started after the script did: the start-time rule took a developer's Visio too."""
    text = (TOOLS / script).read_text(encoding="utf-8")
    assert ". (Join-Path $PSScriptRoot 'visio_process.ps1')" in text
    assert "$ownVisio = Register-OwnVisio -App $app -ProcessIdFile $ProcessIdFile" in text
    assert "[string]$ProcessIdFile" in text
    assert "Stop-OwnVisio -Visio $ownVisio" in text
    # New-Object can start VISIO.EXE and throw before the script could name it (#464)
    assert "$ownVisio = Find-StrandedVisio -Preexisting $preexisting" in text
    # by ID and start time: a Visio that was running can go, and this script's get its ID (#464)
    assert "$preexisting = @(Get-VisioIdentities)" in text
    # a forced kill is the event that tells a locked file from a Visio crash
    assert "if ($null -ne $ownVisio -and (Stop-OwnVisio -Visio $ownVisio)) {" in text
    assert 'Write-Diagnostic "Visio process $($ownVisio.Id) outlived Quit(); killed it' in text
    assert "function Get-VisioIdentities" not in text, "one definition, in visio_process.ps1"
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
    code = re.sub(r"<#.*?#>|#[^\n]*", "", text, flags=re.DOTALL)
    assert ".ProcessID" not in code, "only the comments may name it, to say why not"
    assert "GetWindowThreadProcessId" in text
    assert "$App.WindowHandle32" in text
    assert "$process.ProcessName -ne 'VISIO'" in text
    assert "$leftover | Stop-Process -Force" in text
    # and by the time it started: a later process can have the ID it let go of
    assert "$Process.StartTime.ToUniversalTime().Ticks" in text
    assert "(Get-StartTicks -Process $process) -ne $Visio.StartTicks" in text
    # an unnamed Visio is taken only if it has no visible window, as a developer's has,
    # and is checked again when it comes to be killed (#464)
    assert "$_.MainWindowHandle -eq 0" in text
    assert "$Visio.Inferred -and $leftover.MainWindowHandle -ne 0" in text
    # a Visio that was running is known by its start time too
    assert "$_.Id -eq $candidate.Id -and $_.StartTicks -eq $candidate.StartTicks" in text


def test_the_helper_type_is_added_once_per_powershell_session():
    """A script run twice from one prompt dot-sources the helper twice, and a type cannot be added twice."""
    text = (TOOLS / "visio_process.ps1").read_text(encoding="utf-8")
    assert "if (-not ('VsdxKit.Window' -as [type])) {" in text


@pytest.mark.parametrize("script", (*SCRIPTS, "visio_process.ps1"))
def test_lifecycle_warnings_go_to_stderr_not_into_the_json_on_stdout(script):
    """`Write-Warning` under `powershell -Command` lands on stdout, ahead of the JSON the caller parses (#464)."""
    text = (TOOLS / script).read_text(encoding="utf-8")
    assert "Write-Warning" not in text


def test_the_diagnostic_writer_writes_to_stderr():
    text = (TOOLS / "visio_process.ps1").read_text(encoding="utf-8")
    assert "function Write-Diagnostic {" in text
    assert '[Console]::Error.WriteLine("WARNING: $Message")' in text
