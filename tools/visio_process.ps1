<#
.SYNOPSIS
    Which Windows process a Visio COM object runs in, and how to end it: the
    one lifecycle rule tools/visio_cells.ps1, tools/visio_observe.ps1 and
    tools/visio_export.ps1 share. Dot-sourced by each; runs nothing itself.

.DESCRIPTION
    New-Object -ComObject starts VISIO.EXE out of process, and Quit is a
    request, not a guarantee: a document Visio believes is dirty keeps the
    process alive holding the file. Each script therefore ends the Visio it
    started once Quit has had its chance, and no other. A Visio the developer
    had open, or opened while a long run was under way, is theirs, with their
    unsaved work in it (#463).
#>

# Once per PowerShell session: a type cannot be added twice, and a script
# run a second time from the same prompt dot-sources this again.
if (-not ('VsdxKit.Window' -as [type])) {
    Add-Type -Namespace VsdxKit -Name Window -MemberDefinition @'
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(System.IntPtr hWnd, out uint processId);
'@
}

function Write-Diagnostic {
    <#
      Warn on stderr, not the warning stream: under `powershell -Command`
      that lands on stdout, ahead of the JSON a caller parses there.
    #>
    param([string]$Message)

    [Console]::Error.WriteLine("WARNING: $Message")
}

function Get-StartTicks {
    <#
      When $Process started, in UTC ticks, as tools/visio_verify.py reads it;
      $null where Windows will not say, as for a process run as administrator
      when this one is not. A process whose start cannot be read is never
      taken for this script's.
    #>
    param($Process)

    try { return $Process.StartTime.ToUniversalTime().Ticks }
    catch { return $null }
}

function ConvertTo-VisioIdentity {
    <#
      What names the Visio process $Process: its ID and when it started.
      The ID alone does not. Windows reuses IDs, so once a Visio has gone its
      ID can be a later process's, another Visio's among them.
    #>
    param($Process)

    return [pscustomobject]@{ Id = $Process.Id; StartTicks = (Get-StartTicks -Process $Process) }
}

function Get-VisioIdentities {
    # Every VISIO process running now, named as ConvertTo-VisioIdentity names
    # one. @() at the call site: PowerShell unrolls an array on `return`, so an
    # empty result would otherwise arrive as $null, and $null.Count throws
    # under Set-StrictMode.
    return @(Get-Process -Name VISIO -ErrorAction SilentlyContinue | ForEach-Object { ConvertTo-VisioIdentity -Process $_ })
}

function Get-VisioProcess {
    # The Visio with ID $ProcessId, or $null: an ID a Visio has let go of can
    # be another program's by the time it is looked at.
    param([int]$ProcessId)

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $process -or $process.ProcessName -ne 'VISIO') { return $null }
    return $process
}

function Get-RunningVisio {
    # The process $Visio names while it runs, or $null: once it has gone, a
    # later Visio can have its ID, and is not it.
    param($Visio)

    if ($null -eq $Visio.StartTicks) { return $null }
    $process = Get-VisioProcess -ProcessId $Visio.Id
    if ($null -eq $process -or (Get-StartTicks -Process $process) -ne $Visio.StartTicks) { return $null }
    return $process
}

function Get-OwnVisio {
    <#
      The Visio process $App runs in, or $null where it cannot be told: the
      owner of Visio's main window, WindowHandle32, once it is seen to be a
      Visio whose start can be read.

      Not $App.ProcessID. On Visio 16 that names no process at all (199300,
      against a VISIO.EXE of 39524), so killing by it would miss this Visio
      and could kill whatever process had that ID.
    #>
    param($App)

    [uint32]$owner = 0
    [void][VsdxKit.Window]::GetWindowThreadProcessId([System.IntPtr][int64]$App.WindowHandle32, [ref]$owner)
    if ($owner -eq 0) { return $null }
    $process = Get-VisioProcess -ProcessId ([int]$owner)
    if ($null -eq $process) { return $null }
    $visio = ConvertTo-VisioIdentity -Process $process
    if ($null -eq $visio.StartTicks) { return $null }
    return $visio
}

function Write-StrandedVisio {
    <#
      Warn of each VISIO process with no visible main window that is not
      among $Preexisting, the Visio processes running when the script began,
      for a script that never got as far as naming its own. None is ended.

      New-Object can start VISIO.EXE and still fail before it returns an
      application to ask, and the Visio it started cannot then be told from
      another harness's: an InvisibleApp never shows a window, whoever
      started it. Naming them leaves the choice to whoever ran the script. A
      Visio that was running is known by its start time as well as its ID:
      it can have gone, and a new one been given its ID.
    #>
    param([object[]]$Preexisting)

    $started = @(
        Get-Process -Name VISIO -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowHandle -eq 0 } |
            ForEach-Object { ConvertTo-VisioIdentity -Process $_ } |
            Where-Object {
                $candidate = $_
                -not @($Preexisting | Where-Object {
                    $_.Id -eq $candidate.Id -and $_.StartTicks -eq $candidate.StartTicks
                }).Count
            }
    )
    if ($started.Count -eq 0) { return }
    $noun = if ($started.Count -eq 1) { 'process' } else { 'processes' }
    Write-Diagnostic ("this script could not tell which Visio it started, so none is ended; invisible Visio " +
        "$noun $(($started | ForEach-Object { $_.Id }) -join ', ') started while it ran: end the one it left, " +
        "if you can tell it from another program's")
}

function Stop-OwnVisio {
    <#
      Give $Visio, the Visio this script started and has asked to Quit, 15
      seconds to go, then kill it; $true if it had to be killed, and was. A
      kill that fails is warned of, and gives $false.
    #>
    param($Visio)

    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline -and $null -ne (Get-RunningVisio -Visio $Visio)) {
        Start-Sleep -Milliseconds 250
    }
    $leftover = Get-RunningVisio -Visio $Visio
    if ($null -eq $leftover) { return $false }
    try {
        $leftover | Stop-Process -Force -ErrorAction Stop
        return $true
    }
    catch {
        Write-Diagnostic "Visio process $($Visio.Id) outlived Quit() and could not be killed: $($_.Exception.Message)"
        return $false
    }
}

function Register-OwnVisio {
    <#
      The Visio process $App runs in, written to $ProcessIdFile as "ID ticks"
      where one is named; $null, with a warning, where it cannot be told. A
      Visio not named is never ended: the script names the new invisible
      Visio processes with Write-StrandedVisio as it ends, and a caller whose
      run times out names them too.
    #>
    param($App, [string]$ProcessIdFile)

    $visio = Get-OwnVisio -App $App
    if ($null -eq $visio) {
        Write-Diagnostic ("could not tell which process this Visio runs in; if Quit leaves it running it is " +
            "not ended, and a later run may find it still running")
        return $null
    }
    if ($ProcessIdFile) {
        Set-Content -Path $ProcessIdFile -Value "$($visio.Id) $($visio.StartTicks)" -Encoding ascii
    }
    return $visio
}
