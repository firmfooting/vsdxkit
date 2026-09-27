<#
.SYNOPSIS
    Export the page Microsoft Visio draws for each file, on open and after
    named cells recalculate, as images. Decide nothing.

.DESCRIPTION
    tools/visio_shots.py's probe. It opens each requested file read-only in an
    invisible Visio and exports one page to every path listed under "open".
    It then calls Cell.Trigger() on each named cell and exports the page again
    to every path listed under "recalc". Page.Export picks the format from each
    path's extension, so a .png and a .svg of the same moment can be asked for
    together.

    Visio draws from the values a file caches as it opens; a cell's formula
    only takes over once something recalculates it. A drawing that changes
    between the two exports is one whose cached values were stale on open,
    which is what visio_shots.py looks for. It reaches no verdict here:
    visio_shots.py decides what a difference means, in Python, where it can be
    tested.

.PARAMETER Request
    A JSON file: { "dpi": 150, "files": [ { "path": "C:\...", "page": 1,
    "open": [ "C:\...\a.open.png", "C:\...\a.open.svg" ], "recalc": [ ... ],
    "triggers": [ { "page": 1, "shape": 35, "cell": "LineColor" } ] } ] }.
    "cell" is a Visio universal cell name: PinX, LineColor, Geometry1.X2, ...

.PARAMETER ProcessIdFile
    Where to write the ID of the Visio process this script starts, as soon
    as it has one. A caller that has to give up on the script kills that
    process, and no other.

.PARAMETER AllowRunningVisio
    Proceed even if Visio is already running. Off by default, for the reasons
    tools/visio_cells.ps1 gives.

.OUTPUTS
    One JSON object: { visio: { version, build }, files: [ { path, triggered }
    | { path, error } ] }, files in request order.

.EXAMPLE
    powershell.exe -NoProfile -File tools/visio_export.ps1 -Request request.json
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Request,

    [string]$ProcessIdFile,

    [switch]$AllowRunningVisio
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Refusal {
    # Not Write-Error, for the reason tools/visio_cells.ps1's Write-Refusal gives.
    param([string]$Message, [int]$Code)

    [Console]::Error.WriteLine($Message)
    exit $Code
}

function Get-VisioProcessIds {
    return @(Get-Process -Name VISIO -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
}

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
    $process = Get-Process -Id ([int]$owner) -ErrorAction SilentlyContinue
    if ($owner -eq 0 -or $null -eq $process -or $process.ProcessName -ne 'VISIO') { return $null }
    return [int]$owner
}

# CellExistsU's second argument: 0 counts a cell inherited from a master, as
# tools/visio_cells.ps1's $visExistsAnywhere does.
$visExistsAnywhere = 0

# --- pre-flight -------------------------------------------------------------

$preexisting = @(Get-VisioProcessIds)
if ($preexisting.Count -gt 0 -and -not $AllowRunningVisio) {
    Write-Refusal (
        "Visio is already running (pid $($preexisting -join ', ')). It may hold a lock on the " +
        'files under test. Close it, or pass -AllowRunningVisio if it is wanted.'
    ) 3
}

$req = Get-Content -Raw -Path $Request | ConvertFrom-Json
$files = @($req.files)
if ($files.Count -eq 0) {
    Write-Refusal 'the request names no files' 2
}

# Documents.OpenEx flags, as tools/visio_cells.ps1: read-only, macros disabled,
# no workspace.
$OpenFlags = 2 + 128 + 256

# Settings.SetRasterExportResolution: visRasterUseCustomResolution = 3,
# visRasterPixelsPerInch = 0.
$visRasterUseCustomResolution = 3
$visRasterPixelsPerInch = 0

# --- run --------------------------------------------------------------------

$app = $null
$ownProcessId = $null
$out = @()
$visio = [ordered]@{}
try {
    $app = New-Object -ComObject Visio.InvisibleApp
    # The one process this script may kill if Quit leaves it running. Not
    # "any Visio started during the run": a Visio the developer opens while
    # a long export is under way is theirs, with their unsaved work in it.
    $ownProcessId = Get-OwnProcessId -App $app
    if ($ProcessIdFile -and $null -ne $ownProcessId) {
        Set-Content -Path $ProcessIdFile -Value $ownProcessId -Encoding ascii
    }
    $app.AlertResponse = 7
    $visio.version = [string]$app.Version
    $visio.build = [string]$app.Build
    $app.Settings.SetRasterExportResolution(
        $visRasterUseCustomResolution, [double]$req.dpi, [double]$req.dpi, $visRasterPixelsPerInch)
    foreach ($f in $files) {
        # One try per file, as tools/visio_cells.ps1: a file that will not
        # open costs its own record, not the batch.
        $doc = $null
        try {
            $doc = $app.Documents.OpenEx([string]$f.path, $OpenFlags)
            $page = $doc.Pages.Item([int]$f.page)
            foreach ($target in @($f.open)) { $page.Export([string]$target) }
            $triggered = 0
            foreach ($t in @($f.triggers)) {
                # A case's `.before` file lacks any shape the case created
                # (a copy, say), and ItemFromID throws for an ID the page
                # does not have: that trigger is skipped, not the file.
                $shape = $null
                try { $shape = $doc.Pages.Item([int]$t.page).Shapes.ItemFromID([int]$t.shape) } catch { }
                if ($null -ne $shape -and $shape.CellExistsU([string]$t.cell, $visExistsAnywhere) -ne 0) {
                    $shape.CellsU([string]$t.cell).Trigger()
                    $triggered++
                }
            }
            foreach ($target in @($f.recalc)) { $page.Export([string]$target) }
            $out += [ordered]@{ path = [string]$f.path; triggered = $triggered }
        }
        catch {
            $out += [ordered]@{ path = [string]$f.path; error = $_.Exception.Message }
        }
        finally {
            if ($null -ne $doc) { try { $doc.Close() } catch { } }
        }
    }
}
finally {
    if ($null -ne $app) {
        try { $app.AlertResponse = 0 } catch { }
        try { $app.Quit() } catch { }
        try { [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) } catch { }
        $app = $null
    }
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()

    if ($null -ne $ownProcessId) {
        $deadline = (Get-Date).AddSeconds(15)
        while ((Get-Date) -lt $deadline -and $null -ne (Get-VisioProcess -ProcessId $ownProcessId)) {
            Start-Sleep -Milliseconds 250
        }
        $leftover = Get-VisioProcess -ProcessId $ownProcessId
        if ($null -ne $leftover) {
            try { $leftover | Stop-Process -Force -ErrorAction Stop } catch { }
        }
    }
}

# One object, so no array unrolling can reshape it; see tools/visio_cells.ps1.
ConvertTo-Json -InputObject ([ordered]@{ visio = $visio; files = @($out) }) -Depth 10 -Compress
exit 0
