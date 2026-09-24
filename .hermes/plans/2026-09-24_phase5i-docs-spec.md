# Phase 5I: the primary docs describe 1.0 only (#112, part 5 of 5)

Part of the 1.0 API cutover (#108-#112). Stacked on #412 (the connection
records made internal). Authority:
`.hermes/plans/2026-09-12_simplification-usability-refactor.md`, Phase 5
acceptance ("no old public names in any module, test or primary doc") and the
definition of done ("The README common path uses only the target 1.0 API").

This closes #112.

## How the old names were found

The guide check's own list of removed names drives the sweep. It is every
0.8.0 name the check would ask the guide to explain if the guide were empty,
minus names 1.0 still defines somewhere. Each of those names was searched for
in the README, the Sphinx pages other than the guide, `src`, `tests` and
`tools`. What remains is on purpose:

- the migration guide;
- tests that assert a 0.x name is gone;
- history in test docstrings ("0.x's `Page.set_name` ...");
- words that only share a spelling with a removed name (`debug`, `directory`,
  `members`, the `ConnectObservation.connects` of the Visio harness).

## README

- The 0.x notice becomes a 1.0 notice that points to the migration guide.
- "Find shapes" is new. It covers `page.shapes` against `page.children`,
  the `require_*`/`by_*`/`matching_*` contract and a comprehension, and it
  runs under `test_readme_workflow.py`, which now counts seven examples.
- "Re-anchor" becomes "Retarget". The regular-expression finder claim goes,
  and so do the `Connect` records.

## Sphinx

- `index.rst`: the same notice.
- `quickstart.rst`: the lookup contract replaces "finder methods".
- `find_shape.rst`: the detached-shape paragraph lists every attribute that
  stays readable, as the guide does. "Earlier finders" points to the guide
  without naming the 0.x methods.
- `create_connect.rst`, `templating.rst`: no `Connect` records.
- `classes.rst`: it lists the user-facing members it had left out. For `Page`
  these are `name`, `width`, `height`, `background` and `find_replace`. For
  `Shape` they are `angle`, the begin and end coordinates, `cell_formula`,
  `set_cell_value`, `set_cell_formula`, `master_shape` and `universal_name`.
  `ConnectorOptions` gains its fields. `Connector` shows that it is a
  `Shape`.

## Not here

The `Document` members that are package internals are still public, among
them the ID helpers, the `jinja_*` hooks and `copy_shape`. Phase 6 replaces
the templating mixin and Phase 7 removes dead methods, so they are not
documented and not renamed here.
