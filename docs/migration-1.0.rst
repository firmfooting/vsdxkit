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
   ``from vsdxkit.formulae import calc_value``

``from vsdx import get_logger``
   ``from vsdxkit.logging_support import get_logger``

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
      vis = Document.open("diagram.vsdx")
      vis.pages[0].name = "Current state"
      vis.save()

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

``vis.pages_xml = None``, and the same for ``app_xml``, ``document_xml``, ``masters_xml`` and the other document parts
   Refused with ``ValueError``. Removing the part would leave relationships
   and content-type overrides naming it. ``page.rels_xml = None`` still
   removes a page's relationships part.

Parts are named by part name
----------------------------

A document holds its package in memory, part by part, under each part's
OPC name, and the file-system view of 0.x is gone.

``page.filename``, ``page.rels_xml_filename``
   Now the part names, such as ``/visio/pages/page1.xml``, not paths on
   disk. ``Document.insert_shape``'s ``page_path`` takes the same part name.

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
   ``document.pages_xml`` or ``page.xml``, and compose the two checks 1.0
   keeps. ``vsdxkit.xmlio.require_tree(tree, description)`` refuses ``None``
   with :class:`vsdxkit.errors.MissingPartError`, and
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

``vis.masters_xml``
   Unchanged, as ``document.masters_xml``: it was the mixin's, and is now the
   document's own.

``vis.load_master_pages()``
   Unchanged, as ``document.load_master_pages()``: it re-reads the masters
   from the package, after the masters' XML has been edited.

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

``vis.pages`` is the one place pages are looked up, created, copied and
deleted. The ``VisioFile`` methods that did the same are gone.

``vis.get_page(n)``
   ``vis.pages[n]``, which raises ``IndexError`` where ``get_page`` returned
   ``None``.

``vis.get_page_by_name(name)``
   ``vis.pages.by_name(name)``, or ``vis.pages.require_name(name)``, which
   raises :class:`vsdxkit.errors.NotFoundError`.

``vis.get_page_names()``
   ``[page.name for page in vis.pages]``.

``vis.add_page(name)``
   ``vis.pages.create(name)``.

``vis.add_page_at(index, name)``
   ``vis.pages.create(name, index=index)``. ``index`` runs from 0 to
   ``len(vis.pages)``.

``vis.copy_page(page, index=..., name=...)``
   ``vis.pages.copy(page, name=..., index=...)``. With no ``index`` the copy
   goes straight after ``page``. A page of another document is refused.

``vis.remove_page_by_index(index)``
   ``vis.pages.delete(vis.pages[index])``.

``vis.remove_page_by_name(name)``
   ``vis.pages.delete(vis.pages.require_name(name))``. A name no page has
   raises :class:`vsdxkit.errors.NotFoundError`, where 0.x did nothing.

``PagePosition.FIRST``, ``PagePosition.LAST``, ``PagePosition.END``, ``PagePosition.BEFORE``, ``PagePosition.AFTER``
   An index instead: ``index=0`` for the first page, ``len(vis.pages)`` (or no
   index, for ``create``) for the end, ``vis.pages.index(page)`` for before a
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

``shape.data_properties``
   Also a new ``dict`` on each read; 0.8 returned the same one while the
   property rows were unchanged. A key added to the dict, or a dict kept
   from an earlier read, is not the shape's. Change a property through its
   :class:`vsdxkit.shapes.DataProperty`:
   ``shape.data_properties["Status"].value = "Done"``.

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
