# Phase 7, part 2: the public surface is decided, documented and generated

Epic #29, issue #424, and the points still open from Phase 6 (#28). Stacked on 7c (#425).

Authority:
- the maintainer's request of 2026-09-26: "Stack on fixes for the owed phase 6, and review the API misses, we need to identify what should be public, what should be private and document everything in docstrings regardless. I want the API docs auto generated";
- the maintainer's five decisions of the same day, recorded below;
- the Phase 7 spec (`.hermes/plans/2026-09-26_phase7-spec.md`), whose first goal this finishes.

## Goal

After this part:

- **The public surface is decided.** Every name pyright `--verifytypes` exports from the wheel is user API on purpose. Every other name starts with an underscore, in its own name or its module's.
- **Every definition in `src/vsdxkit` has a docstring,** public or private. That covers modules, classes, functions, methods, properties, module constants, class attributes and enum members. A gate enforces it.
- **The API reference is generated.** `docs/classes.rst` and its hand-kept `:members:` lists are gone. The reference is built from the docstrings, and a gate fails when an exported name is missing from it.
- **The points owed from Phase 6 are closed:**
  - `PageView` is writable;
  - two of the three older bugs the missing Codex review found, F2 and F3, are fixed, and so is the copy-source check, which predates Phase 6;
  - the third, F1 (the style bug), is recorded on #125 and #126, where its fix will happen.

Nothing changes a saved file except the three bug fixes, each of which is a behaviour change named below.

## Where things stand (refactor/phase7c-gates at 19f74ff)

Taken from three read-only investigations. Their notes are in the session scratchpad under `p7d/`: `classification.md`, `docstrings.md`, `autodoc-spike.md` and `phase6-owed.md`.

