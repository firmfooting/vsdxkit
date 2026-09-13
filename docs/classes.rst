API reference
=============

The distribution installs as ``vsdxkit`` but keeps the ``vsdx`` import
namespace.

VisioFile
---------

.. autoclass:: vsdxkit.vsdxfile.VisioFile
   :members: add_page, add_page_at, copy_page, create_shape, get_page_by_name, jinja_render_vsdx, remove_page_by_index, remove_page_by_name, save_vsdx
   :undoc-members:
   :special-members: __init__, __enter__, __exit__

Page and PagePosition
---------------------

.. autoclass:: vsdxkit.pages.Page
   :members: all_shapes, child_shapes, connect_shapes, connects, delete_shape, find_shape_by_id, find_shape_by_text, find_shapes_by_text, get_connectors_between, get_container, add_swimlane, add_shape_to_lane, reanchor_connector
   :undoc-members:

.. autoclass:: vsdxkit.pages.PagePosition
   :members:
   :undoc-members:

Shape, Cell and DataProperty
----------------------------

.. autoclass:: vsdxkit.shapes.Shape
   :members: ID, all_shapes, bounds, cell_value, cells, center_x_y, child_shapes, connected_shapes, connects, copy, data_properties, fill_color, find_replace, find_shape_by_text, find_shapes_by_text, geometry, get_or_create_cell, height, line_color, line_weight, master_page_ID, master_shape_ID, move, remove, shape_name, shape_type, tag, text, text_color, width, x, y
   :undoc-members:

.. autoclass:: vsdxkit.shapes.Cell
   :members:
   :undoc-members:

.. autoclass:: vsdxkit.shapes.DataProperty
   :members:
   :undoc-members:

Connect and Container
---------------------

.. autoclass:: vsdxkit.connectors.Connect
   :members: connector_shape, connector_shape_id, shape, shape_id
   :undoc-members:

Connection records also expose the raw ``from_id``, ``to_id``, ``from_rel``
and ``to_rel`` values from the Visio ``Connect`` element. ``from_id`` is the
connector shape ID. ``to_id`` is the connected shape ID. The relationship
fields identify the source and target cells, such as ``BeginX``, ``EndX``,
``PinX`` or ``Connections.X1``.

.. py:attribute:: vsdxkit.connectors.Connect.from_id
   :type: str | None

.. py:attribute:: vsdxkit.connectors.Connect.to_id
   :type: str | None

.. py:attribute:: vsdxkit.connectors.Connect.from_rel
   :type: str | None

.. py:attribute:: vsdxkit.connectors.Connect.to_rel
   :type: str | None

.. autoclass:: vsdxkit.containers.Container
   :members: add_shape_to_lane, add_swimlane, container_shape, find, lane_band, lane_heading, lane_of, lanes, members, set_lane_label, swimlane_list
   :undoc-members:

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
   |   +-- VisioFileNotOpen
   +-- NotFoundError (ValueError)
   |   +-- MissingPartError
   +-- PackageError
       +-- MalformedPackageError (ValueError)
       +-- PackageLimitError (OSError)

.. autoclass:: vsdxkit.errors.VsdxError

.. autoclass:: vsdxkit.errors.InvalidOperationError

.. autoclass:: vsdxkit.errors.VisioFileNotOpen

.. autoclass:: vsdxkit.errors.NotFoundError

.. autoclass:: vsdxkit.errors.MissingPartError

.. autoclass:: vsdxkit.errors.PackageError

.. autoclass:: vsdxkit.errors.MalformedPackageError

.. autoclass:: vsdxkit.errors.PackageLimitError
