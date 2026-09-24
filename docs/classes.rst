API reference
=============

Each class is imported from the module named in its heading, for example
``from vsdxkit.document import Document``. The package root re-exports nothing.

Document
--------

.. autoclass:: vsdxkit.document.Document
   :members: open, pages, save, render
   :undoc-members:

Page and PageCollection
-----------------------

.. autoclass:: vsdxkit.pages.Page
   :members: name, width, height, background, children, shapes, connect, connectors, create_shape, find_replace, swimlanes, require_swimlanes
   :undoc-members:

.. autoclass:: vsdxkit.pages.PageCollection
   :members: by_name, require_name, create, copy, delete

ShapeKind
---------

.. autoclass:: vsdxkit.shape_kind.ShapeKind
   :members:
   :undoc-members:

Shape, Connector, ShapeCollection, Cell and DataProperty
--------------------------------------------------------

.. autoclass:: vsdxkit.shapes.Shape
   :members: ID, angle, begin_x, begin_y, bounds, cell_formula, cell_value, cells, center_x_y, children, connected_shapes, connectors, copy, data_properties, delete, descendants, end_x, end_y, fill_color, find_replace, geometry, get_or_create_cell, height, is_attached, line_color, line_weight, master_page_ID, master_shape, master_shape_ID, move, set_cell_formula, set_cell_value, shape_name, shape_type, tag, text, text_color, universal_name, width, x, y
   :undoc-members:

.. autoclass:: vsdxkit.shapes.Connector
   :members: source, target, retarget
   :show-inheritance:

.. autoclass:: vsdxkit.shapes.ShapeCollection
   :members:
   :special-members: __iter__, __len__

.. autoclass:: vsdxkit.shapes.Cell
   :members:
   :undoc-members:

.. autoclass:: vsdxkit.shapes.DataProperty
   :members:
   :undoc-members:

Glue, routing and SwimlaneDiagram
---------------------------------

.. autoclass:: vsdxkit.glue.ConnectorOptions
   :members: glue, routing, from_point, to_point, end_point
   :undoc-members:

.. autoclass:: vsdxkit.glue.Glue
   :members:
   :undoc-members:

.. autoclass:: vsdxkit.glue.Routing
   :members:
   :undoc-members:

.. autoclass:: vsdxkit.swimlanes.SwimlaneDiagram
   :members: container, lanes, shapes_in, lane_for, add_lane, set_lane_label, move_to_lane

Package limits
--------------

.. autoclass:: vsdxkit.package.PackageLimits
   :members:
   :undoc-members:

Errors
------

Every error the library raises about a package, a document or an operation on
one derives from ``VsdxError``, so one ``except`` clause covers the library and
nothing else. The guarantee covers what the library checks: opening a document
validates the parts and attributes it reads on the way in, but a package that
is well-formed and breaks the schema somewhere the library only reaches later
can still surface a plain ``KeyError`` or ``AttributeError``.
Errors reporting a mistake in the arguments a caller passed stay plain
builtins: a ``TypeError`` for a ``None`` where a number belongs, or a
``ValueError`` for a page dimension that is not positive, says nothing about
Visio, packages or documents.

Most classes keep a builtin base as well, because the sites that raise them
raised that builtin before the hierarchy existed::

   VsdxError
   +-- InvalidOperationError (ValueError)
   +-- NotFoundError (ValueError)
   |   +-- MissingPartError
   +-- PackageError
       +-- MalformedPackageError (ValueError)
       |   +-- PartParseError (xml.etree.ElementTree.ParseError)
       +-- PackageLimitError (OSError)

.. autoclass:: vsdxkit.errors.VsdxError

.. autoclass:: vsdxkit.errors.InvalidOperationError

.. autoclass:: vsdxkit.errors.NotFoundError

.. autoclass:: vsdxkit.errors.MissingPartError

.. autoclass:: vsdxkit.errors.PackageError

.. autoclass:: vsdxkit.errors.MalformedPackageError

.. autoclass:: vsdxkit.errors.PartParseError

It is also an ``xml.etree.ElementTree.ParseError``, so code that caught what
the parser raised for a malformed part still catches it, ``position`` and all.

.. autoclass:: vsdxkit.errors.PackageLimitError