**The surface.**
- 196 exported names are neither documented nor private (#424), plus the 8 public names of `shape_tree`, which 7c documented.
- Of those 204: 51 are user API, 150 are internals, and 3 are dead.
- Ten modules are internal throughout: `formulae`, `inheritance`, `logging_support`, `masters`, `media`, `partnames`, `relationships`, `shape_part`, `shape_tree` and `xmlio`.
- `connectors` will have no public name once its duplicate `namespace` goes.
- Two public modules each hold one block of internals: `package` (the store, apart from `PackageLimits`) and `glue` (the cell planners and the `Connect` records, apart from the options and enums).

**Docstrings.**
- 444 of 833 definitions have none: 258 of 477 public, 186 of 356 private.
- One constant has a `#:` comment (`SHEET_REFERENCE`), and none of the 84 Protocol stubs has a docstring.
- Ruff's `D` rules cannot enforce this. They are silent on everything in a `_module.py`, on underscored names, on setters, on `@override` methods and on constants (probed with ruff 0.16.7).

**The reference.**
- `docs/classes.rst` lists members by hand. That list drifting from the code is how #424's `Shape` members went missing.
- A spike built the docs both ways. Built-in `autosummary` silently dropped 40 exported names, the constants that have no `#:` comment. `sphinx-autoapi` dropped none.
- Turning generation on surfaced two docstrings that are not valid reST (in `logging_support.py` and `swimlanes.py`), which fail `-W`.
- `docs/templating.rst` embeds `autofunction`/`autoclass`, which would duplicate the generated entries.

**Phase 6's open points.**
- Codex never reviewed #415–#417. The review has now been done. It found no regression those PRs introduced, and three older bugs in the code they moved:
  - **F1:** a connector's style is matched by ID alone, which is the dropped "use names for match" note. Its fix belongs to issues #125 and #126.
  - **F2:** a page's `{% showif %}` is judged by its rendered string, so `None` and `0.0` keep the page, while a shape with the same `showif` is removed.
  - **F3:** page names are not rendered as templates, although `Document.render`'s docstring and `docs/templating.rst` say they are. A `showif` that does not open the name is never stripped either (`re.match` where `re.search` is meant).
- **`PageView` is read-only.** It declares no setters where `Page` has five (`name`, `background`, `width`, `height`, `xml`). Typed code cannot write `shape.page.name = "x"`, although it works at runtime.
- **`shape.copy` onto a removed page** raises `InvalidOperationError`. That is a Phase 6 behaviour change, and the guide does not mention it. `Shape.copy` never checks its *source*: `deleted_shape.copy()` brings a deleted shape back, and a shape on a removed page copies onto a live one. `create_shape(prototype)` refuses both. This predates Phase 6.

## Decisions

### The maintainer's decisions (2026-09-26)

1. **Private by default.** A name that could go either way becomes private: making it public later breaks nothing, and making it private after 1.0 does.
   - The raw-XML helpers (`shape_tree`, and all of `xmlio` including `parse_part`, `serialise_part` and `pretty_print_element`) are private.
   - So are `formulae.calc_value`, `partnames`, and the content-type constants.
   - The root's XML namespace constants stay public, because a user reading `shape.xml` needs them.
2. **The reference is generated by `sphinx-autoapi`.**
3. **`PageView` is writable:** all five setters, matching `Page`.
4. **The small older bugs are fixed here,** test-first: F2, F3, and the copy source check. F1 goes to its issues, #125 and #126, with the reproductions.
5. **The bundled-donor folder `media/` becomes `_bundled/`.** Decided after the maintainer reviewed the plan; see "The migration guide follows the surface".

### Rulings made from those decisions

These rulings are mine, not the maintainer's. Each follows from decision 1 or from the investigation, and each is listed here so it can be overturned.

- **How a name becomes private: a hybrid.**
  - A module that is internal throughout is renamed with a leading underscore.
  - A public module with internals underscores them in place.
  - Where those internals form one block, the block moves to a new underscored module. That keeps the call sites' names and avoids about 114 `PackageStore` renames in tests.
  - Pyright, `autoapi` and the import-graph test all treat `_module` and `_name` as private already. The migration checker already skips `_*.py`.
- **Eleven modules are renamed:** `_formulae`, `_inheritance`, `_logging_support`, `_masters`, `_media`, `_partnames`, `_relationships`, `_shape_part`, `_shape_tree`, `_xmlio`, and `_connectors`. `connectors` goes too because it has no public name left.
- **Two blocks move:**
  - `package`'s store moves to `_package.py`, leaving `package.py` as `PackageLimits`: `PackageStore`, `XmlPart`, `BytesPart`, `PartValue`, `canonical_hash`, `check_relationship_target` and `read_archive_members`.
  - `glue`'s planners and records move to `_glue.py`, leaving `glue.py` as `ConnectorOptions`, `Glue` and `Routing`: `EndGlue`, `CellWrite`, `CellFreeze`, `CellInherit`, `CellChange`, `ConnectionRecord`, `glue_cells`, `routing_cells`, `connection_records` and `record_element`.
- **Underscored in place:**
  - every module `logger` becomes `_logger`;
  - `geometry.GeometryOwner` becomes `_GeometryOwner` (a seam, like `_PageSeam`);
  - `GeometryRow.create_row_xml`, `GeometryRow.inherited_by`, `GeometryCell.create_cell_xml` and `GeometryCell.parent_xml` are underscored, and so is `DataProperty.inherited_by`, for consistency with the row;
  - `shapes.is_connector`, `shapes.substitute`, `pages.PageLifecycle` and `swimlanes.CONTAINER_NAME` are underscored;
  - `document.DRAWING_CONTENT_TYPE` and `MACRO_ENABLED_CONTENT_TYPE` are underscored, because `document.is_macro_enabled` answers the only question they serve.
- **Duplicates of `vsdxkit.namespace` are deleted:** `connectors.namespace` and `geometry.namespace`. Each module imports the root's.
- **Deleted, as dead:**
  - `Shape.line_to_x` and `Shape.line_to_y`: no caller. The getter reads the last LineTo row while `set_line_to` defaults to the first, and the setter writes a cell that is not in the schema when the shape has no LineTo row. The replacement is `shape.geometry`.
  - `swimlanes.ROW_SWIMLANE_GUID`: its definition is its only occurrence.
- **Public, and now documented:**
  - the root's six namespace constants;
  - `errors.PackageLimitError.reason` and `PartParseError.msg`;
  - `Geometry`, `GeometryRow` and `GeometryCell` with their data members, including `GeometryRow.del_bool`;
  - `inherited` and `make_local` on `GeometryRow` and `DataProperty`;
  - the 12 `Shape` members #424 lists (`xml`, `loc_x`, `loc_y`, `append_shape`, `apply_text_filter`, `set_start_and_finish`, `relative_bounds`, `end_arrow`, `is_master_shape` and the three `*_style_id`);
  - `swimlanes.LANE_PITCH_INCHES` and `ROW_HEADING_TEXT`;
  - `templating.RenderTarget.pages`.
- **`Geometry.shape` stays public,** typed with the private `_GeometryOwner`, as `Shape.__init__` already takes `_PageSeam`. Its docstring says it is the `Shape` the section belongs to.
- **The contributor rule moves.** "Part names come only from `vsdxkit.partnames`" becomes "only from `vsdxkit._partnames`". It is a contributor rule, not user API, and the guide's sentence sending users to the module goes.
- **Constructor signatures keep their private seam types.** `Page` and `Shape` render `vis: _DocumentSeam` and `page: _PageSeam`, and no `autoapi` setting hides a real annotation. Both class docstrings already say "reach it through its document or page, do not construct it"; the rendered signature is accepted.
- **A dataclass renders its fields rather than a synthesised `__init__` call.** That is `autoapi`'s static reading. The field list carries the same information.

### The migration guide follows the surface

- `tools/check_migration_guide.py` requires an entry for every 0.8.0 name that goes private or is deleted. The investigation's simulation, run with the real checker, counts **38 new entries**, and the plan finds a 39th, `DataProperty.inherited_by`, which the simulation missed:
  - 12 in `formulae`;
  - 7 in `relationships`;
  - 6 in `xmlio`;
  - 5 on the geometry classes and `DataProperty` (`GeometryRow.create_row_xml`, `GeometryRow.inherited_by`, `GeometryCell.create_cell_xml`, `GeometryCell.parent_xml`, and the 39th, `DataProperty.inherited_by`);
  - 3 for `inheritance`;
  - 2 `namespace` copies;
  - `logging_support.get_logger`, `shapes.substitute`, and `line_to_x`/`line_to_y`.
- **At least twelve existing entries** recommend a name that is now private. The checker cannot see these, so each is rewritten by hand to name the public replacement, or "internal in 1.0; no public replacement". The plan re-counts them against the guide as it stands. They are:
  - `DRAWING_CONTENT_TYPE`/`MACRO_ENABLED_CONTENT_TYPE` (use `document.is_macro_enabled`);
  - `calc_value`;
  - `get_logger` (use `logging.getLogger("vsdxkit")`);
  - `pretty_print_element`, twice (use `ET.indent` and `ET.tostring`);
  - `file_to_xml`/`xml_to_file`;
  - `require_xml_tree`/`require_root`;
  - `shapes.to_float`;
  - `parent_of`/`find_or_create_shapes_tag` (use `shape.parent` and `group.append_shape`);
  - `vis.update_ids` (the page renumbers itself);
  - the `partnames` sentence;
  - the `ROW_SWIMLANE_GUID` line.
- No page in `docs/` or the README names a private module or name as something to use. A test checks this: it searches `README.md` and `docs/*.rst` for `vsdxkit._` and for the eleven old module names. It skips nothing: the guide spells 0.8.0 names `vsdx.<module>`, so any `vsdxkit.<old module>` in it is a 1.0 recommendation.
- `src/vsdxkit/media/`, the folder the bundled donors ship in, becomes `src/vsdxkit/_bundled/`. The maintainer decided this on 2026-09-26, after reviewing the plan. Left as it was, it would keep `import vsdxkit.media` working as an empty namespace package once `media.py` is `_media.py`.

### Every definition has a docstring

- A new `tools/check_docstrings.py` walks `src/vsdxkit/*.py` with `ast`, as `tools/check_public_annotations.py` does, and fails on any definition without documentation:
  - a module, class, function, method or property without a docstring;
  - a module-level assignment, a class-body assignment or annotation (including dataclass fields, Protocol members and enum members) without a string literal on the line after. A `#:` comment does not count: `sphinx-autoapi` reads only the string after, and a probe build rendered a `#:` comment's text nowhere.
- **Exempt:**
  - property setters and deleters, which share the getter's docstring;
  - `@overload` stubs;
  - `__all__`, which does not exist here;
  - names bound by `import`;
  - `if TYPE_CHECKING:` blocks.
  - Nothing else: private names, dunder methods, nested functions and `@override` methods all need one.
- It runs in the lint job and in `S/gates.sh`. It fails with `file:line kind name` for each gap.
- **Docstrings are for readers.** A docstring says what the thing is for and what a caller can rely on, in the project's plain style. It never just restates the name ("The logger."). A private docstring may name the seam or invariant it serves.
- Every docstring renders as valid reST under `-W`.

### The reference is generated

- **`docs/conf.py`** uses `autoapi.extension` with the settings the spike proved:
  - `autoapi_dirs = ["../src/vsdxkit"]`
  - `autoapi_root = "api"`
  - `autoapi_type = "python"`
  - `autoapi_add_toctree_entry = True`
  - `autoapi_member_order = "bysource"`
  - `autoapi_python_class_content = "class"`
  - `autoapi_options = ["members", "undoc-members", "show-inheritance", "show-module-summary", "inherited-members"]`

  `inherited-members` brings `inherited` and `make_local` onto `GeometryRow` and `DataProperty`. It also repeats `Shape`'s 56 members on `Connector`, and adds `count`/`index` to `PageCollection`. That repetition is accepted: without it, those two members appear nowhere, because pyright exports them only under the private `InheritedRow`. `sphinx-autoapi` joins the `docs` dependency group, pinned like the rest.
- **`docs/classes.rst` is deleted.**
  - Its prose moves into module docstrings. The Errors section and its hierarchy diagram go into `errors`' module docstring, and the "import each class from its module" note goes into the root's.
  - `docs/index.rst` drops it from the toctree.
  - Topic pages keep their `:class:` cross-references; the spike confirmed they resolve against the generated pages.
- **`docs/templating.rst`'s embedded `autofunction`/`autoclass`** become `:func:` and `:class:` references.
- **`tests/test_views_agree.py`'s check against `classes.rst`** is replaced by the documentation gate below.
- **A documentation gate.** `tools/check_api_documented.py` loads the built `objects.inv` and fails on any name in pyright's exported-symbol report that the inventory lacks. It reads the report `check_type_completeness.py --report` already writes. Both come from the build job, so the build job also builds the docs.
  - This is the gate that ties "exported" to "documented". `-W` alone cannot catch an absence.
  - It refuses an empty report or an empty inventory, so it cannot pass on nothing.
- `sphinx-build -W` stays in the lint job, over the generated reference.

### Phase 6's open points

- **`PageView` is writable (decision 3).**
  - `shapes.PageView` declares setters for `name` (`str`), `background` (`bool`), `width` and `height` (`float | str | None`), and `xml`. The `xml` setter is typed `PartTree`, not `PartTree | None`, because mypy then rejects `Page` against the class-level `xml: PartTree`.
  - `test_the_views_are_read_only` becomes "each view's setters are exactly its class's public setters".
  - `PageView`'s docstring and the guide's `PageView` entry change to match.
- **F2: a page's `showif` is truthy exactly when a shape's is.** `templating` evaluates the page's `showif` expression with the environment's `compile_expression` and tests `bool(...)`, as `{% if %}` does. When a page name holds two showifs, both must be true, as a shape inside two `{% if %}` blocks needs.
  - **This is a behaviour change, in both directions:**
    - `None`, `0.0`, `0.00` and `set()` used to keep the page and now remove it;
    - the non-empty strings `"0"` and `"False"`, as a context read from a CSV or the environment carries them, used to remove the page and now keep it, as they always kept a shape;
    - `"none"` is kept, as before.
- **F3: page names are templates.**
  - After its `showif` is judged, a kept page's name is rendered with the context and set through `Page.name`, so the name setter's rules apply.
  - The `showif` is found anywhere in the name (`re.search`).
  - `Document.render`'s docstring and `docs/templating.rst` then say what the code does.
  - **This is a behaviour change:** `"{{ title }}"` becomes `"Quarterly"`.
- **The copy source check.** `Shape.copy` calls `self._require_attached("Shape.copy()")` before anything else. Copying a deleted shape, or a shape on a removed page, raises `InvalidOperationError` and writes nothing, as `create_shape(prototype)` already does.
  - **This is a behaviour change:** `deleted_shape.copy()` used to succeed.
  - The guide gains an entry beside "Reading or writing a deleted shape". It names the source check and the Phase 6 target check, `shape.copy` onto a removed page.
- **F1 goes to its issues.**
  - #125 (StyleSheet import by name) is updated with the current location, `document.py:493-499`, and with the two reproduced cases: the same ID naming a different style in `test_master_multiple_child_shapes.vsdx`, and the same name under a different ID.
  - #126 gets the cross-document `shape.copy` case, which is live in 1.0: the imported master names a style that is never imported.
  - This part changes no style code.

## What must not change

- Saved bytes: the save sweep stays at 28 of 28 `same` against `S/main-base/src` on every PR. The render sweep grows to 10 cases in 7d, and is 10 of 10 `same` against its PR's base in 7e and 7f. In 7d, every render-sweep difference must be one that F2 or F3 intends. The plan adds a case for each and names the expected output.
- Type completeness stays at 100.0% of what is exported. The exported count falls as names go private; the gate measures the percentage.
- Coverage stays at or above `fail_under = 97`.
- `from vsdxkit.<public module> import <public name>` works for every public name that remains. Nothing public moves module.
- The import-graph test, pyrefly strict, mypy, ruff, the annotations gate, the guide check, the sdist and wheel smokes, and the type-completeness gate all stay green. The wheel smoke's module-set check follows the renamed files.

## Delivery: three stacked PRs on #425

1. **7d, Phase 6's open points:** `PageView` writable, F2, F3, the copy source check, their guide entries, and the #125/#126 updates. It is small and independent of the surface work, so it lands first.
2. **7e, the surface:**
   - the eleven module renames and the two block moves;
   - the in-place underscores and the three deletions;
   - the 38 new guide entries and the rewrites;
   - the removal of `classes.rst`'s `shape_tree` section;
   - the memory note on `_partnames`.
3. **7f, docstrings and the generated reference:**
   - `tools/check_docstrings.py` and every missing docstring;
   - the reST fixes;
   - `sphinx-autoapi`, with `classes.rst` deleted and its prose moved into module docstrings;
   - `tools/check_api_documented.py` in CI;
   - CONTRIBUTING describing both gates.

   It comes last, so the docstrings are written against the final names.

Each PR gets the Phase 7 verification: per-task reviews, a spec-alignment review, the save and render sweeps, the wheel and sdist smokes, and CI on the pushed head. A final whole-branch review follows 7f.

## Out of scope

- F1's fix (#125, #126).
- #319.
- Folding `Cell` and `GeometryCell` together.
- Renaming `GeometryRow.del_bool`.
- Phase 8: the version and the classifier.
- Codex review of this part's PRs, which depends on its quota.
