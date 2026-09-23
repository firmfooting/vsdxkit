Find pages and shapes
=====================

A Visio document contains pages. Each page contains top-level shapes, and a
shape may contain nested shapes of its own.

Select a page
-------------

Pages can be selected by zero-based index or case-sensitive name.

.. code-block:: python

   from vsdxkit.vsdxfile import VisioFile

   with VisioFile("diagram.vsdx") as vis:
       first_page = vis.pages[0]
       named_page = vis.get_page_by_name("Current state")

       print(first_page.name)
       if named_page is not None:
           print(named_page.name)

Find one shape
--------------

The ``find_shape_*`` methods return the first matching
:class:`vsdxkit.shapes.Shape`, or ``None``.

.. code-block:: python

   with VisioFile("diagram.vsdx") as vis:
       page = vis.pages[0]

       by_id = page.find_shape_by_id("1")
       by_text = page.find_shape_by_text("Assessment")
       by_label = page.find_shape_by_property_label("Status")
       by_data = page.find_shape_by_property_label_value("Status", "Open")

Shape Data labels are the names shown in Visio's Shape Data window. They are
not necessarily the internal row names stored in the file.

Find several shapes
-------------------

The plural methods return ``list[Shape]`` and return an empty list when there
are no matches.

.. code-block:: python

   with VisioFile("diagram.vsdx") as vis:
       page = vis.pages[0]

       mentions_review = page.find_shapes_by_text("Review")
       status_fields = page.find_shapes_by_property_label("Status")
       open_items = page.find_shapes_by_property_label_value("Status", "Open")
       numbered_steps = page.find_shapes_by_regex(r"Step \d+")

Search within a grouped shape
-----------------------------

Page and Shape expose the same recursive finder pattern. Search a group when a
match should be constrained to that subtree.

.. code-block:: python

   group = page.find_shape_by_text("Assessment group")
   if group is not None:
       task = group.find_shape_by_text("Review")

Traverse the hierarchy
----------------------

``child_shapes`` contains only direct children. ``all_shapes`` recursively
includes descendants.

.. code-block:: python

   top_level = page.child_shapes
   every_shape = page.all_shapes

   if every_shape:
       direct_children = every_shape[0].child_shapes
       all_descendants = every_shape[0].all_shapes
