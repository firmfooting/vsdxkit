<#
.SYNOPSIS
    Report what Microsoft Visio shows for named cells, on open and after they
    recalculate, as JSON. Decide nothing.

.DESCRIPTION
    This is the writes-land package's own probe, alongside visio_observe.ps1's
    general one. It opens each requested file read-only in an invisible Visio,
    and for every cell the caller named reports its formula, the result Visio
    shows on open, and the result Visio shows after Cell.Trigger() forces the
    cell to recalculate, plus every page's Connects (glue records). It also
    deliberately reaches no verdict: tools/writes_land_cases.py's `judge`
    decides what a difference means, in Python, where it can be tested.

    Visio shows the cell's cached `V` as soon as a document opens; a formula
    only takes over once something recalculates that cell. A write that is
    silently discarded and replaced by a stale formula (a GUARD(), a theme)
    can therefore still look right on open and only show its true value after
    a recalculation, which is why each cell is read twice here.

.PARAMETER Request
    A JSON file: { "files": [ { "path": "C:\...", "cells": [ { "page": 1,
    "shape": 35, "cell": "LineColor" } ] } ] }. "cell" is a Visio universal
    cell name: PinX, LineColor, Char.Color, Geometry1.X2, ...

.PARAMETER ProcessIdFile
    A file to write the ID of the Visio process this script starts to, as
    soon as it has one. A caller whose run times out kills that process, and
    no other: killing PowerShell leaves the out-of-process Visio running.

.PARAMETER AllowRunningVisio
    Proceed even if Visio is already running. Off by default: a pre-existing
    instance can hold a lock on the file under test and can be carrying
    settings this script did not choose.

.OUTPUTS
    A JSON array, one object per requested file, in request order:
    { path, cells: [ { page, shape, cell, exists, formula, result_iu,
    result_str, recalc_iu, recalc_str } | { ...error } ], connects: [ { page,
    from_shape, from_cell, to_shape, to_cell } ] }.

.EXAMPLE
    powershell.exe -NoProfile -File tools/visio_cells.ps1 -Request request.json
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
    <#
      Refuse to run, with an exit code the caller can act on.

      Not Write-Error: under $ErrorActionPreference = 'Stop' it terminates the
      script on the spot, so the `exit` that follows never runs and every
      refusal arrives as a generic exit 1, indistinguishable from a crash.
    #>
    param([string]$Message, [int]$Code)

    [Console]::Error.WriteLine($Message)
    exit $Code
}

