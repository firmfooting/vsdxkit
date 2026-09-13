<#
.SYNOPSIS
    Report what Microsoft Visio sees in a .vsdx, as JSON. Decide nothing.

.DESCRIPTION
    This is one half of a differential oracle. It opens each document in an
    invisible Visio instance, enumerates every page, every shape (descending
    into groups) and every glue record, and writes the result to stdout as JSON.
    tests/helpers/visio_observation.py reads that JSON, derives the same account
    from the package's own XML, and compares the two.

    It deliberately does not report PASS or FAIL. The checker this replaces did,
    and so it reported PASS on a package whose fourth shape Visio had silently
    discarded: it counted what Visio showed it and never asked what the file had
    promised. A verdict reached inside a Windows-only COM loop is a verdict that
    cannot be tested. Everything here is extraction; all judgment is in Python,
    under test, on any platform.

    Process lifecycle is the other half of its job. A crashed run leaves a Visio
    process holding the file, and the next open fails with "open for
    modifications in another instance" - which reads exactly like a corrupt
    file. That misdiagnosis is easy to make and expensive to chase, so this
    script refuses to start when an orphan is already running, and guarantees
    that every instance it starts is gone before it exits.

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

$SchemaVersion = 1

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
            sha256 = (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        status = 'opened'
        error  = $null
        pages  = @()
    }

    $doc = $null
    try {
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
        # Told apart here because they look identical from the outside and lead
        # to opposite conclusions: one means the file is bad, the other means the
        # machine is dirty and the file was never read at all.
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

$app = $null
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
        $leaked = @(Get-VisioProcessIds | Where-Object { $preexisting -notcontains $_ })
        if ($leaked.Count -eq 0) { break }
        Start-Sleep -Milliseconds 250
    }
    $leaked = @(Get-VisioProcessIds | Where-Object { $preexisting -notcontains $_ })
    foreach ($processId in $leaked) {
        Write-Warning "Visio process $processId outlived Quit(); killing it so the next run can open these files"
        try { Stop-Process -Id $processId -Force -ErrorAction Stop } catch { }
    }
}

@{
    schema    = $SchemaVersion
    viewer    = $viewer
    documents = @($documents)
} | ConvertTo-Json -Depth 8 -Compress

# Explicit, so that $LASTEXITCODE is always set for the caller to read: pwsh -Command
# reports only whether the pipeline succeeded, and a script that falls off its end
# leaves whatever code ran last standing.
exit 0
