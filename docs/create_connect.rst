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
   from vsdxkit.glue import Routing
   from vsdxkit.shape_kind import ShapeKind

   vis = Document.open("diagram.vsdx")
   page = vis.pages[0]

   start = page.create_shape(ShapeKind.START_END, x=2.0, y=6.0, text="Start")
   work = page.create_shape(
       ShapeKind.PROCESS, x=6.0, y=6.0, width=2.0, height=1.0, text="Do the thing"
   )
   decision = page.create_shape(ShapeKind.DECISION, x=10.0, y=6.0, text="OK?")

   page.connect(start, work)
   page.connect(work, decision, routing=Routing.RIGHT_ANGLE)
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

:meth:`vsdxkit.pages.Page.connect` is the one way to create a connector. It
returns a :class:`vsdxkit.shapes.Connector`, a shape whose
:attr:`~vsdxkit.shapes.Connector.source` and
:attr:`~vsdxkit.shapes.Connector.target` are the shapes its ends are glued to.

``glue``
   :attr:`vsdxkit.glue.Glue.DYNAMIC`, the default, walks each end round its
   shape to the nearest side. :attr:`vsdxkit.glue.Glue.POINT` glues the ends to
   ``from_point`` and ``to_point``, zero-based rows of each shape's
   ``Connection`` section.

``routing``
   :attr:`vsdxkit.glue.Routing.DEFAULT` is Visio's own: dynamic glue reroutes
   at right angles and point glue stays straight. ``STRAIGHT``,
   ``RIGHT_ANGLE`` and ``CURVED`` choose the path.

.. code-block:: python

   from vsdxkit.glue import Glue, Routing

   connector = page.connect(
       source,
       target,
       glue=Glue.POINT,
       routing=Routing.CURVED,
       from_point=0,
       to_point=2,
   )

A connection point counts whether the shape holds it or inherits it from its
master. Both shapes must be on the page. Everything is checked before the
connector is created, so a refused call leaves the page as it was.

Find connectors
---------------

A connector either end of which is floating still counts as a connector; its
floating end's ``source`` or ``target`` is ``None``.

:attr:`vsdxkit.pages.Page.connectors`
   Every connector on the page, at any depth.

:attr:`vsdxkit.shapes.Shape.connectors`
   The connectors glued to a shape at either end.

:attr:`vsdxkit.shapes.Shape.connected_shapes`
   The shape at the other end of each of those, each once.

All three are tuples. The connectors between two shapes are the ones both list:

.. code-block:: python

   between = set(start.connectors) & set(work.connectors)

Retarget a connector
--------------------

:meth:`vsdxkit.shapes.Connector.retarget` moves either or both ends. Name the
end that moves, as ``source`` or ``target``; an end not named stays where it
is, floating if it was. Naming neither raises
:class:`vsdxkit.errors.InvalidOperationError`.

Without ``options``, the connector keeps its glue and routing. A moved end
keeps the connection point it was glued to, and a point the new shape does not
have raises :class:`vsdxkit.errors.InvalidOperationError`. It does not fall
back to dynamic glue. An end that was floating, or glued dynamically, is glued
dynamically. A :class:`vsdxkit.glue.ConnectorOptions` passed as ``options``
replaces the glue and routing of both ends.

.. code-block:: python

   from vsdxkit.glue import ConnectorOptions, Glue

   new_target = page.shapes.require_text("Store")
   connector.retarget(target=new_target)
   connector.retarget(target=new_target, options=ConnectorOptions(glue=Glue.POINT, to_point=1))

Delete a connected shape
------------------------

Use :meth:`vsdxkit.pages.Page.delete_shape` when connector cleanup matters. It
removes incident connector shapes and their ``Connect`` records before it
removes the requested shape.

.. code-block:: python

   obsolete = page.shapes.by_text("Obsolete")
   if obsolete is not None:
       page.delete_shape(obsolete)
