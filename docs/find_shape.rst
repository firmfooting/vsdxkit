Find pages and shapes
=====================

A Visio document contains pages. Each page contains top-level shapes, and a
shape may contain nested shapes of its own.

Select a page
-------------

``vis.pages`` is a :class:`vsdxkit.pages.PageCollection`: a sequence of the
document's pages in order, with lookup by name.

.. code-block:: python

   from vsdxkit.vsdxfile import VisioFile

   with VisioFile("diagram.vsdx") as vis:
       first_page = vis.pages[0]
       current = vis.pages.require_name("Current state")
       draft = vis.pages.by_name("Draft")  # None if there is no such page

       for page in vis.pages:
           print(page.name)

Page names are unique in a document, so two pages with one name raise
:class:`vsdxkit.errors.PackageError`.

Add, copy and delete pages
--------------------------

.. code-block:: python

   review = vis.pages.create("Review")              # at the end
   cover = vis.pages.create("Cover", index=0)        # at the front
   again = vis.pages.copy(review, name="Review 2")   # straight after review
   vis.pages.delete(cover)

``index`` is the position the new page will take, from 0 to ``len(vis.pages)``.
A page can be copied only within its own document.

Find shapes in a scope
----------------------

Every lookup goes through a :class:`vsdxkit.shapes.ShapeCollection`, which is a
fixed scope of shapes:

- ``page.children``: the page's top-level shapes;
- ``page.shapes``: every shape on the page, at any depth, connectors included;
- ``shape.children``: a group's direct members, empty for any other shape;
- ``shape.descendants``: every shape inside a group, at any depth.

Iterating a collection and looking up in it read the same shapes. A collection
is live: it sees shapes added or removed after it was taken.

.. code-block:: python

   with VisioFile("diagram.vsdx") as vis:
       page = vis.pages[0]

       start = page.shapes.require_text("Start")
       maybe = page.shapes.by_id("12")
       status = page.shapes.require_property("Status", "Open")

       for shape in page.children:
           print(shape.ID, shape.text)

Each lookup says how many shapes it expects:

- ``by_id``, ``by_text`` and ``by_property`` return the one match, or ``None``;
- ``require_id``, ``require_text`` and ``require_property`` return the one
  match, and raise :class:`vsdxkit.errors.NotFoundError` when there is none;
- ``matching_text`` and ``matching_property`` return every match as a tuple.

When several shapes match, the ``by_*`` and ``require_*`` forms raise
:class:`vsdxkit.errors.InvalidOperationError` naming them instead of picking
one. Shape IDs are unique on a page, so two shapes with one ID raise
:class:`vsdxkit.errors.PackageError`.

Text is matched exactly: ``require_text("Start")`` finds the shape that reads
"Start", not one that mentions it. For a looser search, filter the collection:

.. code-block:: python

   mentions_review = [shape for shape in page.shapes if "Review" in shape.text]

A property is matched by its Shape Data label, the name shown in Visio's Shape
Data window, including properties the shape inherits from its master. A value,
where one is given, is compared as text.

Shape identity
--------------

Every traversal hands back new :class:`vsdxkit.shapes.Shape` objects, and two
of them for one shape are equal and hash alike. A shape stays the same key in a
set or a dict when its ID, its page's name or the file's name changes. Shapes
from two documents are never equal, even two opens of one file.

A shape deleted from its page, or on a page removed from the document, is
detached: ``shape.is_attached`` is ``False``, and reading or changing it raises
:class:`vsdxkit.errors.InvalidOperationError`. Its ``ID`` and its ``repr`` stay
readable, so it can still be named in a message.

Earlier finders
---------------

The ``find_shape_*`` and ``find_shapes_*`` methods, ``child_shapes`` and
``all_shapes`` still work and will be removed before 1.0. They differ from the
collections in two ways: text is matched as a substring, and a lookup of one
shape returns the first match without saying that there were several.

.. code-block:: python

   by_text = page.find_shape_by_text("Assessment")
   numbered_steps = page.find_shapes_by_regex(r"Step \d+")
