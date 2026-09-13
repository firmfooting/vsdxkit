# COM reference corpus

These files are ground truth. Real Microsoft Visio built each one through its
own COM automation, so the XML inside is what Visio writes rather than what we
think Visio writes. `manifest.json` records the connector cell formulas Visio
computed at the same moment, which is how the engine in `vsdx/connectors.py`
knows that dynamic glue means `_WALKGLUE(BegTrigger,EndTrigger,WalkPreference)`
with `GlueType=2`.

Do not edit these files by hand. If a fixture is wrong, regenerate it.

## Provenance

`tools/com_reference.ps1` wrote `manifest.json` on 2026-09-11. The recorded
`visio_version` is `16.0`, the string `Visio.Application.Version` returns; it
covers Visio 2016 through current Microsoft 365 builds and does not identify
the exact one. Nothing records the build, so regenerate rather than assume a
formula still holds on a newer Visio.

## Scenarios

`tools/com_reference.ps1` builds s01 through s06. Each starts from a blank or
templated document, does one thing through COM, saves, and records what
happened, including when the COM call failed. A failure note is ground truth
too: it is how we know which Visio APIs do not do what their names suggest.

| File | What Visio was asked to do | What came out |
|---|---|---|
| `s01_autoconnect_right.vsdx` | Two rectangles, `A.AutoConnect(B, 4)` (right) | One `Dynamic connector` master instance. Source of the `_WALKGLUE`/`_XFTRIGGER`/`GlueType=2`/`ObjType=2`/`ShapeRouteStyle=0` baseline. |
| `s02_glue_pin.vsdx` | Connector from the connector tool, `BeginX.GlueTo(A!PinX)` and `EndX.GlueTo(B!PinX)` | Succeeded. Gluing to `PinX` produces the same dynamic shape glue as AutoConnect. |
| `s03_route_variants.vsdx` | Three connectors between the same pair, `ShapeRouteStyle` set to 1, 16 and 17 (plus `ConLineRouteExt=2`) | All three took. Right-angle = 1, straight = 16, curved = 17 with `ConLineRouteExt=2` come from here. |
| `s04_point_glue.vsdx` | Glue to connection points on plain `DrawRectangle` shapes | **Failed**: `Referenced cell Sheet.1!Connections.X1 does not exist.` Rectangles from `DrawRectangle` have no `Connections` section, so there is nothing to glue to. Kept as the negative case. |
| `s05_swimlanes_cfflow.vsdx` | Open `CFF_HORIZONTAL_M.VSTX`, drop a `Process` master, add it to the lane, insert a lane | Saved with a real CFF container (`CFF Container`, `ContainerStyle=1`, `LockMembership=True`) and 21 shapes. Both membership calls failed: `ContainerProperties.AddMember` rejected a one-argument call, and that object has no `InsertRow`. That failure is why `vsdx/containers.py` treats CFF lane membership as geometric. |
| `s06_basflow_stencils.vsdx` | Open `BASFLO_M.vstx` and save it untouched | An empty page, `top shapes=0`. The bare basic-flowchart template, useful only as a package-shape reference. |
| `s07_point_glue_masters.vsdx` | **Purpose not recorded.** | Not built by `tools/com_reference.ps1` and not listed in `manifest.json`. It arrived with the connector-engine commit `1a564ee`. Its page holds two mastered shapes and a connector glued point to point, with `Connect` records naming `Connections.X1`/`Connections.X2` at `ToPart` 100 and 101, the case s04 could not produce. Use it as the point-glue reference, but nothing records which Visio build or which steps made it. |

Only `s05_swimlanes_cfflow.vsdx` is loaded by the test suite today, in
`tests/test_containers.py`, `tests/test_connector_engine.py`,
`tests/test_connector_atomicity.py` and `tests/test_sheet_reference_remap.py`.
People read the rest. Deleting one because nothing imports it throws away the
evidence behind a formula.

## `manifest.json`

One object, three keys:

```jsonc
{
  "generated": "2026-09-11T15:18:57",  // local time on the generating machine, no zone
  "visio_version": "16.0",             // Visio.Application.Version
  "scenarios": [ /* one entry per scenario, in build order */ ]
}
```

Each scenario:

```jsonc
{
  "scenario": "s01_autoconnect_right",
  "file": "s01_autoconnect_right.vsdx",  // null only in the s05 no-template branch
  "shapes": [ /* every shape on the saved page */ ],
  "notes": "free text from the generator, ';'-joined; failures recorded verbatim"
}
```

A scenario can also be missing rather than null. Only s05 writes a `null` entry
when its template will not open; s06 prints `S06: no BASFLO template found` and
writes no entry at all. Check for the key before reading `file`.

Every shape carries `name`, `id` and `one_d` (Visio's COM boolean: `-1` for a
1-D connector, `0` otherwise), plus `master`, the master's name or `null` for a
shape drawn directly.

A 1-D shape then carries a `cells` object mapping seventeen cell names to their
`FormulaU` string, or to `null` where the shape has no such cell: `BeginX`,
`BeginY`, `EndX`, `EndY`, `BegTrigger`, `EndTrigger`, `EndXTrigger`,
`GlueType`, `ObjType`, `ShapeRouteStyle`, `ConLineRouteExt`, `ConFixedCode`,
`BegPrompt`, `EndPrompt`, `DirX`, `DirY`, `Type`. Add a name to `$CellNames` in
the generator to capture more.

Anything else carries `text`, an empty `cells` object, and a `container` object
holding `style` and `lockMembership` from `ContainerProperties`, or `null` when
the shape is not a container.

## Regenerating

You need Windows and a licensed desktop Visio. Visio for the web has no COM.

1. Empty the output directory first. The script overwrites only the files it
   manages to save, so a scenario that fails this run leaves the previous run's
   `.vsdx` behind, and step 3 would copy that stale file over a fixture while
   the fresh `manifest.json` disagrees with it:

   ```powershell
   Remove-Item C:\tmp\vsdx_corpus\* -Force -ErrorAction SilentlyContinue
   ```

2. From an ordinary PowerShell prompt. WSL users can call `powershell.exe` from
   the Linux side; the script expects that:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/com_reference.ps1
   ```

   It writes to `C:\tmp\vsdx_corpus`, not into the repository, creating the
   directory if it is missing. Read the `SAVED` lines it prints; a scenario that
   could not be built says so instead.

3. Copy the results over the fixtures:

   ```powershell
   Copy-Item C:\tmp\vsdx_corpus\*.vsdx, C:\tmp\vsdx_corpus\manifest.json `
     -Destination path\to\repo\tests\fixtures\com_reference\ -Force
   ```

   Nothing regenerates `s07_point_glue_masters.vsdx`, so the copy leaves it
   alone. Keep it.

4. Run the suite, then read the diff on `manifest.json` before committing. A
   changed formula means Visio now writes something the connector engine does
   not; that needs an issue before the fixture is updated.

The script runs with `$ErrorActionPreference = 'Continue'`, so it keeps going
after a COM error and records it in the notes. Read those rather than the exit
code.

[CONTRIBUTING.md](../../../CONTRIBUTING.md) covers this script and
`tools/visio_verify.py` from the contributor's side, under "When a change needs
Visio".
