Cross-functional flowchart swimlanes
====================================

Swimlane operations work on a page that already contains a Microsoft Visio
cross-functional flowchart (CFF) container. The library does not turn an
ordinary page into a CFF diagram.

Find the container
------------------

.. code-block:: python

   from vsdxkit import VisioFile

   with VisioFile("cross-functional-flow.vsdx") as vis:
       page = vis.pages[0]
       container = page.get_container()

       if container is None:
           raise ValueError("The page is not a Visio CFF diagram")

       for lane in container.lanes:
           print(lane.shape_name, container.members(lane))

:attr:`vsdxkit.containers.Container.lanes` returns the lane shapes in visual order,
from top to bottom.

Add a lane
----------

:meth:`vsdxkit.pages.Page.add_swimlane` clones the current top lane, places the
new lane above it, sets the heading and grows the Swimlane List and CFF
Container to match.

.. code-block:: python

   review_lane = page.add_swimlane("Review")

Add a shape to a lane
---------------------

.. code-block:: python

   check = vis.create_shape(
       page, "PALETTE_PROCESS", 6.0, 2.0, text="Check"
   )
   page.add_shape_to_lane(check, review_lane)

   assert container.lane_of(check) is not None
   vis.save_vsdx("with-review-lane.vsdx")

Membership is geometric
-----------------------

Visio CFF files do not store ordinary flowchart shapes beneath the lane in the
XML tree and do not expose a separate lane-membership field. A shape belongs to
the lane whose vertical band contains its centre. ``lane_of()``, ``members()``
and ``add_shape_to_lane()`` all use that model.

Moving a shape between lanes therefore changes its position. It does not add a
membership tag.
