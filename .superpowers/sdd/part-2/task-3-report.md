# Task 3 report: layered layout primitives (#53)

Branch: feat/layout-primitives. Base for review: 60fe99a. Commit: 4d7d12b `feat: add layered layout primitives`. Not pushed, no PR opened, not merged.

## TDD evidence

Red (after Step 1, tests and the errors-test patch in place, layout and GraphError absent):

```
ERROR collecting tests/test_layout.py
E   ImportError: cannot import name 'GraphError' from 'vsdxkit.errors' (.../src/vsdxkit/errors.py)
1 error in 0.03s
```

Green (after Step 3, errors.py and layout.py added):

```
147 passed in 1.55s
```

## Gates

- `uv run --no-sync python -m pytest tests -q`: 2450 passed, 47 skipped (84.49s).
- `uv run --no-sync ruff check src tests tools`: All checks passed!
- `uv run --no-sync ruff format --check src tests tools`: 154 files already formatted.
- `uv run --no-sync pyrefly check src/vsdxkit --min-severity warn --output-format min-text`: INFO 0 diagnostics.
- `uv run --no-sync python tools/check_docstrings.py`: ok: every definition in 25 module(s) is documented.
- `uv run --no-sync python tools/check_public_annotations.py`: ok: every public definition carries a return annotation.
- `uv run --no-sync sphinx-build -W --keep-going -b html docs docs/_build/html`: build succeeded, exit 0.
- Em dash and banned-phrase grep over the new files: no matches. New and edited files are LF.

Visio oracle: none, per the brief (pure functions, nothing Visio reads).

## Deviations

1. `git apply` rejected the brief's `src/vsdxkit/errors.py` patch with "patch does not apply" at line 15, although the context lines match the file. I saved the same two hunks to a temporary patch with `git apply --recount`, which applied cleanly. `git diff` shows the intended result: the hierarchy line `+   +-- GraphError (ValueError)` after `InvalidOperationError`, and the `GraphError(VsdxError, ValueError)` class at the end of the file. The temporary patch was deleted. The brief's `tests/test_errors.py` patch applied as written.
2. One stray shell command, `cat > /tmp/x` and a write to `$TMPDIR`, failed without creating anything. Nothing was left behind.
3. Commit trailers: rules.md requires `Co-Authored-By: Claude Opus 5.5 (1M context)`. The commit uses that line exactly as rules.md specifies. The model running this task is Haiku 5.5, so the trailer may misattribute the author. The controller should confirm which line it wants.
4. `build/pr-body-3.md` was written (git-ignored) as instructed, with the attribution footer from the controller's override. It was not pushed and no PR was created.

## Concerns

- The brief's Step 5 expects `pytest` to show no failures. It does, with 47 skips that are normal for missing optional tools.
- Sphinx builds cleanly, but the new `vsdxkit.layout` module is not added to `docs/`. The brief does not ask for that, so it was left alone.

## Fix round 1

Changes in src/vsdxkit/layout.py: (1) a `parents` entry naming an undeclared group raises GraphError naming child and parent; (2) lane padding is raised to `max(lane_padding, group_padding * 2)` when groups nest (once, when lanes exist), so a nested parent's box stays inside its lane band; (3) a repeated node, lane or group id raises GraphError naming the id; (4) a group nested under a group that itself nests raises GraphError ("groups nest one level"). `_check` now also asserts each group box lies inside its lane band, which covers the 200-node test. Five new tests (nested group between lanes, undeclared parent, deep nesting, three repeated-id cases).

Red (before the source change): `18 failed, 58 passed` (11 random-graph cases with lanes and groups, the 200-node test, and the 7 new tests). Green: `76 passed` in tests/test_layout.py.

Gates:

```
2456 passed, 47 skipped in 74.96s (0:01:14)
All checks passed!
154 files already formatted
 INFO 0 diagnostics
ok: every definition in 25 module(s) is documented
ok: every public definition carries a return annotation
The HTML pages are in docs/_build/html.
```

## Fix round 2 (PR #475, head 113d72a)

All in src/vsdxkit/layout.py with tests in tests/test_layout.py. Red before the source change: `21 failed, 76 passed` (tests/test_layout.py). Green after: `97 passed`.

