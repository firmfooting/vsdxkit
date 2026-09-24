Create shapes and connectors
============================

Create shapes
-------------

:meth:`vsdxkit.pages.Page.create_shape` places a new shape on the page, either
one of the built-in :class:`vsdxkit.shape_kind.ShapeKind` shapes or a copy of a
shape already in the document. Coordinates are Visio page units, normally
inches, and identify the centre of the shape. ``x`` and ``y`` are keyword-only;
``width``, ``height`` and ``text`` are optional.

.. code-block:: python

   from vsdxkit.document import Document
   from vsdxkit.shape_kind import ShapeKind

   vis = Document.open("diagram.vsdx")
   page = vis.pages[0]

   start = page.create_shape(ShapeKind.START_END, x=2.0, y=6.0, text="Start")
   work = page.create_shape(
       ShapeKind.PROCESS, x=6.0, y=6.0, width=2.0, height=1.0, text="Do the thing"
   )
   decision = page.create_shape(ShapeKind.DECISION, x=10.0, y=6.0, text="OK?")

   page.connect_shapes(start, work)
   page.connect_shapes(work, decision, route="rightangle")
   vis.save("flow.vsdx")

Shape kinds
-----------

:class:`vsdxkit.shape_kind.ShapeKind` names the built-in shapes:
``PROCESS``, ``DECISION``, ``START_END``, ``PARALLELOGRAM``, ``DATABASE``,
``RECTANGLE``, ``CIRCLE`` and ``LINE``. A string is refused with ``TypeError``.

Copy a shape
------------

Pass a shape instead of a kind to place a copy of it, with its text, at the
new position. The shape must belong to the same document; a shape from another
document raises ``vsdxkit.errors.InvalidOperationError``.

.. code-block:: python

   again = page.create_shape(work, x=6.0, y=3.0, text="Do it again")

Connector glue and routing
--------------------------

:meth:`vsdxkit.pages.Page.connect_shapes` returns the new connector as a
:class:`vsdxkit.shapes.Shape`.

``dynamic``
   Dynamic shape glue. This is the default.

``point``
   Glue to zero-based connection points selected with ``from_cp`` and
   ``to_cp``.

``straight``, ``rightangle`` or ``curved``
   Dynamic glue with the selected route style.

``point|straight``, ``point|rightangle`` or ``point|curved``
   Connection-point glue with the selected route style.

.. code-block:: python

   connector = page.connect_shapes(
       source,
       target,
       route="point|curved",
       from_cp=0,
       to_cp=2,
   )

The same choice can be passed as a :class:`vsdxkit.glue.ConnectorOptions`
instead of a ``route`` string. Pass one or the other:

.. code-block:: python

   from vsdxkit.glue import ConnectorOptions, Glue, Routing

   connector = page.connect_shapes(
       source,
       target,
       options=ConnectorOptions(glue=Glue.POINT, routing=Routing.CURVED, to_point=2),
   )

A connection point counts whether the shape holds it or inherits it from its
master. Both shapes must be on the page. Everything is checked before the
connector is created, so a refused call leaves the page as it was.

Re-anchor a connector
---------------------

:meth:`vsdxkit.pages.Page.reanchor_connector` moves either or both endpoints.
Pass ``None`` to retain an existing endpoint.

Without ``options`` or ``route``, the connector keeps its glue and routing. A
moved end keeps the connection point it was glued to, and a point the new shape
does not have raises :class:`vsdxkit.errors.InvalidOperationError`. It does not
fall back to dynamic glue. An end that was floating, or glued dynamically, is
glued dynamically. An end left as ``None`` stays where it is, floating if it
was. ``options`` or ``route`` replace the glue and routing of both ends.

.. code-block:: python

   connector = page.shapes.by_id("9")
   new_target = page.shapes.by_text("Store")

   if connector is not None and new_target is not None:
       page.reanchor_connector(connector, to_shape=new_target)

Delete a connected shape
------------------------

Use :meth:`vsdxkit.pages.Page.delete_shape` when connector cleanup matters. It
removes incident connector shapes and their ``Connect`` records before it
removes the requested shape.

.. code-block:: python

   obsolete = page.shapes.by_text("Obsolete")
   if obsolete is not None:
       page.delete_shape(obsolete)
