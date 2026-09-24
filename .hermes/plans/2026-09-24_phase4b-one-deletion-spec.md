# Phase 4B: one deletion operation (#105)

**Status:** Implementing. Stacked on Phase 4A (#398).
**Plan:** `2026-09-12_simplification-usability-refactor.md`, Phase 4 "Deletion and attachment".
**Issue:** #105 (10B-B2).

## What was already true

Earlier work had delivered most of #105:
- **One path.** `Page.delete_shape` removes the shape and, for a group, its members. It also removes every connector glued to any of them and every `Connect` record naming them. `Shape.remove()` warns and calls it.
- **Detachment is computed (#395).** Every Shape held for a removed element answers `is_attached` False and refuses reads and writes. That includes a cascade-deleted connector.
- **The raw removal is private.** `Page._remove_shape_xml` is the only code that takes a shape element out of its container.

## The gap

Jinja `{% showif %}` removed shapes by rendering them out of the page's XML. That is a second deletion path, and it did none of the cascade: a connector glued to the hidden shape survived, holding a `Connect` record that named a shape no longer on the page.

## Decisions

**D1. `Page._delete(shapes, gone_ids)` is the one deletion.**
- **What it does:** it removes `shapes`, every connector glued to a shape in `gone_ids`, and every record naming any of them.
- **`gone_ids`** also takes shapes already gone from the XML by another route.
- **`delete_shape`** validates, then calls it.
- **The renderer** compares the page's shape IDs before and after rendering. It calls `_delete((), hidden)` for the IDs that vanished.

**D2. Empty `<Shapes>` and `<Connects>` containers are left in place.** VisioSchema15 allows both empty (`minOccurs="0"` for `Shape` and `Connect`), so removing them would be cosmetic.

**D3. #334 is out of scope.** It covers `Sheet.N!` references in other shapes' formulas to a deleted shape. Its issue records why it is separate work: each reference needs its own replacement.

## Tests (`tests/test_shape_removal_cascade.py`)

- **These already pass**, pinning semantics the issue names:
  - a half-glued connector goes with the one shape it is glued to;
  - deleting a connector directly leaves the shapes it joined and their other glue;
  - every shape a delete takes, cascaded connectors included, is detached.
- **These fail on #397:**
  - a shape a showif hides takes its connectors and records;
  - a connector a showif hides takes only its own records.

## Not run here

The COM oracle needs Windows Visio.