1. Group across lanes: GraphError naming the group and the lanes (test_a_group_spanning_two_lanes_is_refused_by_name). Members are collected once, before slots are built.
2. Page size: after v placement the group boxes' extents plus padding (nested padding included) and one grid step are measured; the page grows and every coordinate shifts by a grid-aligned offset (`shift_u`, `shift_v`). `_check` now asserts every node and group box lies in 0..width, 0..height. Tests: padding 0.8 over margin 0.1, nested or not, both directions. Lane bands are not in that assertion because a lane's centre and size snap separately (up to half a step); lane padding gained 2 grid steps so group boxes still stay inside the band after snapping.
3. lane=None with lanes declared: GraphError naming the node.
4. Dummy slots are keyed `(edge number, layer)` tuples (`_Key = str | tuple[int, int]`); test uses node id "\x002:1", the exact old key, which collided before.
5. Child repeated in `parents`: GraphError naming the child.
6. Size: width and height must be finite and POSITIVE (zero rejected too). No existing test, helper or dummy slot uses a zero-size LayoutNode (dummies are not LayoutNodes).
7. Snapping: slot extents are rounded up to the grid (`_ceil`) and packing gaps get one extra grid step, so the drawn boxes (snapped sizes, snapped centres) keep at least `node_gap`. Test: heights 0.8 and 1.23 with node_gap=0.001. Side effect: spacing grows by 0.01 inch.
8. Self-loops: chose to reserve clearance, not to refuse. When any self-loop exists the in-layer gap is at least 0.2 and the layer gap at least 0.3 (the loop's reach), so existing tests and callers keep working. Test: two 1-inch nodes, node_gap=0.1, loop on the second.
9. `snap` derives its decimals from GRID (`-floor(log10(GRID))`); test monkeypatches GRID to 0.001.

Gates: pytest `2477 passed, 47 skipped`; `ruff check` clean; `ruff format --check src tests` clean (the repo-wide check reports 9 files, unchanged from before this round: markdown code blocks in README and docs); pyrefly `0 errors`; check_docstrings and check_public_annotations ok; Sphinx `-W` build succeeds.

## Fix round 3 (threads 4240620229 A, 4240620232 B, 4240620234 C)

All four changes are in src/vsdxkit/layout.py with tests in tests/test_layout.py.

- A: node slots round up to an even number of grid steps (`_even`) and the returned Box uses those slot extents, so a box, packing and route attachment share one extent. Red: `test_a_box_has_the_extent_the_routes_attach_to` 4 failed (zero-width box, endpoint off the border). Green: passes.
- B: the page extents and shift now include each self-loop's bend (along and across the flow), both directions. Red: `test_a_self_loop_stays_on_the_page_when_the_margin_is_small` 2 failed. Green: passes.
- C: parallel edges (grouped by layout-direction endpoints, so a cycle's reversed twin counts) leave and arrive at distinct `_spread` offsets inside the border; parallel self-loops nest with larger radius/protrusion and mirrored return offsets, and the loop clearance reserved in the gaps grows 0.1 in per extra loop. Red: `test_parallel_edges_get_distinct_routes` 4 failed. Green: passes. Ceiling: a node narrower than the number of parallel edges in grid steps gets identical offsets (marked ponytail).
- D: `test_random_small_graphs_with_parallel_edges_and_loops_route_cleanly` (30 seeds x 5 configs, margin 0.1, parallel edges, reversed twin, parallel loops, lanes/groups, both directions; checks overlap, lanes, page bounds, endpoints on borders, no identical route). Red before the fixes: 150 of 150 failed. It exposed a real defect even after A-C: slot centres at half-grid ties snapped independently of their border points (box.y 1.41 vs route end y 1.8 against a top border of 1.81), so a route ended one grid step off the border in 16 cases. Fixed by snapping slot centres (`m.v`, `centre_u`). Green: all 150 pass.

Gates: pytest tests 2637 passed 47 skipped; ruff check and format --check clean; pyrefly 0 errors; check_docstrings and check_public_annotations ok; Sphinx build -W succeeded.