function Get-VisioProcessIds {
    # @() at the call site: PowerShell unrolls an array on `return`, so an
    # empty result would otherwise arrive as $null, and $null.Count throws
    # under Set-StrictMode.
    return @(Get-Process -Name VISIO -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
}

function Test-ProcessRunning {
    param([int]$ProcessId)

    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

# CellExistsU's second argument: 0 asks "does this shape have this cell at all",
# counting one inherited from a master. 1 would ask only about cells stated
# locally, and a stencil instance states almost none of them. Kept in step
# with tools/visio_observe.ps1's own $visExistsAnywhere.
$visExistsAnywhere = 0

function Get-CellRecord {
    param($Shape, $Page, [string]$Name)

    $record = [ordered]@{ page = [int]$Page; shape = [int]$Shape.ID; cell = $Name }
    try {
        if ($Shape.CellExistsU($Name, $visExistsAnywhere) -eq 0) {
            $record.exists = $false
            return $record
        }
        $cell = $Shape.CellsU($Name)
        $record.exists = $true
        $record.formula = [string]$cell.FormulaU
        $record.result_iu = [double]$cell.ResultIU
        $record.result_str = [string]$cell.ResultStrU('')
        # The cached value above is what Visio shows on open; Trigger() forces
        # the cell to recalculate, which is the only way a stale formula shows
        # its true colours (see the DESCRIPTION).
        try {
            $cell.Trigger()
            $record.recalc_iu = [double]$cell.ResultIU
            $record.recalc_str = [string]$cell.ResultStrU('')
        }
        catch {
            $record.recalc_error = $_.Exception.Message
        }
    }
    catch {
        $record.error = $_.Exception.Message
    }
    return $record
}

function Get-ConnectRecords {
    param($Document)

    $records = @()
    for ($p = 1; $p -le $Document.Pages.Count; $p++) {
        foreach ($connect in $Document.Pages.Item($p).Connects) {
            $records += [ordered]@{
                page       = $p
                from_shape = [int]$connect.FromSheet.ID
                from_cell  = [string]$connect.FromCell.Name
                to_shape   = [int]$connect.ToSheet.ID
                to_cell    = [string]$connect.ToCell.Name
            }
        }
    }
    return $records
}

# --- pre-flight -------------------------------------------------------------

$preexisting = @(Get-VisioProcessIds)
if ($preexisting.Count -gt 0 -and -not $AllowRunningVisio) {
    Write-Refusal (
        "Visio is already running (pid $($preexisting -join ', ')). It may hold a lock on the " +
        'files under test, and an orphan from an earlier crashed run reports as a corrupt file ' +
        'rather than as a busy one. Close it, or pass -AllowRunningVisio if it is wanted.'
    ) 3
}

$req = Get-Content -Raw -Path $Request | ConvertFrom-Json
$files = @($req.files)
if ($files.Count -eq 0) {
    Write-Refusal 'the request names no files' 2
}

# Documents.OpenEx flags, matching tools/visio_observe.ps1: read-only because a
# write lock is what strands a file when this crashes; macros disabled because
# opening a document must never run code the document chose; no workspace so a
# saved window layout cannot change what gets reported.
$visOpenRO = 2
$visOpenMacrosDisabled = 128
$visOpenNoWorkspace = 256
$OpenFlags = $visOpenRO + $visOpenMacrosDisabled + $visOpenNoWorkspace

# --- run --------------------------------------------------------------------

$app = $null
$ownProcessId = $null
$out = @()
try {
    $app = New-Object -ComObject Visio.InvisibleApp
    # The one process this script may kill if Quit leaves it running. Not
    # "any Visio started during the run": a Visio the developer opens while
    # a long run is under way is theirs, with their unsaved work in it (#463).
    $ownProcessId = [int]$app.ProcessID
    if ($ProcessIdFile) { Set-Content -Path $ProcessIdFile -Value $ownProcessId -Encoding ascii }
    # Answer every modal dialog with "no" instead of waiting for a click: an
    # unattended run that puts up a dialog does not fail, it hangs.
    $app.AlertResponse = 7
    foreach ($f in $files) {
        # The open and the whole per-file walk share one try/catch, as
        # visio_observe.ps1's Get-DocumentRecord does: a locked or corrupt
        # file must cost this file's record, not the batch - without this,
        # an OpenEx that throws unwinds straight out of the foreach and no
        # file after it, however clean, is ever reported.
        $doc = $null
        try {
            $doc = $app.Documents.OpenEx([string]$f.path, $OpenFlags)
            $cells = @()
            foreach ($c in $f.cells) {
                $record = $null
                try {
                    $shape = $doc.Pages.Item([int]$c.page).Shapes.ItemFromID([int]$c.shape)
                    $record = Get-CellRecord -Shape $shape -Page $c.page -Name $c.cell
                }
                catch {
                    $record = [ordered]@{ page = [int]$c.page; shape = [int]$c.shape; cell = [string]$c.cell; error = $_.Exception.Message }
                }
                $cells += $record
            }
            $out += [ordered]@{ path = [string]$f.path; cells = @($cells); connects = @(Get-ConnectRecords -Document $doc) }
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

    # Quit is a request, not a guarantee: a document Visio believes is dirty
    # keeps the process alive holding the file. Only the Visio this script
    # started is killed, so one the developer had open, or opened while this
    # ran, is never taken from them.
    if ($null -ne $ownProcessId) {
        $deadline = (Get-Date).AddSeconds(15)
        while ((Get-Date) -lt $deadline -and (Test-ProcessRunning -ProcessId $ownProcessId)) {
            Start-Sleep -Milliseconds 250
        }
        if (Test-ProcessRunning -ProcessId $ownProcessId) {
            try { Stop-Process -Id $ownProcessId -Force -ErrorAction Stop } catch { }
        }
    }
}

# -InputObject @($out), not `$out | ConvertTo-Json`: piping unrolls the
# array element by element, so a batch of exactly one file loses its
# arrayness and ConvertTo-Json emits a bare object instead of a one-element
# array - `-AsArray` would fix that but needs PowerShell 7, and this has to
# run under Windows PowerShell 5.1 too. Passed as -InputObject, the whole
# array binds as one argument and is never unrolled.
ConvertTo-Json -InputObject @($out) -Depth 10 -Compress

# Explicit, so that $LASTEXITCODE is always set for the caller to read: a
# script that falls off its end otherwise leaves whatever code ran last
# standing.
exit 0
