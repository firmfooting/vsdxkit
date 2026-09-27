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

function Get-VisioProcessIds {
    # @() at the call site: PowerShell unrolls an array on `return`, so an
    # empty result would otherwise arrive as $null, and $null.Count throws
    # under Set-StrictMode.
    return @(Get-Process -Name VISIO -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
}

function Get-StartTicks {
    # When $Process started, in UTC ticks; tools/visio_verify.py reads the same.
    param($Process)

    return $Process.StartTime.ToUniversalTime().Ticks
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

    $process = Get-VisioProcess -ProcessId $Visio.Id
    if ($null -eq $process -or (Get-StartTicks -Process $process) -ne $Visio.StartTicks) { return $null }
    return $process
}

function Get-OwnVisio {
    <#
      The Visio process $App runs in, or $null where it cannot be told: the
      owner of Visio's main window, WindowHandle32, once it is seen to be a
      Visio.

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
    return ConvertTo-VisioIdentity -Process $process
}

function Find-StrandedVisio {
    <#
      The Visio this script's COM activation started, when it never got as
      far as naming it: the one VISIO process with no visible main window
      that is not among $Preexisting. $null where there is none, or more
      than one, which are then warned of and left alone.

      New-Object can start VISIO.EXE and still fail before it returns an
      application to ask. A script's Visio is an InvisibleApp, with no visible
      window; a Visio the developer opens has one, so it is never taken.
    #>
    param([int[]]$Preexisting)

    $stranded = @(
        Get-Process -Name VISIO -ErrorAction SilentlyContinue |
            Where-Object { $Preexisting -notcontains $_.Id -and $_.MainWindowHandle -eq 0 }
    )
    if ($stranded.Count -gt 1) {
        Write-Diagnostic ("invisible Visio processes $(($stranded | ForEach-Object { $_.Id }) -join ', ') started " +
            "while this ran and none is known to be this script's, so none is ended; end the ones that are not yours")
    }
    if ($stranded.Count -ne 1) { return $null }
    return ConvertTo-VisioIdentity -Process $stranded[0]
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
      where one is named; $null, with a warning, where it cannot be told. The
      script then looks for it with Find-StrandedVisio as it ends, and a
      caller whose run times out looks for it among the new invisible Visio
      processes.
    #>
    param($App, [string]$ProcessIdFile)

    $visio = Get-OwnVisio -App $App
    if ($null -eq $visio) {
        Write-Diagnostic ("could not tell which process this Visio runs in; if Quit leaves it running it is " +
            "ended only if it is the one new Visio with no window, and a later run may find it still running")
        return $null
    }
    if ($ProcessIdFile) {
        Set-Content -Path $ProcessIdFile -Value "$($visio.Id) $($visio.StartTicks)" -Encoding ascii
    }
    return $visio
}
