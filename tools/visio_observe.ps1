<#
.SYNOPSIS
    Report what Microsoft Visio sees in a .vsdx, as JSON. Decide nothing.

.DESCRIPTION
    This is one half of a differential oracle. It opens each document in an
    invisible Visio instance, enumerates every page, every shape (descending
    into groups) with the cells that place it, and every glue record, and writes
    the result to stdout as JSON.
    tests/helpers/visio_observation.py reads that JSON, derives the same account
    from the package's own XML, and compares the two.

    It deliberately reaches no verdict. A verdict reached inside a Windows-only
    COM loop cannot be exercised by a test, so everything here is extraction and
    all judgment is in Python.

    Process lifecycle is the other half of its job: it refuses to start when an
    orphan Visio is already running, and guarantees that every instance it
    starts is gone before it exits. See Write-Refusal and the cleanup block.

.PARAMETER Path
    One or more .vsdx files, or directories to scan for them.

.PARAMETER AllowRunningVisio
    Proceed even if Visio is already running. Off by default: a pre-existing
    instance can hold a lock on the file under test and can be carrying settings
    this script did not choose.

.OUTPUTS
    A JSON object: { schema, viewer, documents: [ ... ] }. Each document record
    carries its own schema stamp so that it stays valid once split out and
    recorded on its own.

.EXAMPLE
    powershell.exe -NoProfile -File tools/visio_observe.ps1 -Path out\probe.vsdx
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string[]]$Path,

    [switch]$AllowRunningVisio
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$SchemaVersion = 2

# The cells that decide where a shape is, how big it is and which way round it
# faces. Kept in step with PLACEMENT_CELLS in tests/helpers/visio_observation.py
# by test_the_two_sides_ask_for_the_same_placement_cells - a name added on one
# side and not the other is a cell nobody compares.
#
# The last four exist only on a 1-D shape, so every name is asked for with
# CellExistsU and a shape reports the ones it has. That keeps the record
# symmetric with the package side, which can only speak where its XML does.
$PlacementCells = @(
    'PinX', 'PinY', 'Width', 'Height', 'Angle', 'LocPinX', 'LocPinY', 'FlipX', 'FlipY',
    'BeginX', 'BeginY', 'EndX', 'EndY'
)

# CellExistsU's second argument: 0 asks "does this shape have this cell at all",
# counting one inherited from a master. 1 would ask only about cells stated
# locally, and a stencil instance states almost none of them.
$visExistsAnywhere = 0

# Documents.OpenEx flags. Read-only because a write lock is what strands a file
# when this crashes; macros disabled because opening a document must never run
# code the document chose; no workspace so a saved window layout cannot change
# what gets reported.
$visOpenRO = 2
$visOpenMacrosDisabled = 128
$visOpenNoWorkspace = 256
$OpenFlags = $visOpenRO + $visOpenMacrosDisabled + $visOpenNoWorkspace

function Write-Refusal {
    <#
      Refuse to run, with an exit code the caller can act on.

      Not Write-Error: under $ErrorActionPreference = 'Stop' it terminates the
      script on the spot, so the `exit` that follows never runs and every
      refusal arrives as a generic exit 1. The caller then cannot tell "Visio is
      already running" from "the script crashed", which is the distinction these
      codes exist to make.
    #>
    param([string]$Message, [int]$Code)

    [Console]::Error.WriteLine($Message)
    exit $Code
}

function Get-TargetFiles {
    param([string[]]$Candidates)
    $files = @()
    foreach ($candidate in $Candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Container) {
            $files += Get-ChildItem -LiteralPath $candidate -Include *.vsdx, *.vsdm -Recurse -File |
                ForEach-Object { $_.FullName }
        }
        elseif (Test-Path -LiteralPath $candidate) {
            $files += (Resolve-Path -LiteralPath $candidate).Path
        }
        else {
            throw "no such file or directory: $candidate"
        }
    }
    return $files
}

