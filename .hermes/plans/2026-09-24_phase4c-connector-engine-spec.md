# Phase 4C: one connector engine (#106)

Stacked on #399 (Phase 4B, one deletion). Roadmap key 10B-B3.

## Problem

`connectors.py` holds glue in three places, and they disagree.

- **Route parsing runs three times per call:** in `create`, in `_validate_point_glue`, and again in `_apply_glue`. Nothing carries the parsed result.
- **`_apply_glue` has two branches** that build the same things (per-end trigger and coordinate formulas, two `<Connect>` records) by string formatting. They drift apart:
  - The point branch writes its begin trigger to a cell named `BeginTrigger`. Visio has no such cell; its begin trigger is `BegTrigger` (`s07_point_glue_masters.vsdx`, `s01`/`s02` in the COM manifest). The real `BegTrigger` is left as the donor connector had it, `_XFTRIGGER(Sheet.1!EventXFMod)`. That names whatever shape happens to be 1 in the target document.
- **Retarget always re-glues from the `route` argument, default `"dynamic"`.** So a point-glued connector whose one end is moved silently becomes dynamic at both ends, and its routing resets.
- **Retarget refuses a connector with a floating end**: "no resolvable endpoints to keep".
- **Validation covers only point indexes.** An endpoint on another page, a detached endpoint, or the connector itself as an endpoint is written without complaint.

## Design

### `vsdxkit.glue`: glue as data, no package access

A new module of pure values and functions. It imports nothing from vsdxkit except `errors`.

```python
class Glue(Enum):          # how an end attaches
    DYNAMIC = "dynamic"    # shape glue: _WALKGLUE, record to PinX
    POINT = "point"        # a connection-point row: PAR(PNT(...)), record to Connections.Xk

class Routing(Enum):       # ShapeRouteStyle (+ ConLineRouteExt)
    STRAIGHT = "straight"      # 16
    RIGHT_ANGLE = "rightangle" # 1
    CURVED = "curved"          # 17, ConLineRouteExt=2

@dataclass(frozen=True)
class ConnectorOptions:
    glue: Glue = Glue.DYNAMIC
    routing: Routing | None = None
    from_point: int = 0     # 0-based connection-point row, used when glue is POINT
    to_point: int = 0

    @classmethod
    def from_route(cls, route: str, from_point: int = 0, to_point: int = 0) -> ConnectorOptions: ...
```

- **`ConnectorOptions` is the one parser's output.** `from_route` accepts exactly the legacy tokens (`dynamic`, `point`, `straight`, `rightangle`, `curved`, `|`-joined, at most one routing) and raises `ValueError` as today.
- **`__post_init__`** refuses:
  - a point index that is not a non-negative `int` (`bool` excluded), raising `InvalidOperationError`, whose message keeps the words "connection point";
  - a non-`Glue` glue or a non-`Routing` routing, raising `TypeError`.

The builder's input is per end, because a retained end and a replaced end can glue differently:

```python
@dataclass(frozen=True)
class EndGlue:
    shape_id: str
    point: int | None      # None: dynamic glue

@dataclass(frozen=True)
class ConnectionRecord:   # data only
    from_sheet: str; from_cell: str; from_part: str
    to_sheet: str; to_cell: str; to_part: str

def glue_cells(begin: EndGlue | None, end: EndGlue | None) -> tuple[CellWrite, ...]
def routing_cells(routing: Routing | None, *, dynamic: bool) -> tuple[CellWrite, ...]
def connection_records(connector_id: str, begin: EndGlue | None, end: EndGlue | None) -> tuple[ConnectionRecord, ...]
def record_element(record: ConnectionRecord) -> Element
```

`CellWrite` is `(name, formula | None, value | None)`, a frozen dataclass.

