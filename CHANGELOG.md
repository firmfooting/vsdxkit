# Changelog

This changelog covers `vsdxkit`. The project it descends from, and whose
history precedes 0.6.3 here, remains available at
<https://github.com/dave-howard/vsdx>.

From 0.7.1 onward this file is maintained by release-please, which writes a
section per release from the conventional-commit subjects on `main`. Edit the
release pull request rather than this file directly.

## [0.9.0](https://github.com/firmfooting/vsdxkit/compare/v0.8.0...v0.9.0) (2026-09-28)


### ⚠ BREAKING CHANGES

* moving a shape moves the shape, and a 1-D shape's text sits on it ([#455](https://github.com/firmfooting/vsdxkit/issues/455))
* writes to an instance stay on the instance, and a deleted shape stays deleted ([#454](https://github.com/firmfooting/vsdxkit/issues/454))
* one cell writer, and a value written is the value Visio shows ([#453](https://github.com/firmfooting/vsdxkit/issues/453))
* the 1.0 public surface is only the user API; internal modules and names are private ([#424](https://github.com/firmfooting/vsdxkit/issues/424)) (#429)
* PageView is writable; page showifs and names follow the template rules; Shape.copy checks its source ([#28](https://github.com/firmfooting/vsdxkit/issues/28)) (#428)
* the package internals are private, and the page allocates shape IDs ([#116](https://github.com/firmfooting/vsdxkit/issues/116)) (#423)
* the dead members go, and one read-a-part-or-raise ([#116](https://github.com/firmfooting/vsdxkit/issues/116)) (#422)
* the back-references are read-only views, and every import points down ([#114](https://github.com/firmfooting/vsdxkit/issues/114)) (#419)
* templating is a function; Document has no mixin base ([#113](https://github.com/firmfooting/vsdxkit/issues/113)) (#416)
* the connection records are internal ([#412](https://github.com/firmfooting/vsdxkit/issues/412))
* Shape.delete, and pages change only through the collection ([#411](https://github.com/firmfooting/vsdxkit/issues/411))
* the 0.x traversal names go; collections are the one walk ([#410](https://github.com/firmfooting/vsdxkit/issues/410))
* SwimlaneDiagram replaces Container ([#408](https://github.com/firmfooting/vsdxkit/issues/408))
* Connector(Shape), Page.connect and graph queries ([#406](https://github.com/firmfooting/vsdxkit/issues/406))
* ShapeKind and Page.create_shape ([#405](https://github.com/firmfooting/vsdxkit/issues/405))
* Document replaces VisioFile ([#403](https://github.com/firmfooting/vsdxkit/issues/403))
* a document has no close state ([#402](https://github.com/firmfooting/vsdxkit/issues/402))
* one connector engine, glue as data ([#401](https://github.com/firmfooting/vsdxkit/issues/401))
* one creation operation, and donors loaded once per process ([#398](https://github.com/firmfooting/vsdxkit/issues/398))
* no synthetic <Shapes> wrapper, and each finder written once ([#397](https://github.com/firmfooting/vsdxkit/issues/397))
* shapes and pages read their XML, and the one memo left has a counter ([#396](https://github.com/firmfooting/vsdxkit/issues/396))
* a Shape is its element, and a deleted shape says so ([#395](https://github.com/firmfooting/vsdxkit/issues/395))
* `VisioFile.pages` is a read-only `PageCollection` rather than a `list`. Use `pages.create`, `pages.copy` and `pages.delete` to change pages.
* `Page.shapes` is now the recursive `ShapeCollection` of every shape on the page, not the deprecated list holding the page's `<Shapes>` wrapper.
* `VisioFile` no longer inherits `MastersImportMixin`, and `master_pages` and `master_index` are read-only.
* import every name from the module that defines it ([#383](https://github.com/firmfooting/vsdxkit/issues/383))
* `VisioFile.zip_file_contents`, `VisioFile.directory`, the `vsdxkit.zip_contents` module and `PackageStore.write_bytes_keeping_tree` are removed. So are `vsdxkit.xmlio.file_to_xml`, `xml_to_file`, `require_xml_tree` and `require_root`, and `vsdxkit.vsdxfile.file_to_xml`. Work on a document through its object model; to read raw part bytes, open the saved file with `zipfile`. `parse_part(bytes)` and `serialise_part(tree)` replace the `xmlio` helpers.
* `Page.filename` and `Page.rels_xml_filename` hold OPC part names such as `/visio/pages/page1.xml` instead of a path under the source file's name. `insert_shape`'s `page_path` takes the same part name.
* the library's exceptions are now a hierarchy under `vsdxkit.VsdxError`, defined in `vsdxkit.errors`.
    - `VisioFileNotOpen` now derives from `ValueError`, through
    `InvalidOperationError`. A `try` with both `except ValueError:` and
    `except VisioFileNotOpen:` takes the `ValueError` branch unless
    `VisioFileNotOpen` is listed first.
    - `PackageLimitError` and `VisioFileNotOpen` are defined in
    `vsdxkit.errors`, so their `__module__` changed.
    `vsdxkit.vsdxfile.PackageLimitError`,
    `vsdxkit.package.PackageLimitError` and
    `vsdxkit.vsdxfile.VisioFileNotOpen` still resolve to the same classes.
    - Opening a package raises `vsdxkit.MalformedPackageError` where it used
    to raise one of these builtins:
      - `zipfile.BadZipFile`: not a zip, truncated, or a CRC mismatch
    - `NotImplementedError`: an unsupported zip version or compression
    method
      - `RuntimeError`: an encrypted member
    - `zlib.error`, `lzma.LZMAError`, or an `OSError` with no `errno`: a
    corrupt compressed stream
      - `UnicodeDecodeError`: a member name flagged UTF-8 that is not
    - `LookupError`, or `ValueError`: a part declaring an encoding that
    cannot be decoded or that the parser refuses
    - `KeyError`: a `pages.xml`, `masters.xml` or relationship element
    missing a required attribute
* save only what changed, byte for byte ([#373](https://github.com/firmfooting/vsdxkit/issues/373))
* move to a src layout and rename the import package to vsdxkit ([#350](https://github.com/firmfooting/vsdxkit/issues/350))

### Features

* a document has no close state ([#402](https://github.com/firmfooting/vsdxkit/issues/402)) ([dc5c6cb](https://github.com/firmfooting/vsdxkit/commit/dc5c6cb6473ccfddca09bb379bcab418a4a58e31))
* a Shape is its element, and a deleted shape says so ([#395](https://github.com/firmfooting/vsdxkit/issues/395)) ([60872c5](https://github.com/firmfooting/vsdxkit/commit/60872c5c6366f5776f295f7cdcc642c05b722c1b))
* Connector(Shape), Page.connect and graph queries ([#406](https://github.com/firmfooting/vsdxkit/issues/406)) ([449c0f7](https://github.com/firmfooting/vsdxkit/commit/449c0f7f0ed2d770c81d9a4e87ab7e9a0f8a5ca3))
* Document replaces VisioFile ([#403](https://github.com/firmfooting/vsdxkit/issues/403)) ([ef717d7](https://github.com/firmfooting/vsdxkit/commit/ef717d76c1c4bfd3e6d854e23b895e81ba479315))
* hold the package as parts addressed by OPC part name ([#355](https://github.com/firmfooting/vsdxkit/issues/355)) ([4ac48f9](https://github.com/firmfooting/vsdxkit/commit/4ac48f96b0d9d2de479be1f5eb5d82e9fcd7454c))
* no synthetic &lt;Shapes&gt; wrapper, and each finder written once ([#397](https://github.com/firmfooting/vsdxkit/issues/397)) ([6b76e4e](https://github.com/firmfooting/vsdxkit/commit/6b76e4eee97b3f351bc83c5c05ba506d6c990956))
* one connector engine, glue as data ([#401](https://github.com/firmfooting/vsdxkit/issues/401)) ([d95b64d](https://github.com/firmfooting/vsdxkit/commit/d95b64d26aa7645cbbf50c3f59d842998663b6cd))
* one creation operation, and donors loaded once per process ([#398](https://github.com/firmfooting/vsdxkit/issues/398)) ([a2bb9e7](https://github.com/firmfooting/vsdxkit/commit/a2bb9e7f0838aa4d59c7fb979389af321935cb10))
* PageCollection, a document's pages and the one place pages change ([#393](https://github.com/firmfooting/vsdxkit/issues/393)) ([07fd086](https://github.com/firmfooting/vsdxkit/commit/07fd086085bfe9fb6b0f90998bd3c95dedf8e121))
* raise a named error hierarchy instead of bare ValueErrors ([#365](https://github.com/firmfooting/vsdxkit/issues/365)) ([6f17506](https://github.com/firmfooting/vsdxkit/commit/6f175069df16a928812e1e409a46feffc5ebae85))
* save only what changed, byte for byte ([#373](https://github.com/firmfooting/vsdxkit/issues/373)) ([769fe87](https://github.com/firmfooting/vsdxkit/commit/769fe87c0e121f983f5d5bc2364b99c35ecf21a9))
* save the package store through one atomic archive writer ([#370](https://github.com/firmfooting/vsdxkit/issues/370)) ([05b9cda](https://github.com/firmfooting/vsdxkit/commit/05b9cda6762d2feba4024daf6567d82873362a88))
* Shape.delete, and pages change only through the collection ([#411](https://github.com/firmfooting/vsdxkit/issues/411)) ([6da9920](https://github.com/firmfooting/vsdxkit/commit/6da9920848dd0741619125d09d88dde14c9ccc29))
* ShapeCollection, one scoped lookup that says how many shapes it expects ([#392](https://github.com/firmfooting/vsdxkit/issues/392)) ([ebf6fa8](https://github.com/firmfooting/vsdxkit/commit/ebf6fa8e8b7af5bc83594d1cfb2ba5e03009cbc3))
* ShapeKind and Page.create_shape ([#405](https://github.com/firmfooting/vsdxkit/issues/405)) ([0d7eb5d](https://github.com/firmfooting/vsdxkit/commit/0d7eb5d5dfb8ff8db7138a84125589c4e28eda9f))
* shapes and pages read their XML, and the one memo left has a counter ([#396](https://github.com/firmfooting/vsdxkit/issues/396)) ([04b0995](https://github.com/firmfooting/vsdxkit/commit/04b0995daf7c2d318585c8d7fdf12c6f35995316))
* SwimlaneDiagram replaces Container ([#408](https://github.com/firmfooting/vsdxkit/issues/408)) ([565361f](https://github.com/firmfooting/vsdxkit/commit/565361f9eb312d0d8a429432cb8061334ac3be48))
* templating is a function; Document has no mixin base ([#113](https://github.com/firmfooting/vsdxkit/issues/113)) ([#416](https://github.com/firmfooting/vsdxkit/issues/416)) ([e79d4d3](https://github.com/firmfooting/vsdxkit/commit/e79d4d3009c2f20abe36aa28fe09c12138262bfd))
* the 0.x traversal names go; collections are the one walk ([#410](https://github.com/firmfooting/vsdxkit/issues/410)) ([fae67fe](https://github.com/firmfooting/vsdxkit/commit/fae67fe452564b27940716886fe73c3075b0c140))
* the back-references are read-only views, and every import points down ([#114](https://github.com/firmfooting/vsdxkit/issues/114)) ([#419](https://github.com/firmfooting/vsdxkit/issues/419)) ([0d3cd9b](https://github.com/firmfooting/vsdxkit/commit/0d3cd9b59384f947578a4552979390e3a9cc29a4))
* the connection records are internal ([#412](https://github.com/firmfooting/vsdxkit/issues/412)) ([7b3a376](https://github.com/firmfooting/vsdxkit/commit/7b3a3760867024b1b1c12b24bbf188b709ad7fda))
* the dead members go, and one read-a-part-or-raise ([#116](https://github.com/firmfooting/vsdxkit/issues/116)) ([#422](https://github.com/firmfooting/vsdxkit/issues/422)) ([4e96a93](https://github.com/firmfooting/vsdxkit/commit/4e96a93df07aa9f2731fb8483107b74f5d89a64b))
* the package internals are private, and the page allocates shape IDs ([#116](https://github.com/firmfooting/vsdxkit/issues/116)) ([#423](https://github.com/firmfooting/vsdxkit/issues/423)) ([31c863f](https://github.com/firmfooting/vsdxkit/commit/31c863f5170d4a2007d50e7bce72f8ceeb2c8160))


### Bug Fixes

* a formula with an unknown input has no value; the stack's open review comments are answered ([#28](https://github.com/firmfooting/vsdxkit/issues/28), [#29](https://github.com/firmfooting/vsdxkit/issues/29)) ([#451](https://github.com/firmfooting/vsdxkit/issues/451)) ([3575873](https://github.com/firmfooting/vsdxkit/commit/3575873edbd182621da67a68d06ab99e15afcb47))
* count an app.xml change in the section it was made in ([#369](https://github.com/firmfooting/vsdxkit/issues/369)) ([8920d34](https://github.com/firmfooting/vsdxkit/commit/8920d3419d71041cb885d3ca70b72ed3511d2f7b))
* find app.xml's page section on a file whose producer did not write English ([#363](https://github.com/firmfooting/vsdxkit/issues/363)) ([a9b6d77](https://github.com/firmfooting/vsdxkit/commit/a9b6d77da6fec6a101c365622b2ee7320faf32ab))
* moving a shape moves the shape, and a 1-D shape's text sits on it ([#455](https://github.com/firmfooting/vsdxkit/issues/455)) ([df1e399](https://github.com/firmfooting/vsdxkit/commit/df1e399bc1eb60710be29f23cac7f6822c59212d))
* name a new page in app.xml's Pages section, not among the masters ([#356](https://github.com/firmfooting/vsdxkit/issues/356)) ([014352e](https://github.com/firmfooting/vsdxkit/commit/014352e991851fe7e331f9acac5c40c43284f51d))
* one cell writer, and a value written is the value Visio shows ([#453](https://github.com/firmfooting/vsdxkit/issues/453)) ([6ed09f8](https://github.com/firmfooting/vsdxkit/commit/6ed09f80a32b30a00f1b7c72c1e8cc5e9ff5b4ea))
* one deletion operation, and a shape a showif hides is deleted like any other ([#399](https://github.com/firmfooting/vsdxkit/issues/399)) ([3d1dad5](https://github.com/firmfooting/vsdxkit/commit/3d1dad5d1257434887f802fd1122143c0a27b9ab))
* PageView is writable; page showifs and names follow the template rules; Shape.copy checks its source ([#28](https://github.com/firmfooting/vsdxkit/issues/28)) ([#428](https://github.com/firmfooting/vsdxkit/issues/428)) ([e15c0f1](https://github.com/firmfooting/vsdxkit/commit/e15c0f11e01507ac7061097f33df8740332ae845))
* read the whole attribute name in a {% set self.x %} reference ([#354](https://github.com/firmfooting/vsdxkit/issues/354)) ([2e82673](https://github.com/firmfooting/vsdxkit/commit/2e82673ceef5d229b4e164ea4c47947e99a75127))
* serialise the page rels and masters parts through xmlio ([#364](https://github.com/firmfooting/vsdxkit/issues/364)) ([9b4b590](https://github.com/firmfooting/vsdxkit/commit/9b4b59088f9103a52dd58f569a0dbdde54dd2788))
* **tools:** the Visio scripts kill only the Visio they started ([#463](https://github.com/firmfooting/vsdxkit/issues/463)) ([#464](https://github.com/firmfooting/vsdxkit/issues/464)) ([9bba3a4](https://github.com/firmfooting/vsdxkit/commit/9bba3a49b56866e8e88955e113c8b12873381398))
* writes to an instance stay on the instance, and a deleted shape stays deleted ([#454](https://github.com/firmfooting/vsdxkit/issues/454)) ([e54cd29](https://github.com/firmfooting/vsdxkit/commit/e54cd29ba9f2e00754be9368f21a26b82c2a9a2e))


### Documentation

* a migration guide checked against 0.8.0's whole public surface ([#409](https://github.com/firmfooting/vsdxkit/issues/409)) ([f71a34f](https://github.com/firmfooting/vsdxkit/commit/f71a34fb49191c8732edfa08abfd4c4015549242))
* apply the firmfooting brand ([#414](https://github.com/firmfooting/vsdxkit/issues/414)) ([5ef18b3](https://github.com/firmfooting/vsdxkit/commit/5ef18b3d85be04275e311b251f28346c0506a291))
* every definition has a docstring, and the API reference is generated from them ([#424](https://github.com/firmfooting/vsdxkit/issues/424)) ([#446](https://github.com/firmfooting/vsdxkit/issues/446)) ([5ed4bf9](https://github.com/firmfooting/vsdxkit/commit/5ed4bf9b4ae3de3d99a512f60025fa09f6db596c))
* Phase 6 spec and plan: templating as a function, every import arrow pointing down ([#415](https://github.com/firmfooting/vsdxkit/issues/415)) ([8039877](https://github.com/firmfooting/vsdxkit/commit/8039877089a39ce9baff5cdf4fe00325f4a8c3ec))
* Phase 7 part 2 spec and plan: the public surface decided, documented and generated ([#424](https://github.com/firmfooting/vsdxkit/issues/424)) ([#427](https://github.com/firmfooting/vsdxkit/issues/427)) ([225d411](https://github.com/firmfooting/vsdxkit/commit/225d41169ce2a13a983cfbe876346c1711a2996f))
* rework the README and docs landing page around the firmfooting brand ([#420](https://github.com/firmfooting/vsdxkit/issues/420)) ([e7ad0aa](https://github.com/firmfooting/vsdxkit/commit/e7ad0aa50221d48c32a37dad3dd1a1d810f6f365))
* say what the 0.x line actually is ([#347](https://github.com/firmfooting/vsdxkit/issues/347)) ([280e8af](https://github.com/firmfooting/vsdxkit/commit/280e8af77284c655bb291b9e39d187e39252bd82))
* the Phase 7 spec and plan: the 1.0 surface is only the user API ([#29](https://github.com/firmfooting/vsdxkit/issues/29)) ([#421](https://github.com/firmfooting/vsdxkit/issues/421)) ([f5e8a8c](https://github.com/firmfooting/vsdxkit/commit/f5e8a8cc659c35faeb93a5c3f47c929659042f16))
* the README and the Sphinx pages describe 1.0 only ([#413](https://github.com/firmfooting/vsdxkit/issues/413)) ([58536ab](https://github.com/firmfooting/vsdxkit/commit/58536ab58436592aa02fc3a946940489b3157b09))
* the writes-land spec and plan ([#452](https://github.com/firmfooting/vsdxkit/issues/452)) ([14b3955](https://github.com/firmfooting/vsdxkit/commit/14b3955e1e0a90c3de8958013e931efbb02b213e))


### Code Refactoring

* delete zip_file_contents and the helpers that served it ([#381](https://github.com/firmfooting/vsdxkit/issues/381)) ([c952e49](https://github.com/firmfooting/vsdxkit/commit/c952e49c008a78add326069b0d1a9515ee0215fa))
* import every name from the module that defines it ([#383](https://github.com/firmfooting/vsdxkit/issues/383)) ([6a7b3fc](https://github.com/firmfooting/vsdxkit/commit/6a7b3fc7d6d046b25b890ced41bcf805c49718d7))
* MasterCatalog owns every master, and VisioFile loses its mixin ([#388](https://github.com/firmfooting/vsdxkit/issues/388)) ([1c08713](https://github.com/firmfooting/vsdxkit/commit/1c08713045d9fe76277829b2aba9c0393788eada))
* move to a src layout and rename the import package to vsdxkit ([#350](https://github.com/firmfooting/vsdxkit/issues/350)) ([75e7e7c](https://github.com/firmfooting/vsdxkit/commit/75e7e7c1d8f397f2747587dd376c19d29ce219d4))
* name every part by its part name ([#380](https://github.com/firmfooting/vsdxkit/issues/380)) ([a260e80](https://github.com/firmfooting/vsdxkit/commit/a260e803fdee70f471db07d648a419a7429e2fe4))
* the 1.0 public surface is only the user API; internal modules and names are private ([#424](https://github.com/firmfooting/vsdxkit/issues/424)) ([#429](https://github.com/firmfooting/vsdxkit/issues/429)) ([5abe4ff](https://github.com/firmfooting/vsdxkit/commit/5abe4ff67e76c51288257d9d1ea4006b92a6aa11))

## [0.8.0](https://github.com/firmfooting/vsdxkit/compare/v0.7.1...v0.8.0) (2026-09-13)


### ⚠ BREAKING CHANGES

* read a shape's identity off its element, not a copy of it ([#333](https://github.com/firmfooting/vsdxkit/issues/333))
* guard the operation, not the call site, when the document is closed ([#336](https://github.com/firmfooting/vsdxkit/issues/336))
* one implementation of substituting into shape text ([#318](https://github.com/firmfooting/vsdxkit/issues/318))
* refuse mutations on a closed document ([#304](https://github.com/firmfooting/vsdxkit/issues/304))
* allocate shape ids through one path that owns set_max_ids ([#270](https://github.com/firmfooting/vsdxkit/issues/270))
* make a text colour and a lane label land, or say they did not ([#307](https://github.com/firmfooting/vsdxkit/issues/307))
* common_members returns the members the two files have in common ([#339](https://github.com/firmfooting/vsdxkit/issues/339))

### Features

* one implementation of the relationship and content-type operations ([#344](https://github.com/firmfooting/vsdxkit/issues/344)) ([c300c4f](https://github.com/firmfooting/vsdxkit/commit/c300c4f58666fd340ea9d1b30a68a91641311bbb))


### Bug Fixes

* allocate ids for every descendant when copying a group ([#275](https://github.com/firmfooting/vsdxkit/issues/275)) ([f180d20](https://github.com/firmfooting/vsdxkit/commit/f180d203ce784a80c4ee48af8e7c06212f3eedbe))
* allocate shape ids through one path that owns set_max_ids ([#270](https://github.com/firmfooting/vsdxkit/issues/270)) ([615212f](https://github.com/firmfooting/vsdxkit/commit/615212f2f9d1a112d0838158d0a4f58cc6341eae))
* build a swimlane before putting it on the page ([#340](https://github.com/firmfooting/vsdxkit/issues/340)) ([ebeff71](https://github.com/firmfooting/vsdxkit/commit/ebeff71d11bc7df4913e67c31866ec3f10d2da19))
* common_members returns the members the two files have in common ([#339](https://github.com/firmfooting/vsdxkit/issues/339)) ([cfba91e](https://github.com/firmfooting/vsdxkit/commit/cfba91ebb536572d8e3a936158d34f30fd53aa36))
* copy an inherited row onto the instance before writing to it ([#272](https://github.com/firmfooting/vsdxkit/issues/272)) ([2f582a4](https://github.com/firmfooting/vsdxkit/commit/2f582a46bc4957ac14731e71da1e57bff33cd513))
* give atan2 the rise before the run in formulae.angle ([#332](https://github.com/firmfooting/vsdxkit/issues/332)) ([8302be7](https://github.com/firmfooting/vsdxkit/commit/8302be7e229e5a6ff9bf02dffdb89f07acb4b637))
* guard the operation, not the call site, when the document is closed ([#336](https://github.com/firmfooting/vsdxkit/issues/336)) ([69af217](https://github.com/firmfooting/vsdxkit/commit/69af2179d575e8e8d15bed7a3a903c180fbeca50))
* keep the namespace prefixes a document chose ([#306](https://github.com/firmfooting/vsdxkit/issues/306)) ([12fe207](https://github.com/firmfooting/vsdxkit/commit/12fe207d3447cc948e88480f32d3390df9e277ac))
* make a text colour and a lane label land, or say they did not ([#307](https://github.com/firmfooting/vsdxkit/issues/307)) ([9f6c2fb](https://github.com/firmfooting/vsdxkit/commit/9f6c2fbe032804f340f5e913699a031aa39e1ebc))
* one implementation of substituting into shape text ([#318](https://github.com/firmfooting/vsdxkit/issues/318)) ([1b06826](https://github.com/firmfooting/vsdxkit/commit/1b068267842fd56159f05ae8bbf9dbccae613f15))
* read a shape's identity off its element, not a copy of it ([#333](https://github.com/firmfooting/vsdxkit/issues/333)) ([44749cf](https://github.com/firmfooting/vsdxkit/commit/44749cf3cfbed6f9a91c701fb46d0cb131f0e5ad))
* refuse mutations on a closed document ([#304](https://github.com/firmfooting/vsdxkit/issues/304)) ([f4cf31b](https://github.com/firmfooting/vsdxkit/commit/f4cf31b86fd0981f1e4315c9e56dbf15eaa642bf))
* renumber a shape and its Connect records as one operation ([#312](https://github.com/firmfooting/vsdxkit/issues/312)) ([2de4d60](https://github.com/firmfooting/vsdxkit/commit/2de4d602e6fe13fd118232a50efdf5905ed18a9b))
* renumbering sweeps the whole page, formulas as well as records ([#341](https://github.com/firmfooting/vsdxkit/issues/341)) ([3931e51](https://github.com/firmfooting/vsdxkit/commit/3931e511d57231f589bfc83115d1c74480cf4354))
* repoint the stale-sheet-reference rule at the moved namespace constant ([#343](https://github.com/firmfooting/vsdxkit/issues/343)) ([238d4cb](https://github.com/firmfooting/vsdxkit/commit/238d4cb6eb8056a5dab453b341f65ce700697ae5))


### Performance Improvements

* resolve the master once and build geometry on demand ([#277](https://github.com/firmfooting/vsdxkit/issues/277)) ([ee3a9e6](https://github.com/firmfooting/vsdxkit/commit/ee3a9e63284ec8e04261b5691606499ef2ba27e4))

## [0.7.1](https://github.com/firmfooting/vsdxkit/compare/v0.7.0...v0.7.1) (2026-09-13)

**This release fixes a critical security defect. 0.7.0 was withdrawn from PyPI
because of it and cannot be reinstalled; upgrade to 0.7.1.**

### Security

* Jinja templates are rendered in a sandboxed environment
  ([#259](https://github.com/firmfooting/vsdxkit/pull/259))
  ([d5b735c](https://github.com/firmfooting/vsdxkit/commit/d5b735c95385032f72129e057a34484dab321d71)).

  `jinja_render_vsdx()` compiled text taken from the document being rendered —
  shape text, shape names, cell formulas — on Jinja's default environment, where
  that text is executable. A crafted `.vsdx` could reach the `os` module through
  a builtin's `__globals__` and run shell commands in the calling process, so
  rendering a document from an untrusted source was equivalent to running it.
  The context dictionary was readable by the document as well, exposing anything
  passed alongside it.

  All three compile sites now use `jinja2.sandbox.SandboxedEnvironment`. Ordinary
  templating is unchanged — loops, conditionals, filters and arithmetic behave
  exactly as before — while reaching through attributes raises
  `jinja2.exceptions.SecurityError`.

  The same defect exists in `vsdx`, the project this one descends from, in every
  released version up to and including 0.6.1. It has been reported privately to
  its maintainer as GHSA-2gwv-3c82-73r5. If you use that package, watch for its
  fix.

### Documentation

* correct attribution and release-day drift ([#265](https://github.com/firmfooting/vsdxkit/issues/265)) ([659b47b](https://github.com/firmfooting/vsdxkit/commit/659b47b5059cc186674c2d244e4e7e75f5b46035))

## 0.7.0 - 2026-09-13

**Withdrawn.** 0.7.0 was published and removed from PyPI the same day, over the
security defect fixed in 0.7.1. Everything below shipped in 0.7.1 instead. PyPI
does not permit a version number to be reused, so 0.7.0 will not return.

### Added

- The documentation is published to GitHub Pages at
  <https://firmfooting.github.io/vsdxkit/>, rebuilt on every push to `main` that
  touches the docs or the package. Sphinx autodoc reads the source, so the site
  would go stale the moment the API changed if publishing were manual. The build
  uses the same `-W --keep-going` gate as CI, so a warning cannot reach the
  published site by another route. The unused Read the Docs configuration is
  removed.
- A 0.x API notice at the top of the README and the documentation landing page:
  0.7 is the last release of the inherited API, and 1.0 renames `VisioFile` and
  `Container`, splits `Connect`, and removes the context manager.
- `tests/fixtures/com_reference/README.md` documents the COM reference corpus:
  what each scenario captured from Visio 16.0 and why, including the two
  scenarios whose COM calls failed, the `manifest.json` schema, and how to
  regenerate with `tools/com_reference.ps1`. CONTRIBUTING gains a "When a change
  needs Visio" section covering the `needs-visio` label and
  `tools/visio_check.ps1`.
- `docs/maintainers/upstream-sync.md` records how and when to check
  `dave-howard/vsdx` for fixes worth adopting, and the sync point last checked.
- CI runs the test suite on macOS as well as Linux and Windows, on the oldest
  and newest supported interpreters, which catches path-separator and
  case-sensitivity regressions before a release does.
- CI measures coverage on one matrix cell, publishes the per-file report to the
  job summary, uploads `coverage.xml` as an artifact, and fails the run below
  the `fail_under` threshold in `pyproject.toml`. The threshold starts at the
  suite's measured 90% and only ever rises.
- `Geometry`, `GeometryRow` and `GeometryCell` have direct tests, covering every
  line of `vsdx/geometry.py`: the master-geometry merge, `start_pos()`,
  `move()`, the `set_move_to()`/`set_line_to()` no-ops, and `RelMoveTo`
  handling. The tests characterise the code as it stands, faults included, and
  the docstrings now say what those faults are. `start_pos()` answers in
  shape-local coordinates for a `MoveTo` row but returns the shape's pin for a
  `RelMoveTo` one; `move()` and the coordinate setters write through an
  inherited row into the master, moving every other shape drawn from it; and a
  row added to a section is placed among the section's cells, ordered by index
  as text. Issues #239, #240 and #241 track the fixes.
- Package expansion limits: `VisioFile` inspects archive metadata before reading
  members and enforces caps on member count, per-member and total uncompressed
  size and compression ratio, and rejects duplicate and path-unsafe member names,
  raising `vsdx.PackageLimitError` with a stable `reason`. Defaults suit
  untrusted documents; trusted callers relax them via `limits=` or `limits_path=`.
- Renovate keeps the digest-pinned GitHub Actions and Python dependencies
  current, with grouped weekly update PRs and a uv lock maintenance pass.
- `VisioFileNotOpen` is now a genuine `Exception` subclass and is exported from
  the package root, so save-after-close is caught by normal `except Exception`
  handling and can be caught specifically.
- The CI build job now smoke-tests the built wheel in a clean virtual
  environment from outside the checkout: wheel contents are inspected for
  `py.typed` and both bundled media documents, and the installed distribution
  is exercised through `Media()`, `create_shape()`, connector creation, save
  and reopen before the artifact is uploaded.
- The `Connect` constructor validates its inputs and always produces a complete
  instance: the page and XML element are required, the element must be a
  namespaced `Connect` tag, and the schema-required `FromSheet`/`ToSheet`
  attributes must be present. `FromCell`/`ToCell` remain optional per the
  `Connect_Type` schema and read as `None` when absent. Invalid input raises
  `ValueError` instead of yielding an object that fails later on missing
  attributes.
- CI cancels superseded runs on the same ref via a concurrency group.
- Page `width`/`height` setters reject `None`, non-numeric and non-finite values
  and non-positive dimensions instead of silently writing `0.0`; the cell is
  left untouched on failure.
- Pyrefly runs at the `strict` preset with zero diagnostics at warning severity
  and no in-source type suppression comments.
- Every public definition (258 across the package) now carries an explicit
  return annotation, so Mypy consumers get real types instead of `Any`. A
  completeness gate (`tools/check_public_annotations.py`) and a Mypy consumer
  fixture (`tests/type_fixture.py`, run with `--disallow-untyped-calls`) keep
  the advertised typed contract checker-independent.
- Review-fix pass on merged PRs: the default `PackageLimits` are lowered to
  512 members, 64 MiB per member, 256 MiB total uncompressed and a 100:1
  ratio, so even at the caps loading materialises at most 256 MiB; the
  archive's declared entry count is checked against `max_members` before
  `ZipFile` parses the central directory; `Shape.connects`' `Connect`
  annotation is runtime-resolvable for `typing.get_type_hints` consumers; and
  `VisioFileDiff` streams members through a capped incremental decoder and
  hash instead of inflating each member wholesale. The action-pin drift
  checker is wired into CI.
- Page removal now deletes the page's relationship from `pages.xml.rels`, its
  `[Content_Types].xml` override and its page-rels part alongside the page part,
  so the OPC graph stays consistent. New pages allocate part names and
  relationship IDs from unused values instead of page count (removing a page
  then adding one no longer targets a colliding `pageN.xml`), and the returned
  `Page` carries its real page ID and relationship ID immediately.
- Typed contracts for shapes, pages, connectors, geometry, containers,
  templating, media and XML/package persistence.
- Shared required-XML helpers that report the missing package part rather than
  failing later on a `None` value.
- Regression coverage for in-place and named save destinations.
- `PagePosition.BEFORE` and `PagePosition.AFTER` now require a reference page:
  `add_page_at()` rejects them with `ValueError` instead of silently appending,
  and the resolver no longer falls back to `LAST` for invalid combinations.
  Integer, `FIRST` and `LAST` placements are asserted by index in tests.
- Current README and Sphinx guides for shape creation, connectors,
  re-anchoring, swimlanes, search and Jinja templates.
- Sphinx warning-as-error validation and a dedicated zizmor GitHub Actions audit
  in the CI gates.
- Malformed numeric ShapeSheet values raise `ValueError` naming the cell and raw
  value instead of silently reading as `0.0`; absent cells still read as `None`,
  keeping absent, malformed and genuine zero distinct.
- Package-wide import coverage now runs as a normal test across the supported
  Python and operating-system matrix.
- Test-suite strengthening: previously output-only tests now assert against
  independent expectations and reopen persisted files; a conditional-assert
  precedence bug in the end-arrow tests, an always-true assertion and an
  ignored expectations parameter are fixed; the two skipped diff tests are
  replaced with deterministic equivalents; and a four-mutant kill run
  documents that the new tests fail when the behaviour they name is broken.

### Fixed

- Every XML part is serialised with the namespace prefixes Visio itself writes.
  `ET.register_namespace` evicts any previous holder of a prefix, so registering
  four namespaces as the default left only the last one holding it and every
  Visio element serialised under a generated `ns0:` prefix. libvisio, which
  backs LibreOffice Draw's import filter, and draw.io's importer are stricter
  about prefixes than Visio is and reject such a package. Prefixes are now
  applied per part, so each part carries its own root vocabulary as the default.
  A CI job converts library output through LibreOffice Draw to keep it that way.
  Shape text no longer depends on the prefix either: the `cp`/`pp` formatting
  runs that bracket it are located by walking the `Text` element's children
  rather than by matching `ns0:` in serialised text.
- Copying a shape remaps every `Sheet.N!` and `SheetN!` reference in a formula,
  not only those a formula begins with. The connector engine writes
  `_XFTRIGGER(Sheet5!EventXFMod)` and `PAR(PNT(Sheet5!Connections.X1,...))` —
  no dot, and nested inside a function call — so a copied connector kept
  pointing at the source shapes and Visio dropped the glue. The walk also
  reaches the copied shape's own cells and cells nested inside `Section`s,
  which a copied group previously lost.
- Archive preflight derives the central directory's start from the end-of-
  central-directory record and detects ZIP64 by its locator, rather than
  trusting the declared values. A falsified declared count no longer stops the
  directory scan early, and a directory declaring zero entries is still scanned.
- `Page.delete_shape()` identifies the shape by element rather than by ID.
  Visio shape IDs are page-scoped and collide, so handing a page a shape
  belonging to a different page satisfied the guard and then deleted whichever
  shape on *this* page happened to share the number. It now raises `ValueError`,
  and says so when an ID collision is what made the call look plausible.
- `Shape.remove()` is deprecated and now delegates to `Page.delete_shape()`, the
  single deletion path. It previously detached the element and nothing else,
  leaving orphan connectors and dangling `Connect` records that Visio repairs on
  open, and it raised `ValueError` outright for a shape inside a group, whose
  XML is held by the group's `Shapes` container rather than by the group element.
  Deleting a shape through either API now also removes `Connect` records that
  name it as the target, not only those leading from it, and deleting a group
  removes the records naming its children — they disappear with the group, so a
  record pointing at one dangled. Deleting a shape that is not on the page now
  raises `ValueError` instead of silently doing nothing, and a connector that
  inherits `BeginX` from its master is recognised as a connector rather than
  surviving as a detached line. `Page.remove_connect_records()` takes a
  `match="from" | "either"` argument for those two cases.
- Reading Shape Data no longer changes the document. `DataProperty.value`'s
  getter used to clear a `No Formula` formula and stamp a `STR` unit while
  reading, so merely inspecting a shape's properties altered the bytes the
  package saved. The tidy-up now happens on write, where it belongs, and the
  setter creates the `Value` cell when the row has none instead of silently
  doing nothing (upstream dave-howard/vsdx#79).
- `Shape.data_properties` no longer serves a stale cache after a `Property` row
  is added, removed or replaced; the cache is keyed on the rows themselves. It
  also copies the master's dictionary rather than merging into it in place.
  Inherited properties are still resolved once per shape, so a change made to a
  master *after* an instance's properties have been read is not picked up until
  that instance's own rows change.
- Connector record removal normalises integer IDs before matching XML attributes,
  preserving the existing public-call behaviour.
- Shape and connector coordinate setters reject `None` instead of writing
  invalid `V="None"` ShapeSheet values.
- `save_vsdx()` now writes through a same-directory temporary archive and
  atomically replaces the target; failed in-place writes retain the original.
- Repeated in-place or named saves preserve untouched ZIP members and keep
  archive member paths relative.
- Combined routes such as `point|curved` retain connection-point glue while
  applying the requested line style.
- `apply_text_context()` again coerces non-string values before replacement.
- The legacy debug-handler bridge imports and runs on Python 3.10.
- `Shape.copy()` retains a valid Page or Shape parent rather than assigning an
  internal shape list as the parent.
- XML master-part types now match the package representation used at runtime.
- Missing `IX` values and list/dictionary confusion in geometry handling no
  longer flow into unguarded operations.
- Page-template matching handles absent names and non-matching Jinja markers.
- Connector re-anchoring handles missing endpoint IDs explicitly and avoids
  parameter shadowing.
- Media documents can be closed and opened again through one lazy access path.
- Page relationship parts use OPC separators on every operating system and are
  copied into the in-memory package when a page is copied.
- Bundled media paths no longer depend on the process working directory.
- Closing an in-memory document no longer deletes an unrelated same-stem
  directory beside the source file.
- Saving rejects an empty package instead of writing a corrupt archive and
  recognises an uppercase `.VSDX` suffix without appending another extension.

### Changed

- Tests write their output to pytest's `tmp_path` instead of `tests/out`, so a
  run no longer leaves 120 files in the checkout. `/tests/out/` is gone from
  `.gitignore`; delete any `tests/out` an earlier run left behind. A
  session-scoped fixture snapshots `git status --porcelain --untracked-files=all`
  at session start and fails the run if new entries appear afterwards, naming
  them. Diffing against the snapshot rather than demanding a clean tree keeps
  the check usable in a checkout that already has unrelated edits. Paths git
  ignores stay invisible to it, and it is skipped where git cannot report.
- The bundled media and palette documents are now parsed once per `VisioFile`
  rather than once per `create_shape` and `connect_shapes` call. A loop building
  N shapes and N connectors re-opened and re-parsed `media.vsdx` and
  `palette_extended.vsdx` 2N times; it now opens each at most once. The shared
  `Media` is owned by the document and released by `close_vsdx()`, which stays
  safe to call more than once, and a create or connect call after a close builds
  a fresh one instead of reusing a closed instance. `Media` remains public and
  independently constructible.
- `save_vsdx` now keeps the saved extension in step with the package kind. The
  kind comes from the content type of `visio/document.xml`, not the filename, so
  saving a macro-enabled package to a `.vsdx` destination — or a plain drawing to
  a `.vsdm` one — raises `ValueError` instead of writing a package whose
  extension and `[Content_Types].xml` disagree, which Visio reports as corrupt.
  The same check applies to an in-place `save_vsdx()` on a file that was renamed
  outside the library; it refuses rather than renaming the caller's path. A
  destination carrying neither Visio extension still gets the matching one
  appended, which for a macro-enabled package is now `.vsdm` rather than `.vsdx`.
  Callers relying on the old silent `.vsdx` suffix for `.vsdm` documents will see
  the new exception. The new `VisioFile.is_macro_enabled` property exposes the
  same determination.
- The documentation toolchain moved from the published `docs` extra to a PEP 735
  `docs` dependency group carrying its own `requires-python` floor, so Sphinx can
  track releases that need a newer interpreter than `vsdxkit` itself. Sphinx is
  now pinned to 9.1.0 and the docs build runs on Python 3.12. Anyone installing
  `vsdxkit[docs]` should install the `docs` group instead.
- The lint job checks and formats the whole `tests` tree rather than two
  selected test modules; the remaining test files have been brought into
  compliance (semantic fixes: `raise AssertionError` instead of `assert
  False`, `zip(..., strict=True)`, `enumerate()` accumulation, exception
  chaining).
- zizmor is pinned to the committed uv lock (`uv run zizmor`) instead of
  resolving ad hoc via `uvx` at run time.
- Package keywords no longer carry inherited upstream terms.
- CONTRIBUTING.md and SECURITY.md now describe this fork (uv workflow,
  gate list, private vulnerability reporting on this repository) rather than
  inheriting the upstream project's text.
- CI now uses a committed uv lock for normal test, lint and build jobs. The
  minimum-dependency job regenerates that lock with
  `--resolution lowest-direct` and runs the full test suite on the oldest and
  newest supported Python versions.
- Test and development tooling now use uv dependency groups instead of a
  published `dev` extra.
- The pyrefly preset is now `strict` rather than `basic`.
- Runtime dependency floors now match the supported API and security baseline:
  `Jinja2>=3.1.6`, `deprecation>=2.1.0`, and `typing-extensions>=4.4.0` on
  Python 3.10–3.11. Python 3.12 and later use `typing.override` directly.
- `insert_shape()` now validates that `page_path` identifies the supplied
  `Page` instead of silently allocating IDs against whichever page was visited
  last.
- GitHub's default branch is now `main`; CI and documentation references follow
  the renamed branch.
- `VisioFileDiff` reads archive members in-memory: it no longer extracts
  beside the source files (which could delete a user's same-stem directory)
  and undecodable members compare by SHA-256 digest, so two different binary
  members are reported as changed instead of collapsing into one placeholder.
- Documentation now names the distribution `vsdxkit`, retains `import vsdx`,
  and requires Python 3.10 or later.

## 0.6.3

- Renamed the distribution to `vsdxkit` while preserving the `vsdx` import.
- Replaced legacy packaging with `pyproject.toml`.
- Added ruff, pyrefly and a Python 3.10–3.14 Linux/Windows CI matrix.
- Added connector creation, master import, connector re-anchoring, shape
  creation from the bundled palette and CFF swimlane operations.
- Split master import, templating and XML persistence out of `vsdxfile.py`.
- Replaced package `print()` diagnostics with standard-library logging.
