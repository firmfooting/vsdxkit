Create shapes and connectors
============================

Create shapes
-------------

:meth:`vsdx.vsdxfile.VisioFile.create_shape` copies a masterless shape from
the bundled palette into an existing page. Coordinates are Visio page units,
normally inches, and identify the centre of the shape.

.. code-block:: python

   from vsdx import VisioFile

   with VisioFile("diagram.vsdx") as vis:
       page = vis.pages[0]

       start = vis.create_shape(
           page, "PALETTE_START_END", 2.0, 6.0, text="Start"
       )
       work = vis.create_shape(
           page, "PALETTE_PROCESS", 6.0, 6.0,
           w=2.0, h=1.0, text="Do the thing"
       )
       decision = vis.create_shape(
           page, "PALETTE_DECISION", 10.0, 6.0, text="OK?"
       )

       page.connect_shapes(start, work)
       page.connect_shapes(work, decision, route="rightangle")
       vis.save_vsdx("flow.vsdx")

Palette names
-------------

The bundled palette exposes these names:

* ``PALETTE_PROCESS``
* ``PALETTE_DECISION``
* ``PALETTE_START_END``
* ``PALETTE_PARALLELOGRAM``
* ``PALETTE_DATABASE``

An unknown name raises ``vsdxkit.NotFoundError``.

Connector glue and routing
--------------------------

:meth:`vsdx.pages.Page.connect_shapes` returns the new connector as a
:class:`vsdx.shapes.Shape`.

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

Re-anchor a connector
---------------------

:meth:`vsdx.pages.Page.reanchor_connector` moves either or both endpoints.
Pass ``None`` to retain an existing endpoint.

.. code-block:: python

   connector = page.find_shape_by_id("9")
   new_target = page.find_shape_by_text("Store")

   if connector is not None and new_target is not None:
       page.reanchor_connector(connector, to_shape=new_target)

Delete a connected shape
------------------------

Use :meth:`vsdx.pages.Page.delete_shape` when connector cleanup matters. It
removes incident connector shapes and their ``Connect`` records before it
removes the requested shape.

.. code-block:: python

   obsolete = page.find_shape_by_text("Obsolete")
   if obsolete is not None:
       page.delete_shape(obsolete)