- **The cells are the whole glue state, not a delta** (Codex on #401). `glue_cells` returns `CellWrite`, `CellFreeze` (drop the formula, keep the value) and `CellInherit` (remove the connector's own cell):
  - **an end that is `None` is floating:** it gets no record, its trigger is inherited, and its coordinates are frozen, so no stale formula glues it back to a shape;
  - **when no end is dynamic,** `GlueType` and `ObjType` are inherited.
- **Per glued end, in the order Visio writes them:**
  - the trigger is `BegTrigger`/`EndTrigger`, `_XFTRIGGER(SheetN!EventXFMod)`;
  - the coordinates are `BeginX/Y`/`EndX/Y`: `_WALKGLUE(BegTrigger,EndTrigger,WalkPreference)` (or the End form) for dynamic, and `PAR(PNT(SheetN!Connections.Xk,SheetN!Connections.Yk))` for a point.
- **When any end is dynamic,** the connector-level `GlueType=2`, `ObjType=2`, `ConFixedCode=6` follow.
- **Routing:**
  - dynamic glue starts from `ShapeRouteStyle=0`, `ConLineRouteExt=0`;
  - point glue starts from the straight donor's own `ShapeRouteStyle=16`, `ConLineRouteExt=1`, `ConFixedCode=6`, written out so that options replace a retargeted connector's routing rather than adding to it (Codex on #401);
  - `STRAIGHT`, `RIGHT_ANGLE` and `CURVED` then override. `CURVED` also sets `ConFixedCode=0`: s03's generator set only `ShapeRouteStyle` and `ConLineRouteExt`, and Visio changed `ConFixedCode` from 6 to 0 itself. The engine writes 6 today, so the COM oracle fails on `curved`.
- **Record order is the End record, then the Begin record, as today.** `FromPart` is 9 or 12; `ToPart` is 3 for `PinX`, or `99 + k` for `Connections.Xk`.
- **The sheet reference keeps its current undotted form.** Visio writes `Sheet.N!`, but changing that touches the remap, the validator and a dozen assertions, so it is #400.

### `connectors.py`: validate, then write once

```python
Connect.create(page, from_shape, to_shape, route="dynamic", from_cp=0, to_cp=0, *, options=None) -> Shape
Connect.retarget(page, connector_shape, from_shape=None, to_shape=None, route=None, from_cp=0, to_cp=0, *, options=None) -> Shape
```

- **Options come from exactly one place:** `options` if given, otherwise `ConnectorOptions.from_route(route, from_cp, to_cp)`. Passing both `options` and a `route` raises `ValueError`.
- **One private `_plan(...)`** resolves the two `EndGlue | None` values and runs every check before the first write:
  - the document is open;
  - each endpoint is attached and on `page`;
  - an endpoint is not the connector itself;
  - each point index is within its shape's `Connection` rows.
- **One private `_write(connector, begin, end, routing_cells)`** writes the cells, removes the connector's own records, and appends the new ones.
- **create:** both endpoints are required. It plans, copies the donor connector, writes, and sets start and finish.
- **retarget:**
  - At least one endpoint is required. Omitting both raises `InvalidOperationError`.
  - **Current ends are read from the connector's records.** A `BeginX`/`EndX` record naming a resolvable shape gives that end its shape, and its point comes from `Connections.Xk` (`None` for `PinX`). No record, or one naming a missing shape, means the end is floating.
  - **No options (no `route`, no `options`):**
    - A replaced end keeps the point index it had, validated against the new shape. An invalid retained point raises `InvalidOperationError`; it never falls back to dynamic glue.
    - A replaced end that was floating, or glued dynamically, uses dynamic glue.
    - A kept end keeps its glue.
    - Routing cells are not written.
  - **With options:** the options replace the glue and routing of both ends. A kept floating end stays floating.
  - **Start and finish:** a glued end moves to its shape's centre; a floating end keeps its coordinates.
- **`Page.connect_shapes` and `Page.reanchor_connector`** gain `options` as a keyword. `reanchor_connector`'s `route` default becomes `None`, meaning keep.
- **`_parse_route`, `_validate_point_glue` and `_apply_glue` are deleted.**

### Breaking

- `reanchor_connector`/`Connect.retarget` without `route` keeps the connector's glue and routing, instead of resetting it to dynamic.
- Retargeting a connector with a floating end moves the named end and leaves the floating one; it used to raise `InvalidOperationError`.
- Endpoints on another page, detached endpoints, and the connector itself are refused with `InvalidOperationError` before any write.
- Point glue writes its begin trigger to `BegTrigger`, not `BeginTrigger`.
- A curved connector gets `ConFixedCode=0`, as Visio sets it, instead of 6.
- Point glue accepts the connection points a shape inherits from its master. It used to count only the shape's own `Connection` rows, so it refused every point on a mastered flowchart shape.

## Tests

`tests/test_glue.py`, pure, with no document:

- `from_route` for every legal token combination, and its refusals;
- `ConnectorOptions` validation;
- `glue_cells` for both ends dynamic, both point, mixed, and one end floating;
- `routing_cells`;
- `connection_records` and `record_element` attribute values.

`tests/test_connector_engine.py`, additions:

- **COM oracle, each route option:** for `dynamic`, `straight`, `rightangle` and `curved`, the non-trigger glue cells and routing cells equal the `s03`/`s01` manifest values. For point glue, the cell names and formulas equal `s07` modulo the sheet-reference dot. The `BegTrigger` assertion fails on #399.
- Point glue leaves no `BeginTrigger` and no reference to a shape the connector is not glued to (fails on #399).

`tests/test_reanchor.py`, additions:

- retargeting one end of a point-glued connector keeps point glue at both ends and the moved end's index (fails on #399);
- a retained point index the new shape does not have raises, and changes nothing (fails on #399);
- a connector with a floating begin: retargeting its end glues the end and leaves the begin floating (fails on #399). `test_retarget_unconnected_connector_raises` is rewritten to this.
- a floating end being replaced gets dynamic glue;
- retarget without options keeps a curved routing (fails on #399);
- no endpoint raises; the connector itself as an endpoint raises; an endpoint on another page raises; a detached endpoint raises. Each case changes nothing.
- `options` and `route` together raise `ValueError`, as do `from_cp`/`to_cp` without a route.
- a connector Visio glued between two inherited points (s05's 59) keeps point glue when one end moves. On #399 the record parse (`int("X3")`) raised.
- a connector on another page raises, and changes nothing.
- create: an endpoint on another page raises before the connector is copied; point glue reaches a mastered shape's inherited points (fails on #399).

## Verification

- The gates script.
- The canonical sweep against #399 is byte-identical. The sweep opens and saves fixtures, and no fixture's save runs point glue.
- The wheel smoke test.
