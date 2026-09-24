# Phase 5E: a checked migration guide (#112, part 1 of 2)

Part of the 1.0 API cutover (#108-#112). Stacked on #408 (`SwimlaneDiagram`).
Authority: `.hermes/plans/2026-09-12_simplification-usability-refactor.md`,
Phase 5 acceptance and "Definition of done": the migration guide contains
every removed documented call from the first breaking PR onward.

#112 lands as two PRs:

1. **This one:** the checker, and the guide entries for every name and
   behaviour already gone since 0.8.0.
2. **5F:** remove the 0.x names still present and add their entries. It also
   rewrites README, quickstart, `find_shape.rst` and `classes.rst` for 1.0.

## Baseline

0.8.0 is the last release: #349, the release PR, has not been merged, so
everything since the `v0.8.0` tag is unreleased. The package imported as
`vsdx` then.

`tools/api-0.8.0.txt` is 0.8.0's public surface, generated once from the tag:

- every name in `vsdx.__all__`;
- every public name a `vsdx` module defined (not ones it imported, loggers or
  type variables);
- every public class-level member of a class it defined, including
  inherited members from `vsdx` bases.

Instance attributes (`zip_file_contents`, `directory`, `debug`) are not
visible to the snapshot, so the guide covers them by hand.

## The check

`tools/check_migration_guide.py`, run in CI after the annotations gate:

- `vsdx.<m>.<name>` is looked up as `vsdxkit.<m>.<name>`. The exceptions are
  `VisioFile`, which becomes `vsdxkit.document.Document`, and `Container`,
  which becomes `vsdxkit.swimlanes.SwimlaneDiagram`.
- A name 1.0 does not have must appear as an identifier in an inline literal
  or a code-block line of `docs/migration-1.0.rst`.
- A member of a class that is gone is covered by the class's own entry.
- A member of a class that moved to another module is looked up there.
- A root name must appear as `from vsdx import <name>`.

## Guide entries added

- The import package rename, and the root imports with one entry per
  `vsdx.__all__` name.
- Errors are one hierarchy (#365).
- A save writes only what changed, and document parts refuse `None` (#373).
- Parts are named by part name, covering:
  - `filename` (#380);
  - `zip_file_contents`, `directory` and the `xmlio` file helpers (#381);
  - `to_float`, the content-type constants, `PackageLimits`, `DocumentPart`
    and `MastersImportMixin`.
- Pages and shapes are collections (#392, #393, #397).
- A shape is its element (#395, #396).
- `Media` (#398), and `Shape.copy()` with no page.
- Retarget keeps glue, routing and points, with its new refusals (#401). The
  earlier entry wrongly said "as before".
- The swimlane constants moved to `vsdxkit.swimlanes`.
