Migrating to 1.0
================

1.0 removes the names and behaviour listed here, counted from 0.8.0, the last
0.x release. Each entry gives the 0.x call and what replaces it.
``tools/check_migration_guide.py`` holds the guide to 0.8.0's whole public
surface: a name 1.0 no longer has must be named here.

The import package is ``vsdxkit``
---------------------------------

0.8.0 installed as ``vsdxkit`` but imported as ``vsdx``, the name another
distribution on PyPI also uses. Whichever of the two was installed last
owned ``import vsdx``. The package now imports as ``vsdxkit``, and there is
no ``vsdx`` alias, because an alias would bring the collision back.

``import vsdx``, ``from vsdx.pages import Page``
   ``import vsdxkit``, ``from vsdxkit.pages import Page``.

The package root re-exports nothing. Import each name from the module that
defines it:

``from vsdx import Page, PagePosition``
   ``from vsdxkit.pages import Page``. ``vsdx.pages.PagePosition`` is gone; see "Pages
   change through the collection" below.

``from vsdx import Shape, Cell, DataProperty``
   ``from vsdxkit.shapes import Shape, Cell, DataProperty``

``from vsdx import Geometry, GeometryRow, GeometryCell``
   ``from vsdxkit.geometry import Geometry, GeometryRow, GeometryCell``

``from vsdx import PackageLimits``
   ``from vsdxkit.package import PackageLimits``

``from vsdx import PackageLimitError``
   ``from vsdxkit.errors import PackageLimitError``, with every other error
   the library raises.

``from vsdx import calc_value``
   Internal in 1.0; no public replacement. See "Internal modules are
   private" below.

``from vsdx import get_logger``
   ``logging.getLogger("vsdxkit")``, as shown under
   ``VisioFile(path, debug=True)`` below.

``from vsdx import attach_debug_stream_handler``, ``vsdx.logging_support.attach_debug_stream_handler()``
   Gone. Configure logging for the ``vsdxkit`` logger instead, as shown under
   ``VisioFile(path, debug=True)`` below.

``from vsdx import pretty_print_element``
   ``from vsdxkit.xmlio import pretty_print_element``

``from vsdx import namespace``, and the other namespace constants
   ``from vsdxkit import namespace``: the root keeps the XML namespace
   constants and ``__version__``, and nothing else.

``from vsdx import VisioFile``
   ``from vsdxkit.document import Document``, below.

``from vsdx import VisioFileNotOpen``
   Gone, with the close state, below.

``from vsdx import Media``
   Gone. A page creates its shapes from a ``ShapeKind``, below.

``from vsdx import Connect``
   Gone. A 1-D shape is a ``Connector``, below.

``from vsdx import Container``
   ``from vsdxkit.swimlanes import SwimlaneDiagram``, below.

``Document`` replaces ``VisioFile``
-----------------------------------

The class is :class:`vsdxkit.document.Document`, in the module
``vsdxkit.document``. ``vsdxkit.vsdxfile`` is gone.

``from vsdxkit.vsdxfile import VisioFile``
   ``from vsdxkit.document import Document``

``VisioFile(path)``, ``VisioFile(path, limits=..., limits_path=...)``
   ``Document.open(path)``, with the same keyword arguments. ``path`` may be
   a ``str`` or a :class:`pathlib.Path`.

``VisioFile(path, debug=True)``
   Configure logging instead. The library logs under ``vsdxkit`` and never
   configures a handler itself:

   .. code-block:: python

      import logging

      logging.basicConfig()
      logging.getLogger("vsdxkit").setLevel(logging.DEBUG)

``VisioFile.save_vsdx(new_filename=None)``
   ``Document.save(target=None)``, which returns the absolute
   :class:`pathlib.Path` it wrote. ``target`` may be a ``str`` or a ``Path``.

``VisioFile.jinja_render_vsdx(context)``
   ``Document.render(context)``.

A ``{% showif %}`` in a page name
   Judged as ``{% if %}`` judges it, so a page is kept exactly when a shape
   behind the same ``showif`` is. 0.8 rendered the expression to a string
   and hid the page only for ``False``, ``0``, an empty string and the
   empty ``()``, ``[]`` and ``{}``. It kept a page for ``None``, ``0.0`` or
   an empty ``set()``, and hid one for the strings ``"0"`` and ``"False"``,
   which are true. A name with two ``showif`` statements is kept only when
   both are true, where 0.8 read the last one.

