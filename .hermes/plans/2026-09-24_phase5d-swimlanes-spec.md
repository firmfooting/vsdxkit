# Phase 5D: `SwimlaneDiagram` replaces `Container` (#110)

Part of the 1.0 API cutover (#108-#112). Stacked on #406 (`Connector`).
Authority: `.hermes/plans/2026-09-12_simplification-usability-refactor.md`,
"Swimlane semantics". Ground truth: `tests/fixtures/com_reference/s05_swimlanes_cfflow.vsdx`.

## Public API

`vsdxkit.swimlanes.SwimlaneDiagram` is a view bound to one CFF container shape
on one page. `vsdxkit.containers` is deleted.

- `Page.swimlanes -> SwimlaneDiagram | None`: `None` for a page with no CFF
  container; `InvalidOperationError` for a page with more than one.
- `Page.require_swimlanes() -> SwimlaneDiagram`: `NotFoundError` when absent,
  the same `InvalidOperationError` when ambiguous.
- `container -> Shape`: the CFF container shape it is bound to.
- `lanes -> tuple[Shape, ...]`: top lane first.
- `shapes_in(lane) -> tuple[Shape, ...]`: the top-level flowchart shapes whose
  centre lies in the lane's band; CFF machinery, lanes and connectors are not
  members.
- `lane_for(shape) -> Shape | None`: the lane whose band holds the shape's
  centre. `InvalidOperationError` when overlapping lanes make it ambiguous.
- `add_lane(label=None) -> Shape`: a copy of the top lane one pitch above it,
  made by `Shape.copy` (the one creation operation), with the Swimlane List and
  container grown to match. A label the lane cannot take is refused first.
- `set_lane_label(lane, label) -> None`: unchanged semantics.
- `move_to_lane(shape, lane) -> None`: the old `add_shape_to_lane`. It sets PinY
  to the lane's centre, unless the shape is already in the lane.

A lane passed to `shapes_in`, `set_lane_label` or `move_to_lane` that is not one
of `lanes` raises `InvalidOperationError`.

## One band predicate

A lane's band is half-open, `bottom <= y < top`, so a shape on the edge two lanes
share belongs to the upper lane only. Visio's own lanes meet only to within
rounding (3.6e-15 in the capture). So the lanes' edges are snapped: each edge
takes the value of the first edge already seen within 1e-9 of it. Adjoining
lanes then share one float, and the bands leave no gap and no overlap. Shifting
each edge by a tolerance instead kept the discrepancy, one tolerance lower
(Codex on #408). `shapes_in`, `lane_for` and `move_to_lane` use the same
snapped bands. The 0.x band was closed at both ends, which put a shape on the
edge in two lanes, and `lane_of` then returned whichever it found first.

## Discovery

The container and lanes are found among `page.children`, the shared top-level
walk. The container is the child named `CFF Container` or `CFF Container.<n>`,
where `<n>` is a number: `CFF Container.backup` is not a copy Visio made.
The same rule names every piece of the CFF machinery. A lane is `Swimlane` or
`Swimlane.<n>`, and a flowchart shape named `Swimlane.backup`, `SwimlaneTask`
or `Separator task` is a member of the lane it sits in, not machinery
(Codex on #408). Membership is one predicate: a top-level shape that is not
the container, the Swimlane List, the Phase List, a Separator, a lane or a
connector.

A page removed from its document has no diagram to find: `page.swimlanes` and
`require_swimlanes()` raise `InvalidOperationError` instead of reading the
stale XML. `move_to_lane` refuses a shape that is not a member candidate on
the diagram's page (another page's shape, a lane, a connector, the
container), before writing anything.

A diagram whose container has been deleted, or whose page has, refuses every
operation with `InvalidOperationError`, before anything is written. `lanes`,
which every operation reads first, checks it, and so does `container`; the
diagram's `repr` says it is detached. The 0.x finder searched every shape at any
depth for an exact name, while the container property searched the top level by
prefix; there is now one rule.

## Removed

- `Page.get_container`, `Page.add_swimlane` and `Page.add_shape_to_lane`.
- `vsdxkit.containers.Container` with `find`, `container_shape`, `swimlane_list`,
  `lane_band`, `lane_of`, `members`, `add_swimlane`, `lane_heading` and
  `add_shape_to_lane`.
- The public `get_user_row` and `set_user_row_value` (now private to
  `vsdxkit.swimlanes`).

## Tests

- Container, atomicity and label tests are migrated to the new API.
- New tests cover:
  - absence (`None` and `NotFoundError`);
  - two containers (`InvalidOperationError` from both accessors);
  - a shape on a shared edge belonging to one lane;
  - overlapping lanes making `lane_for` refuse;
  - a lane from elsewhere being refused;
  - `move_to_lane` leaving a member alone;
  - `add_lane` giving the copy its own ids.
- The removed names are gone.