function Get-VisioProcessIds {
    return @(Get-Process -Name VISIO -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
}

function Get-LeakedProcessIds {
    <#
      Visio processes this run is responsible for killing.

      Not simply "any pid that was not in the snapshot": the developer may open
      Visio while a run is in progress, and killing it would take their work
      away in the middle of it - the opposite of what the cleanup promises. A
      process that started before this script did is theirs whether or not it
      was in the snapshot, so the start time is the deciding fact.
    #>
    param([int[]]$Preexisting, [datetime]$StartedAfter)

    return @(
        Get-Process -Name VISIO -ErrorAction SilentlyContinue |
            Where-Object { $Preexisting -notcontains $_.Id -and $_.StartTime -ge $StartedAfter } |
            ForEach-Object { $_.Id }
    )
}

function Get-CellRecords {
    <#
      Both halves of every placement cell: the formula and the evaluated result.
      They are different facts, both are recorded, and Python decides what to do
      with them.

      FormulaU and CellsU rather than Formula and Cells: the universal forms do
      not change with the machine's language, and a recording made on a German
      Windows has to replay on an English one.

      ResultIU is in internal units - inches, and radians for angles - which is
      the unit the package's own `V` attribute uses. FormulaU is rendered in the
      document's units instead, so the same cell reads `33.849999572584 mm`
      there and `1.33267714852694` here. Reporting both is what lets the Python
      side compare a constant without parsing units.
    #>
    param($Shape)

    $records = @()
    foreach ($name in $PlacementCells) {
        # A cell Visio has but will not read out is a finding, and it has to
        # arrive as a record rather than as a gap. A gap reads as "this shape
        # does not have this cell", which is a different fact, and one the
        # package side says too - legitimately, for the four endpoint cells on
        # every 2-D shape. Both sides would then be silent and nothing would
        # fire. That is why a failure to ask is reported the same way as a
        # failure to read: CellExistsU answers false for a cell the shape has
        # not got, so it throwing means something else went wrong.
        $unreadable = $null
        $exists = $false
        try { $exists = [bool]$Shape.CellExistsU($name, $visExistsAnywhere) }
        catch { $unreadable = "CellExistsU: $($_.Exception.Message)" }
        if ($null -eq $unreadable) {
            if (-not $exists) { continue }
            try {
                $cell = $Shape.CellsU($name)
                $records += @{
                    name    = $name
                    formula = [string]$cell.FormulaU
                    result  = [double]$cell.ResultIU
                }
                continue
            }
            catch { $unreadable = $_.Exception.Message }
        }
        $records += @{
            name    = $name
            formula = "<unreadable: $unreadable>"
            result  = $null
        }
    }
    return $records
}

function Get-ShapeRecords {
    <#
      Walk a Shapes collection, descending into groups.

      Visio's Shape.ID is page-scoped, the same number the package writes as
      <Shape ID='...'>, which is what lets the two sides be joined at all. The
      enclosing group's id travels with each record because a shape that has
      escaped its group is a different failure from a shape that has vanished,
      and a flat set of ids reports them identically.
    #>
    param($Shapes, $ParentId)

    $records = @()
    foreach ($shape in $Shapes) {
        $record = @{
            id        = [int]$shape.ID
            parent_id = $ParentId
            name      = [string]$shape.NameID
            # @() because PowerShell unrolls an array on `return`: a shape with
            # one readable cell would otherwise arrive as a bare hashtable and be
            # serialised as a JSON object where every other shape has a list.
            cells     = @(Get-CellRecords -Shape $shape)
        }
        $records += $record
        $childCount = 0
        try { $childCount = $shape.Shapes.Count } catch { $childCount = 0 }
        if ($childCount -gt 0) {
            $records += Get-ShapeRecords -Shapes $shape.Shapes -ParentId ([int]$shape.ID)
        }
    }
    return $records
}

function Get-ConnectRecords {
    param($Page)

    $records = @()
    foreach ($connect in $Page.Connects) {
        try {
            $records += @{
                from_shape = [int]$connect.FromSheet.ID
                from_cell  = [string]$connect.FromCell.Name
                to_shape   = [int]$connect.ToSheet.ID
                to_cell    = [string]$connect.ToCell.Name
            }
        }
        catch {
            # An endpoint Visio cannot resolve is a finding in its own right, but
            # it is not a difference between two views, so it is reported as a
            # record the comparison can see rather than dropped on the floor.
            $records += @{
                from_shape = -1
                from_cell  = "<unreadable: $($_.Exception.Message)>"
                to_shape   = -1
                to_cell    = ''
            }
        }
    }
    return $records
}

function Get-DocumentRecord {
    param($App, [string]$File)

    $record = @{
        schema = $SchemaVersion
        source = @{
            name   = (Split-Path -Path $File -Leaf)
            path   = $File
            sha256 = ''
        }
        status = 'opened'
        error  = $null
        pages  = @()
    }

    $doc = $null
    try {
        # Inside the try: a file that has gone away or been locked between
        # staging and hashing should cost one document record, not the whole
        # run and every document already collected with it.
        $record.source.sha256 = (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant()
        $doc = $App.Documents.OpenEx($File, $OpenFlags)
        $pages = @()
        foreach ($page in $doc.Pages) {
            $pages += @{
                index      = [int]$page.Index
                name       = [string]$page.Name
                background = [bool]$page.Background
                shapes     = @(Get-ShapeRecords -Shapes $page.Shapes -ParentId $null)
                connects   = @(Get-ConnectRecords -Page $page)
            }
        }
        $record.pages = $pages
    }
    catch {
        $message = $_.Exception.Message
        $record.status = 'error'
        $record.error = $message
        # "Visio cannot open this file because something holds it" and "this
        # file is broken" are the same error from the outside and lead to
        # opposite conclusions, so they are told apart here.
        if ($message -match 'another instance|in use|being edited|modifications') {
            $record.status = 'locked'
        }
    }
    finally {
        if ($null -ne $doc) {
            try { $doc.Close() } catch { }
        }
    }
    return $record
}

# --- pre-flight -------------------------------------------------------------

$files = @(Get-TargetFiles -Candidates $Path)
if ($files.Count -eq 0) {
    Write-Refusal 'no .vsdx or .vsdm files found in the given paths' 2
}

# @() at the call site because PowerShell unrolls an array on `return`: an empty
# result arrives as $null, and $null.Count throws under Set-StrictMode.
$preexisting = @(Get-VisioProcessIds)
if ($preexisting.Count -gt 0 -and -not $AllowRunningVisio) {
    Write-Refusal (
        "Visio is already running (pid $($preexisting -join ', ')). It may hold a lock on the " +
        'files under test, and an orphan from an earlier crashed run reports as a corrupt file ' +
        'rather than as a busy one. Close it, or pass -AllowRunningVisio if it is wanted.'
    ) 3
}

# --- run --------------------------------------------------------------------

$startedAt = Get-Date
$app = $null
$viewer = @{ product = ''; version = '' }
$documents = @()
try {
    $app = New-Object -ComObject Visio.InvisibleApp
    # Answer every modal dialog with "no" instead of waiting for a click: an
    # unattended run that puts up a dialog does not fail, it hangs.
    $app.AlertResponse = 7
    $app.EventsEnabled = 0
    $viewer = @{
        product = [string]$app.ProductName
        version = [string]$app.Version
    }
    foreach ($file in $files) {
        $documents += Get-DocumentRecord -App $app -File $file
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

    # Quit is a request, not a guarantee: a document Visio believes is dirty, or
    # a hung add-on, keeps the process alive holding the file. Only processes
    # that were not running when this started are killed, so a Visio the user
    # had open is never taken away from them.
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline) {
        if (@(Get-LeakedProcessIds -Preexisting $preexisting -StartedAfter $startedAt).Count -eq 0) { break }
        Start-Sleep -Milliseconds 250
    }
    $leaked = @(Get-LeakedProcessIds -Preexisting $preexisting -StartedAfter $startedAt)
    foreach ($processId in $leaked) {
        Write-Warning "Visio process $processId outlived Quit(); killing it so the next run can open these files"
        try { Stop-Process -Id $processId -Force -ErrorAction Stop } catch { }
    }
}

@{
    schema    = $SchemaVersion
    viewer    = $viewer
    documents = @($documents)
} | ConvertTo-Json -Depth 10 -Compress

# Explicit, so that $LASTEXITCODE is always set for the caller to read: pwsh -Command
# reports only whether the pipeline succeeded, and a script that falls off its end
# leaves whatever code ran last standing.
exit 0