A page name holding ``{{ ... }}``
   Rendered with the context, as shape text is: a page named
   ``{{ title }}`` is named ``Quarterly`` after
   ``document.render({"title": "Quarterly"})``. 0.8 left the name as it was.
   A ``showif`` anywhere in the name is taken out of it before it is
   rendered, where 0.8 took one out only when it opened the name. Nothing
   checks that the names rendered are unique: give each page a name the
   others do not render to, because ``document.pages.by_name`` refuses a
   name two pages share. A name meant to keep a literal ``{{`` or ``{%``
   now needs escaping, as in shape text: ``{{ '{{' }}``. A broken
   template in a name raises ``jinja2.TemplateSyntaxError``.

``vsdx.templating.JinjaTemplatingMixin``
   Gone. ``Document`` has no base class. ``Document.render(context)`` calls
   ``vsdxkit.templating.render_document(document, context)``, which takes a
   :class:`~vsdxkit.templating.RenderTarget`. The context may be any mapping,
   not only a ``dict``. The mixin's
   ``JinjaTemplatingMixin.increment_sub_shape_ids`` was a placeholder for the
   document's own method, which is gone as well; see "The page allocates
   shape IDs" below.

``vis.jinja_render_shape``, ``vis.jinja_set_selfs``, ``vis.unescape_jinja_statements``, ``vis.jinja_create_for_loop_if``, ``vis.jinja_page_showif``
   Gone. They were the steps of one render, not something to call on their
   own. Render the whole document with ``Document.render(context)``.

``JinjaTemplatingMixin.remove_page_by_index``
   Gone with ``vis.remove_page_by_index``; see "Pages change through the
   collection" below.

``VisioFile.open_vsdx_file()``
   ``Document.open(path)`` opens a fresh document from the file.

``VisioFile.debug``, ``VisioFile.limits``
   Gone. The limits a document was opened with are applied at open and not
   kept.

A document has no close state
-----------------------------

A document reads its whole package into memory when it opens and holds no
file, so there is nothing to close. The context manager, ``close_vsdx()`` and
the closed-document error are gone, and a document can be edited for as long
as you hold it.

``with VisioFile(path) as vis:``
   Assign instead. ``with`` now raises ``TypeError`` (``AttributeError`` on
   Python 3.10).

   .. code-block:: python

      # 0.x
      with VisioFile("diagram.vsdx") as vis:
          vis.pages[0].name = "Current state"
          vis.save_vsdx()

      # 1.0
      document = Document.open("diagram.vsdx")
      document.pages[0].name = "Current state"
      document.save()

``VisioFile.close_vsdx()``
   Delete the call. Nothing needs releasing.

``VisioFile.file_open``
   Delete the check. A document is always open.

``vsdxkit.errors.VisioFileNotOpen``, ``vsdx.vsdxfile.VisioFileNotOpen``
   Delete the ``except`` clause. Nothing raises it. A write through a shape
   that has been deleted from its page still raises
   :class:`vsdxkit.errors.InvalidOperationError`.

Errors are one hierarchy
------------------------

An error about the package, the document or an operation on it derives
from :class:`vsdxkit.errors.VsdxError`, and every such class is defined in
``vsdxkit.errors``. A class that replaced a ``ValueError`` is still a
``ValueError``, so ``except ValueError:`` keeps working.

The guarantee covers what the library checks. Opening a document validates
the parts and attributes it reads on the way in, but a package that is
well-formed and breaks the schema somewhere the library only reaches later,
such as a shape element missing an attribute it reads, can still raise a
plain ``KeyError`` or ``AttributeError``. ``except VsdxError:`` is not
exhaustive for such a package.

An argument of the wrong type or out of range usually raises a plain
``TypeError`` or ``ValueError``, not a ``VsdxError``, and ``except VsdxError:``
does not catch it. Examples are ``Document.open("file.txt")``, a page width
that is not positive, and a ``ConnectorOptions`` ``glue`` or ``routing`` that
is not a ``Glue`` or ``Routing``. A connection point that is not a
non-negative ``int`` (``ConnectorOptions(from_point=-1)``) is the exception:
it raises :class:`vsdxkit.errors.InvalidOperationError`, which is both.

``except zipfile.BadZipFile:``, ``except RuntimeError:``, ``except KeyError:`` around an open
   ``except MalformedPackageError:``. Opening a package that is not a zip,
   is truncated, encrypted, compressed with an unsupported method, or whose
   parts name an undecodable encoding or lack a required attribute raises
   :class:`vsdxkit.errors.MalformedPackageError`. The original exception is
   its ``__cause__``. An ``OSError`` with an ``errno``, and ``MemoryError``,
   still propagate unchanged.

``except ET.ParseError:``
   Still works. A part that is not well-formed XML raises
   :class:`vsdxkit.errors.PartParseError`, which is an ``ET.ParseError``
   carrying ``position`` and ``code``.

``vsdx.vsdxfile.PackageLimitError``
   ``vsdxkit.errors.PackageLimitError``, a
   :class:`vsdxkit.errors.PackageError` and an ``OSError``.

A save writes only what changed
-------------------------------

A save writes each part the document did not change byte for byte as it
arrived. 0.x re-serialised every XML part it had parsed, so tooling that
relied on the library normalising every part's declaration, prefixes or
quoting now sees the producer's own spelling on the parts left alone.

Parts are named by part name
----------------------------

A document holds its package in memory, part by part, under each part's
OPC name, and the file-system view of 0.x is gone.

``VisioFile.zip_file_contents``, ``VisioFile.directory``
   Gone. Work through the object model; to read a part's raw bytes, open
   the saved file with :mod:`zipfile`.

``vsdx.xmlio.file_to_xml``, ``xmlio.xml_to_file``
   Gone with the file-system view. ``vsdxkit.xmlio.parse_part(bytes)`` and
   ``serialise_part(tree)`` parse and serialise a part's bytes.

``xmlio.require_xml_tree``, ``xmlio.require_root``
   Gone. They read a named part from the zip, refused one that was absent
   with the description given, and ``require_root`` returned the root. The
   parts are already parsed: take the tree from the object model, such as
   ``page.xml``, and compose the two checks 1.0 keeps.
   ``vsdxkit.xmlio.require_tree(tree, description)`` refuses ``None`` with
   :class:`vsdxkit.errors.MissingPartError`, and
   ``require_element(tree.getroot(), description)`` gives the root.

``vsdx.shapes.to_float``
   ``vsdxkit.xmlio.to_float``.

``vsdx.vsdxfile.DRAWING_CONTENT_TYPE``, ``vsdxfile.MACRO_ENABLED_CONTENT_TYPE``
   ``vsdxkit.document.DRAWING_CONTENT_TYPE`` and
   ``vsdxkit.document.MACRO_ENABLED_CONTENT_TYPE``.

``vsdx.vsdxfile.PackageLimits``
   ``vsdxkit.package.PackageLimits``.

``vsdx.relationships.CONTENT_TYPES_NS``, ``relationships.RELATIONSHIPS_NS``
   ``vsdxkit.cont_types_namespace`` and ``vsdxkit.document_rels_namespace``,
   which they were copies of.

``vsdx.document_part.DocumentPart``
   Gone. It was not a package part: it was the base that gave ``Shape``,
   ``Cell``, ``DataProperty`` and the geometry and container classes their
   closed-document guard. A document has no close state now, so a subclass
   that implemented ``_document`` and called ``_require_open`` drops the base
   and the guard, and has nothing to replace them with.

``vsdx.masters.MastersImportMixin``
   Gone as a base class. The document's masters are
   ``document.master_pages`` and ``document.master_index``, which are now
   read-only. Each read builds a new list or dict: one kept from before a
   master is imported does not show it, and changing the list or dict changes
   nothing in the document. Read the property again after a master changes.

``vis.load_master_pages()``
   Unchanged, as ``document.load_master_pages()``. It rebuilds
   ``document.master_pages`` and ``document.master_index`` by re-reading
   every master from the package. Copying a shape whose master this document
   lacks already adds that master to both, so this is for confirming the
   catalog still matches the package, not for making an import visible.

Pages and shapes are collections
--------------------------------

``vis.pages``
   A read-only :class:`vsdxkit.pages.PageCollection`, not a ``list``. It
   supports ``len``, iteration and indexing, ``by_name`` and
   ``require_name``. Change pages with ``pages.create``, ``pages.copy`` and
   ``pages.delete``.

``page.shapes``
   The recursive :class:`vsdxkit.shapes.ShapeCollection` of every shape on
   the page, connectors included. It used to be a list holding the page's
   ``<Shapes>`` element as a shape. ``page.children`` holds the top-level
   shapes, and ``shape.children`` and ``shape.descendants`` a shape's own.

``shape.parent`` of a top-level shape
   Its :class:`vsdxkit.pages.Page`. It used to be the wrapper of the page's
   ``<Shapes>`` element.

``shape.append_shape(other)``
   Takes a group only. ``other.copy(page)`` places a copy of ``other`` at a
   page's top level, importing its master and the page relationships it
   needs.

A lookup by ID on a page where two shapes share the ID
   Raises :class:`vsdxkit.errors.PackageError`, because the page is not
   valid. It used to take the first match.

``page.child_shapes``, ``page.sub_shapes()``
   ``page.children``.

``page.all_shapes``
   ``page.shapes``.

``shape.child_shapes``, ``shape.sub_shapes()``
   ``shape.children``.

``shape.all_shapes``
   ``shape.descendants``.

A collection is not a list: it has ``len`` and iteration, but no indexing.
Where a list is needed, ``list(page.children)`` makes one.

``page.set_name(name)``, ``page.page_name``
   ``page.name``, which can be assigned.

``vis.get_sub_shapes(element, nth)``
   Gone. ``shape.children`` holds the shapes inside a group.

Pages change through the collection
-----------------------------------

``document.pages`` is the one place pages are looked up, created, copied and
deleted. The ``VisioFile`` methods that did the same are gone.

``vis.get_page(n)``
   ``document.pages[n]``, which raises ``IndexError`` where ``get_page`` returned
   ``None``.

``vis.get_page_by_name(name)``
   ``document.pages.by_name(name)``, or ``document.pages.require_name(name)``, which
   raises :class:`vsdxkit.errors.NotFoundError`.

``vis.get_page_names()``
   ``[page.name for page in document.pages]``.

``vis.add_page(name)``
   ``document.pages.create(name)``.

``vis.add_page_at(index, name)``
   ``document.pages.create(name, index=index)``. ``index`` runs from 0 to
   ``len(document.pages)``.

``vis.copy_page(page, index=..., name=...)``
   ``document.pages.copy(page, name=..., index=...)``. With no ``index`` the copy
   goes straight after ``page``. A page of another document is refused.

``vis.remove_page_by_index(index)``
   ``document.pages.delete(document.pages[index])``.

``vis.remove_page_by_name(name)``
   ``document.pages.delete(document.pages.require_name(name))``. A name no page has
   raises :class:`vsdxkit.errors.NotFoundError`, where 0.x did nothing.

``PagePosition.FIRST``, ``PagePosition.LAST``, ``PagePosition.END``, ``PagePosition.BEFORE``, ``PagePosition.AFTER``
   An index instead: ``index=0`` for the first page, ``len(document.pages)`` (or no
   index, for ``create``) for the end, ``document.pages.index(page)`` for before a
   page, and no index, for ``copy``, for after it.

Shapes delete themselves
------------------------

``page.delete_shape(shape)``, ``shape.remove()``
   ``shape.delete()``. It deletes the shape from its own page, with every
   connector glued to it and every ``Connect`` record naming it; a group takes
   its members with them. A shape can no longer be handed to the wrong page,
   so the ``NotFoundError`` for a shape from elsewhere is gone. Deleting a
   shape twice raises :class:`vsdxkit.errors.InvalidOperationError`.

``Shape.remove`` warned with ``DeprecationWarning`` in 0.8; ``shape.delete()``
does not warn.

The finders are gone
--------------------

The ``find_shape_*`` and ``find_shapes_*`` methods of ``Page`` and ``Shape``
are gone. A page's finders searched ``page.shapes``, and a shape's searched
``shape.descendants``. They differed from the collections in two ways:

- text was matched as a substring;
- a lookup of one shape returned the first match without saying there
  were several.

The collections match whole text and refuse more than one match; see
:doc:`find_shape`. In the replacements, ``scope`` is ``page.shapes`` for a
page's finder and ``shape.descendants`` for a shape's.

.. list-table::
   :header-rows: 1

   * - 0.x
     - 1.0
   * - ``page.find_shape_by_id(id)``, ``page.find_shapes_by_id(id)``,
       ``shape.find_shape_by_id(id)``, ``shape.find_shapes_by_id(id)``
     - ``scope.by_id(id)``, or ``scope.require_id(id)``. IDs are unique on a
       page, so the plural forms had at most one shape to return; a page that
       holds two shapes with one ID raises
       :class:`vsdxkit.errors.PackageError`.
   * - ``page.find_shape_by_text(text)``, ``shape.find_shape_by_text(text)``
     - ``scope.by_text(text)`` for the whole text;
       ``next((s for s in scope if text in s.text), None)`` for a substring
   * - ``page.find_shapes_by_text(text)``, ``shape.find_shapes_by_text(text)``
     - ``scope.matching_text(text)`` for the whole text;
       ``[s for s in scope if text in s.text]`` for a substring
   * - ``page.find_shape_by_property_label(label)``,
       ``shape.find_shape_by_property_label(label)``
     - ``scope.by_property(label)``
   * - ``page.find_shape_by_property_label_value(label, value)``,
       ``shape.find_shape_by_property_label_value(label, value)``
     - ``scope.by_property(label, value)``
   * - ``page.find_shapes_by_property_label(label)``,
       ``shape.find_shapes_by_property_label(label)``
     - ``scope.matching_property(label)``
   * - ``page.find_shapes_by_property_label_value(label, value)``,
       ``shape.find_shapes_by_property_label_value(label, value)``
     - ``scope.matching_property(label, value)``
   * - ``page.find_shapes_by_regex(regex)``, ``shape.find_shapes_by_regex(regex)``
     - ``[s for s in scope if re.search(regex, s.text)]``, after ``import re``
   * - ``page.find_shape_by_attr(attr, value)``, ``shape.find_shape_by_attr(attr, value)``
     - ``next((s for s in scope if str(s.xml.get(attr)) == value), None)``.
       The ``str`` keeps 0.x's match of ``"None"`` against a shape without the
       attribute; compare ``s.xml.get(attr) is None`` to find those directly.
   * - ``shape.find_shapes_by_master(page_id, shape_id)``
     - ``[s for s in scope if (s.master_page_ID, s.master_shape_ID) == (page_id, shape_id)]``
   * - ``page.find_shapes_with_same_master(shape)``
     - ``[s for s in page.shapes if (s.master_page_ID, s.master_shape_ID) == (shape.master_page_ID, shape.master_shape_ID)]``

A shape is its element
----------------------

``shape_a == shape_b``, ``hash(shape)``
   Two shapes are equal when they wrap the same XML element, whatever their
   class, and a shape keeps its place in a set or dict through a rename, a
   renumber or a save. The hash used to be the ID, page name and file name.
   Shapes from two documents are never equal, even two opens of one file.

Reading or writing a deleted shape
   Raises :class:`vsdxkit.errors.InvalidOperationError`, as does a shape on
   a deleted page. ``shape.is_attached`` says whether a shape is still in
   its document. ``ID``, ``xml``, ``page``, ``parent``, ``repr`` and
   ``hash`` keep working: ``page`` and ``parent`` are where the shape was.

``deleted_shape.copy()``, ``shape.copy(removed_page)``
   Both raise :class:`vsdxkit.errors.InvalidOperationError` and write
   nothing. A copy reads the whole shape, so a shape that has been deleted,
   or that is on a page removed from its document, is refused as any other
   read of it is; 0.8 copied it back onto a page. A copy onto a page removed
   from its document is refused too, where 0.8 returned a shape that was in
   no document. ``page.create_shape(...)`` and ``page.connect(...)`` on a
   removed page are refused the same way.

``shape.cells``
   A read-only property that returns a new ``dict`` on each read, from the
   XML. Assigning into the dict changes nothing; set a cell with
   ``shape.set_cell_value`` or ``shape.set_cell_formula``.

``shape.data_properties``
   Also a new ``dict`` on each read; 0.8 returned the same one while the
   property rows were unchanged. A key added to the dict, or a dict kept
   from an earlier read, is not the shape's. Change a property through its
   :class:`vsdxkit.shapes.DataProperty`:
   ``shape.data_properties["Status"].value = "Done"``.

``shape.page = page``, ``shape.parent = group``, ``page.vis = document``
   Read-only. The XML does not follow a repointed reference, so assigning
   one only ever made the wrapper lie. Move a shape into a group with
   ``group.append_shape(shape)``.

``shape.page.swimlanes``, ``shape.page.vis``, ``page.vis``
   Typed code sees ``shape.page`` as :class:`vsdxkit.shapes.PageView`. The
   same type is the page half of ``shape.parent`` (``PageView | Shape``) and
   of ``shape.master_page`` (``PageView | None``). ``PageView`` lists the
   page's API apart from ``swimlanes``, ``require_swimlanes`` and ``vis``,
   whose types are declared above ``shapes``. It has the page's setters, so
   ``shape.page.name = "Summary"`` type-checks. At runtime it is the same
   ``Page``. For those three, use the ``Page`` you hold, such as
   ``document.pages[0]``.

   The same holds one level up. Typed code sees ``page.vis`` as
   :class:`vsdxkit.pages.DocumentView`, which lists the document's
   ``pages``, ``save`` and ``render``. At runtime it is the same
   ``Document``. For the rest of the document's API, use the ``Document``
   you opened.

A page creates its own shapes
-----------------------------

Shapes are created by the page they go on, from a
:class:`vsdxkit.shape_kind.ShapeKind` or from a shape already in the document.
Palette-name strings are gone.

``vis.create_shape(page, "PALETTE_PROCESS", x, y, w, h, text="...")``
   ``page.create_shape(ShapeKind.PROCESS, x=x, y=y, width=w, height=h, text="...")``,
   with ``from vsdxkit.shape_kind import ShapeKind``. The position is
   keyword-only and ``w``/``h`` are now ``width``/``height``. ``PALETTE_X``
   becomes ``ShapeKind.X`` for ``PROCESS``, ``DECISION``, ``START_END``,
   ``PARALLELOGRAM`` and ``DATABASE``; ``RECTANGLE``, ``CIRCLE`` and ``LINE``
   are new. A string raises ``TypeError``.

A copy of an existing shape
   ``page.create_shape(shape, x=x, y=y)`` places a copy of ``shape``, with its
   text, on ``page``. ``shape`` must belong to the same document.

``vsdx.media.Media``
   Gone. The bundled shapes are loaded once per process and only copies
   leave the library:

   - ``Media.rectangle``: ``page.create_shape(ShapeKind.RECTANGLE, ...)``;
   - ``Media.circle``: ``page.create_shape(ShapeKind.CIRCLE, ...)``;
   - ``Media.straight_connector``: ``page.connect(a, b,
     routing=Routing.STRAIGHT)`` for a connector glued at both ends, or
     ``page.create_shape(ShapeKind.LINE, x=..., y=..., width=...)`` for a
     free-standing straight line;
   - ``Media.curved_connector``: ``page.connect(a, b,
     routing=Routing.CURVED)`` for a connector glued at both ends. For a
     free-standing one, place a copy of such a connector:
     ``page.create_shape(connector, x=..., y=..., width=...)`` floats both of
     the copy's ends and keeps its curved routing;
   - ``Media.rectangle_text``, ``Media.circle_text``,
     ``Media.straight_connector_text``, ``Media.curved_connector_text``: the
     strings ``"RECTANGLE"``, ``"CIRCLE"``, ``"STRAIGHT_CONNECTOR"`` and
     ``"CURVED_CONNECTOR"`` that marked each shape in the bundled donor file.
     They are gone with no replacement, and a created shape does not carry
     them: ``create_shape`` gives it the text you pass, or none;
   - ``Media.palette``, ``Media.media``, ``Media.rels_xml``: the donor
     documents themselves, no longer handed out;
   - ``Media.close()``: nothing to close.

``shape.copy()`` with no page
   The copy's parent is the page it lands on, not the group the source is
   in.

``ConnectorOptions(routing=None)``
   ``ConnectorOptions(routing=Routing.DEFAULT)``, which is also the default:
   the connector keeps the routing Visio gives it. ``None`` raises
   ``TypeError``.

A connector is a shape
----------------------

Every 1-D shape is a :class:`vsdxkit.shapes.Connector`, wherever it is reached
from: a walk of ``page.shapes``, ``page.connectors`` or a copy. Route strings
are gone; glue and routing are :class:`vsdxkit.glue.Glue` and
:class:`vsdxkit.glue.Routing`.

``page.connect_shapes(a, b, route="point|curved", from_cp=1, to_cp=2)``
   ``page.connect(a, b, glue=Glue.POINT, routing=Routing.CURVED, from_point=1, to_point=2)``.
   ``"dynamic"`` is the default glue, and ``"straight"``, ``"rightangle"``
   and ``"curved"`` are ``Routing.STRAIGHT``, ``Routing.RIGHT_ANGLE`` and
   ``Routing.CURVED``.

``page.connect_shapes(a, b, options=ConnectorOptions(...))``, ``Connect.create(page, a, b, ...)``
   ``page.connect(a, b, ...)`` with the options' fields as keywords.

``Connect.retarget(page, connector_shape, from_shape=a, to_shape=b, route=...)``
   ``connector.retarget(source=a, target=b, options=...)``, as for
   ``reanchor_connector`` below. The connector is the shape itself, so the
   page is not passed, and nothing is returned: keep the connector you
   called it on.

``page.reanchor_connector(connector, from_shape=a, to_shape=b, route=...)``
   ``connector.retarget(source=a, target=b, options=ConnectorOptions(...))``.
   An end not named stays where it is, so ``None`` is never needed. Without
   ``options`` the connector keeps its glue, its routing and each end's
   connection point; 0.x reset them to dynamic glue. A kept point the new
   shape does not have raises :class:`vsdxkit.errors.InvalidOperationError`
   instead of falling back to dynamic glue. A connector with a floating end
   can now be retargeted. An endpoint on another page, and the connector
   itself as an endpoint, are refused before anything is written.

   ``retarget`` returns ``None``; 0.x returned the connector. Replace
   ``connector = page.reanchor_connector(connector, ...)`` with the call
   alone.

``page.reanchor_connector(connector, route="curved")``, with neither shape
   Name an end where it already is, and give the glue and connection points
   with the routing, because ``options`` replaces them all:
   ``connector.retarget(source=connector.source, options=ConnectorOptions(glue=Glue.DYNAMIC, routing=Routing.CURVED))``.
   Use ``target=connector.target`` when the begin end floats. A call that
   names neither end raises :class:`vsdxkit.errors.InvalidOperationError`.

``page.get_connectors_between(shape_a_id=..., shape_b_id=...)``
   ``set(a.connectors) & set(b.connectors)``.

``page.get_connectors_between(shape_a_text=..., shape_b_text=...)``
   The text form took the first shape whose text contained each string, and
   raised ``ValueError`` when there was none. A comprehension keeps both:
   ``a = next((s for s in page.shapes if shape_a_text in s.text), None)``,
   the same for ``b``, ``raise ValueError(...)`` if either is ``None``, then
   ``set(a.connectors) & set(b.connectors)``. Without the default, ``next``
   raises ``StopIteration`` instead.
   ``page.shapes.require_text`` and ``matching_text`` compare the whole text
   instead.

``shape.connected_shapes``
   It now returns the shapes at the other end of each connector glued to
   ``shape``, each once, as a tuple. It used to return the connector shapes
   themselves; those are :attr:`vsdxkit.shapes.Shape.connectors`.

``ConnectorOptions.from_route(route)``
   Gone with the route strings.

The ``<Connect>`` records are internal
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The records that glue a connector's ends are how the package stores the graph,
and the library keeps them in step with every connect, retarget, copy and
delete. The graph is read through connectors and shapes instead.

``connectors.Connect``, and ``page.connects`` or ``page.get_connects()``
   The records are no longer objects. ``page.connectors`` lists the page's
   connectors; ``connector.source`` and ``connector.target`` are the shapes
   its ends are glued to, or ``None`` for a floating end.

``shape.connects``
   ``shape.connectors`` for the connectors glued to ``shape``, and
   ``shape.connected_shapes`` for what is at their other ends. On a
   connector, ``shape.connects`` returned the connector's own records; use
   ``connector.source`` and ``connector.target`` there, because
   ``connector.connectors`` lists the connectors glued to the connector,
   which is normally none.

``Connect.connector_shape``, ``Connect.connector_shape_id``, ``Connect.from_id``
   The connector itself, and its ``ID``.

``Connect.shape``, ``Connect.shape_id``, ``Connect.to_id``
   ``connector.source`` or ``connector.target``, and its ``ID``.

``Connect.from_rel``, ``Connect.to_rel``
   ``connector.source`` and ``connector.target`` are the shapes each end is
   glued to. The record's exact ``FromCell`` and ``ToCell``, such as
   ``BeginX`` and ``PinX`` for dynamic glue or a ``Connections.X<n>`` row for
   glue to a point, are only on the raw ``<Connect>`` element, found as under
   ``Connect.xml`` below. For dynamic glue the ``BeginX`` and ``EndX``
   formulas are ``_WALKGLUE`` expressions that name no shape.

``Connect.page``
   ``connector.page``.

``Connect.xml``
   The ``<Connect>`` element itself, with ``FromSheet``, ``ToSheet``,
   ``FromPart`` and ``ToPart``, is a child of the ``Connects`` element in
   ``page.xml``, for code that needs the raw record:
   ``[c for c in page.xml.getroot().iter(f"{ns}Connect") if c.get("FromSheet") == connector.ID]``,
   where ``ns`` is ``"{http://schemas.microsoft.com/office/visio/2012/main}"``.
   ``connector.xml`` is the connector's ``<Shape>`` element, not a record.

``page.add_connect(connect)``, ``page.remove_connect_records(ids)``
   ``page.connect(a, b)`` writes a connector with its records,
   ``connector.retarget(...)`` rewrites them, and ``shape.delete()`` removes
   those that name the shape. A record written by hand is not checked
   against the shapes it names.

A swimlane diagram replaces the container
-----------------------------------------

:class:`vsdxkit.swimlanes.SwimlaneDiagram` replaces ``vsdxkit.containers.Container``,
which is gone along with its module. Membership is still geometric.

``page.get_container()``
   ``page.swimlanes``, which is ``None`` on a page with no CFF container, or
   ``page.require_swimlanes()``, which raises
   :class:`vsdxkit.errors.NotFoundError`. A page with two CFF containers now
   raises :class:`vsdxkit.errors.InvalidOperationError` from both.

``page.add_swimlane(label)``, ``container.add_swimlane(label)``
   ``diagram.add_lane(label)``.

``page.add_shape_to_lane(shape, lane)``, ``container.add_shape_to_lane(shape, lane)``
   ``diagram.move_to_lane(shape, lane)``. A shape already in the lane is left
   where it is.

``container.lane_of(shape)``
   ``diagram.lane_for(shape)``. It raises
   :class:`vsdxkit.errors.InvalidOperationError` where lanes overlap.

``container.members(lane)``
   ``diagram.shapes_in(lane)``, a tuple.

``container.lanes``
   ``diagram.lanes``, a tuple.

``container.container_shape``
   ``diagram.container``.

``container.page``
   ``diagram.container.page``, or the page you asked for the diagram. A
   diagram whose container has been deleted raises
   :class:`vsdxkit.errors.InvalidOperationError` from every operation,
   ``diagram.container`` included, where 0.x kept ``container.page`` and
   answered ``None`` for ``container.container_shape``. Keep the page if code
   that runs after a deletion needs it; ``page.swimlanes`` then says whether
   the page still has a diagram.

``container.lane_band(lane)``, ``container.swimlane_list``, ``container.lane_heading(lane)``, ``Container.find(page)``
   Gone. A lane's band is its ``y`` plus or minus half its height, where a
   lane with no height, or a zero one, counts as
   ``vsdxkit.swimlanes.LANE_PITCH_INCHES`` high:
   ``half = (lane.height or LANE_PITCH_INCHES) / 2``. ``diagram.lane_for``
   and ``diagram.shapes_in`` use the same band.

``vsdxkit.containers.get_user_row``, ``containers.set_user_row_value``
   Gone. To label a lane, use ``diagram.set_lane_label(lane, label)``, which
   writes the lane's ``visHeadingText`` row and its heading together. For any
   other User-section row, or a shape that is not a lane, read and write the
   row in the shape's XML:

   .. code-block:: python

      from vsdxkit import namespace

      rows = (
          row
          for section in shape.xml.findall(f"{namespace}Section")
          if section.get("N") == "User"
          for row in section.findall(f"{namespace}Row")
          if row.get("N") == name
      )
      row = next(rows, None)
      value = None if row is None else row.find(f"{namespace}Cell[@N='Value']")
      updated = value is not None
      if updated:
          value.set("V", new_value)

   The row name is compared in Python rather than written into the path, so
   a name holding a quote, such as ``Owner's``, still matches. ``updated``
   is what ``set_user_row_value`` returned: whether a ``Value`` cell was
   written. Compare with ``None`` rather than testing ``value`` itself,
   because an element with no children is false.

   As in 0.x, a row that is absent is not created.

``vsdx.containers.LANE_PITCH_INCHES``, ``containers.ROW_HEADING_TEXT``, ``containers.ROW_SWIMLANE_GUID``
   ``vsdxkit.swimlanes.LANE_PITCH_INCHES``, ``ROW_HEADING_TEXT`` and
   ``ROW_SWIMLANE_GUID``.

A shape on the edge two lanes share is now in the upper lane only. It used to
count as a member of both.

Members removed as unused
-------------------------

These had no caller in the library, repeated a 1.0 name, or did nothing.

``vis.get_shape_location(element)``, ``vis.set_shape_location(element, x, y)``, ``vis.get_shape_id(element)``
   Gone. Ask the shape: ``shape.x`` and ``shape.y`` read and write its
   position, and ``shape.ID`` is its ID.
   ``page.shapes.by_id(element.attrib["ID"])`` finds the shape for an
   element.

``vis.apply_text_context(element, context)``
   ``page.apply_text_context(context)``, which also substitutes into text a
   shape shows from its master.

``vis.pretty_print_element(xml)``
   ``vsdxkit.xmlio.pretty_print_element(xml)``.

``vis.document_rels()``
   Internal in 1.0; no public replacement. The document keeps its
   relationships in step itself.

``Cell.func``, ``GeometryCell.func``
   ``cell.formula``, which is the same value.

``shape.shape_value(name)``
   ``shape.xml.get(name)``, the attribute it read.

``shape.text_raw``
   ``shape.text``, which leaves out the formatting-run markup and the
   trailing newline ``text_raw`` also showed.

``shape.loc_x_f``, ``shape.loc_y_f``
   ``shape.cell_formula("LocPinX")`` and ``shape.cell_formula("LocPinY")``.

``shape.get_max_id()``
   Gone. The page allocates shape IDs itself. For the highest ID in a shape
   and the shapes inside it, use
   ``max((int(s.ID) for s in (shape, *shape.descendants) if s.ID), default=0)``.

``shapes.shape_type_names``
   Gone, with no replacement: nothing read it. ``isinstance(shape, Connector)``
   tells whether a shape is a connector.

``DataProperty.remove_attribute(name, attrib)``
   Gone, with no replacement. On a property the shape inherits it removed
   the attribute from the master's cell, which changed every shape that
   uses the master.

``page.master_base_id``
   Gone, with no replacement: nothing read it.

The page allocates shape IDs
----------------------------

A shape ID is written in three places: the shape's own element, the
``Sheet.N!`` references in other shapes' formulas, and the page's glue
records. The page allocates IDs and moves all three together, whenever a
shape is created, copied or repeated by a ``{% for %}`` loop, so there is
nothing left for a caller to renumber.

``shapes.parent_of(root, element)``, ``shapes.find_or_create_shapes_tag(parent)``
   ``vsdxkit.shape_tree.parent_of`` and
   ``vsdxkit.shape_tree.find_or_create_shapes_tag``, unchanged, beside the
   other element-level walks. For a shape, ``shape.parent`` is its page or
   group.

``vis.copy_shape(element, page)``, ``vis.insert_shape(element, shapes, page, page_path)``
   ``shape.copy(page)``: a copy of the shape at the page's top level, with
   IDs the page does not use, the master it instances and the page
   relationships it needs. ``group.append_shape(shape)`` moves a shape into
   a group.

``vis.renumber_shape_ids(...)``, ``vis.increment_shape_ids(...)``, ``vis.increment_sub_shape_ids(...)``, ``vis.set_new_id(...)``
   Internal in 1.0; no public replacement. The page renumbers what it needs
   to, as above.

``vis.update_ids(element, id_map)``
   ``vsdxkit.shape_tree.remap_sheet_references(element, id_map)`` rewrites
   the ``Sheet.N!`` and ``SheetN!`` references in every formula under
   ``element``, keeping each one's form. It returns ``None``, where
   ``update_ids`` returned the element.

Package internals are private
-----------------------------

The document keeps its package parts in step itself, and a page's
part-level bookkeeping is the document's, so 1.0 makes both private. The
part names are in :mod:`vsdxkit.partnames`. To read a part's bytes, save the
document and open the file with :mod:`zipfile`. If you need one of these,
open an issue asking for an API.

``vis.pages_xml``, ``vis.pages_xml_rels``, ``vis.content_types_xml``, ``vis.app_xml``, ``vis.document_xml``, ``vis.document_xml_rels``, ``vis.masters_xml``
   Internal in 1.0; no public replacement. Assigning a tree to one replaced
   the part without the relationships and content types that name it; the
   library's own writes keep those in step.

``vis.load_pages()``
   Internal in 1.0; no public replacement. The document reads its pages when
   it opens, and calling this again added every page a second time.

``vis.get_master_page_by_id(master_id)``
   Internal in 1.0. ``shape.master_page`` is the master a shape instances,
   and ``document.master_index[name]`` finds a master by name.

``page.filename``, ``page.rels_xml_filename``, ``page.rels_xml``
   Internal in 1.0; no public replacement. They were the page's part name,
   the name of its relationships part, and that part's tree.

``page.page_id``, ``page.rel_id``, ``page.master_unique_id``
   Internal in 1.0; no public replacement. A page is known by ``page.name``
   and by its place in ``document.pages``.

Two 0.x holdovers go
--------------------

``vis.filename = path``
   Read-only. ``document.filename`` is the path the document was opened
   from, and ``save()`` with no target writes back over it. Assigning it used
   to send the next plain save somewhere else; that is
   ``document.save(path)`` now, and the assignment raises ``AttributeError``.

``shape.geometry = geometry``
   Read-only. The assignment wrote nothing to the shape's XML, so the shape
   and its file disagreed. Change the geometry through the rows and cells
   of ``shape.geometry``.

The package differ is gone
--------------------------

``vsdxdiff.VisioFileDiff``, ``from vsdxkit.vsdxdiff import VisioFileDiff``
   Gone, with no replacement. It compared two packages member by member,
   under limits of its own rather than
   :class:`~vsdxkit.package.PackageLimits`, and only this project's tests
   used it; they keep a private copy. To compare two saved files, read both
   with :mod:`zipfile` and compare the members with :mod:`difflib`.

   Its members went with it: ``VisioFileDiff.MAX_MEMBER_BYTES``,
   ``VisioFileDiff.MAX_TOTAL_BYTES``, ``VisioFileDiff.added_members``,
   ``VisioFileDiff.break_all_xml_into_lines``,
   ``VisioFileDiff.break_xml_into_lines``, ``VisioFileDiff.common_members``,
   ``VisioFileDiff.compare_members``, ``VisioFileDiff.contents_a``,
   ``VisioFileDiff.contents_b``, ``VisioFileDiff.diffs``,
   ``VisioFileDiff.extract_file_data``, ``VisioFileDiff.filepath_a``,
   ``VisioFileDiff.filepath_b``, ``VisioFileDiff.get_file_diffs`` and
   ``VisioFileDiff.removed_members``.

Internal modules are private
----------------------------

Every name 1.0 exports is user API on purpose. The rest start with an
underscore, in their own name or their module's, and may change in any
release. The modules below hold only the library's plumbing, so each is
renamed with a leading underscore; nothing in them is supported.

``vsdx.formulae.calc_value``, ``formulae.func_map``, ``formulae.width_x_1``, ``formulae.width_x_0``, ``formulae.middle_x``, ``formulae.middle_y``, ``formulae.center_x``, ``formulae.center_y``, ``formulae.diag_width``, ``formulae.angle``, ``formulae.width``, ``formulae.height``
   Internal in 1.0; no public replacement. They compute the values
   ``shape.set_start_and_finish(...)`` writes beside a line's formulas,
   which it still does.

``vsdx.inheritance.InheritedRow``, ``InheritedRow.inherited``, ``InheritedRow.make_local``
   ``InheritedRow`` is internal in 1.0. Its two members are public on the
   rows a shape inherits from its master,
   :class:`vsdxkit.geometry.GeometryRow` and
   :class:`vsdxkit.shapes.DataProperty`: ``row.inherited`` says whether the
   row is still the master's, and ``row.make_local()`` gives the shape a
   row of its own.

``vsdx.logging_support.get_logger``
   ``logging.getLogger("vsdxkit")``. The library logs under ``vsdxkit`` and
   never configures a handler itself.
