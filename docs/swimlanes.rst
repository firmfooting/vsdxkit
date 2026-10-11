Cross-functional flowchart swimlanes
====================================

Swimlane operations work on a page that contains a Microsoft Visio
cross-functional flowchart (CFF) container: one Visio drew, or one made with
:meth:`~vsdxkit.pages.Page.create_swimlanes`. The library does not turn an
ordinary page with shapes on it into a CFF diagram.

Create the diagram
------------------

:meth:`~vsdxkit.pages.Page.create_swimlanes` copies the diagram Visio draws for
its Cross-Functional Flowchart template onto a page that has none, with one
lane for each ``(label, height)`` band, top to bottom, and sizes it. Do it
before adding shapes: the copy takes shape IDs below 1000, and a page whose IDs
leave no room for it is refused.

.. code-block:: python

   from vsdxkit.document import Document

   document = Document.new()
   page = document.pages[0]
   page.width, page.height = 12.0, 8.0
   diagram = page.create_swimlanes([("Requester", 1.5), ("Reviewer", 2.0)], left=0.5, top=7.0, width=10.0)
   document.save("lanes.vsdx")

The diagram's container stands a title bar, 15 mm high, above the first lane,
so ``top`` is the top of the first lane and not of the container.

Find the diagram
----------------

:attr:`vsdxkit.pages.Page.swimlanes` is the page's
:class:`vsdxkit.swimlanes.SwimlaneDiagram`, or ``None`` on a page with no CFF
container. :meth:`vsdxkit.pages.Page.require_swimlanes` raises
:class:`vsdxkit.errors.NotFoundError` instead. A page with more than one CFF
container is ambiguous, and both raise
:class:`vsdxkit.errors.InvalidOperationError`.

.. code-block:: python

   from vsdxkit.document import Document

   document = Document.open("cross-functional-flow.vsdx")
   page = document.pages[0]
   diagram = page.require_swimlanes()

   for lane in diagram.lanes:
       print(lane.shape_name, diagram.shapes_in(lane))

:attr:`~vsdxkit.swimlanes.SwimlaneDiagram.lanes` returns the lane shapes in
visual order, from top to bottom.

Add a lane
----------

:meth:`~vsdxkit.swimlanes.SwimlaneDiagram.add_lane` copies the top lane, places
the copy one lane above it, sets its heading and grows the Swimlane List and CFF
container to match. A label the lane cannot take is refused before anything is
written.

.. code-block:: python

   review_lane = diagram.add_lane("Review")

Put a shape in a lane
---------------------

.. code-block:: python

   from vsdxkit.shape_kind import ShapeKind

   check = page.create_shape(ShapeKind.PROCESS, x=6.0, y=2.0, text="Check")
   diagram.move_to_lane(check, review_lane)

   assert diagram.lane_for(check) == review_lane
   document.save("with-review-lane.vsdx")

Membership is geometric
-----------------------

Visio CFF files do not store ordinary flowchart shapes beneath the lane in the
XML tree and do not expose a separate lane-membership field. A shape belongs to
the lane whose vertical band contains its centre.
:meth:`~vsdxkit.swimlanes.SwimlaneDiagram.lane_for`,
:meth:`~vsdxkit.swimlanes.SwimlaneDiagram.shapes_in` and
:meth:`~vsdxkit.swimlanes.SwimlaneDiagram.move_to_lane` all use that model.

A band includes its bottom edge and not its top, so a shape on the edge two
lanes share is in the upper lane. Lanes that overlap make ``lane_for`` raise
:class:`vsdxkit.errors.InvalidOperationError` for a shape in the overlap.

Moving a shape between lanes therefore changes its position. It does not add a
membership tag.
