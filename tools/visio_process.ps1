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

Add-Type -Namespace VsdxKit -Name Window -MemberDefinition @'
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(System.IntPtr hWnd, out uint processId);
'@

function Get-VisioProcess {
    # The Visio with ID $ProcessId, or $null: an ID a Visio has let go of can
    # be another program's by the time it is looked at.
    param([int]$ProcessId)

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $process -or $process.ProcessName -ne 'VISIO') { return $null }
    return $process
}

function Get-OwnProcessId {
    <#
      The ID of the Windows process $App runs in, or $null where it cannot be
      told: the owner of Visio's main window, WindowHandle32, once it is seen
      to be a Visio.

      Not $App.ProcessID. On Visio 16 that names no process at all (199300,
      against a VISIO.EXE of 39524), so killing by it would miss this Visio
      and could kill whatever process had that ID.
    #>
    param($App)

    [uint32]$owner = 0
    [void][VsdxKit.Window]::GetWindowThreadProcessId([System.IntPtr][int64]$App.WindowHandle32, [ref]$owner)
    if ($owner -eq 0 -or $null -eq (Get-VisioProcess -ProcessId ([int]$owner))) { return $null }
    return [int]$owner
}

function Stop-OwnVisio {
    <#
      Give the Visio with ID $ProcessId, one this script started and has
      asked to Quit, 15 seconds to go, then kill it; $true if it had to be
      killed.
    #>
    param([int]$ProcessId)

    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline -and $null -ne (Get-VisioProcess -ProcessId $ProcessId)) {
        Start-Sleep -Milliseconds 250
    }
    $leftover = Get-VisioProcess -ProcessId $ProcessId
    if ($null -eq $leftover) { return $false }
    try { $leftover | Stop-Process -Force -ErrorAction Stop } catch { }
    return $true
}
