Diagrams from data
==================

:mod:`vsdxkit.builder` describes a diagram as values and compiles it to a
Visio document. No coordinates are given: the layout puts every node in a
layer along the flow, gives each lane a band and each group a box, and routes
every edge in right angles that meet no node. Every shape is written with
explicit geometry, so the drawing does not depend on Visio computing a layout
when the file opens.

Describe the diagram
--------------------

A :class:`~vsdxkit.builder.Diagram` is a title and pages. A
:class:`~vsdxkit.builder.Page` holds :class:`~vsdxkit.builder.Node`,
:class:`~vsdxkit.builder.Edge`, :class:`~vsdxkit.builder.Group` and
:class:`~vsdxkit.builder.Lane` values. Every id is a string of your choosing,
and an id is unique across the whole diagram, lanes and groups included.

.. code-block:: python

   from vsdxkit.builder import Diagram, Edge, Group, Lane, Node, Page

   nodes = [
       Node("start", "start", "Request received"),
       Node("check", "decision", "Complete?", sublabel="all fields present"),
       Node("fix", "process", "Ask for the missing details"),
       Node("file", "data_store", "Request register"),
       Node("done", "end", "Closed"),
   ]
   edges = [
       Edge("start", "check"),
       Edge("check", "fix", "No", "no-path"),
       Edge("fix", "check"),
       Edge("check", "file", "Yes", "yes-path"),
       Edge("file", "done"),
   ]
   page = Page(
       "Intake",
       nodes,
       edges,
       groups=[Group("loop", "Completeness check", ["check", "fix"])],
       lanes=[Lane("front", "Front desk", ["start", "check", "fix"]), Lane("back", "Records", ["file", "done"])],
   )
   diagram = Diagram("Intake process", [page])

Node kinds are ``start``, ``end``, ``process``, ``decision``, ``data_store``,
``external``, ``document``, ``subprocess`` and ``off_page``. Edge kinds are
``flow``, ``yes-path``, ``no-path``, ``data``, ``call`` and ``page-link``. The
``no-path``, ``data`` and ``call`` edges are drawn dashed. An edge label is
drawn on an opaque white background.

:meth:`~vsdxkit.builder.Diagram.validate` refuses a description that cannot be
drawn, naming the first thing wrong, as :class:`~vsdxkit.errors.GraphError`.
:meth:`~vsdxkit.builder.Diagram.build` and :meth:`~vsdxkit.builder.Diagram.save`
call it first.

Text must be a string, and a control character other than tab and newline is
refused, in the title, page names, ids, labels, sublabels and Shape Data. Shape
Data names and values are strings, and a ``Kind`` entry is refused because the
node's kind is always written.

Build and save
--------------

:meth:`~vsdxkit.builder.Diagram.build` returns a
:class:`~vsdxkit.document.Document` to carry on editing.
:meth:`~vsdxkit.builder.Diagram.save` builds and writes it with a deterministic
save, so equal diagrams give equal bytes.

.. code-block:: python

   path = diagram.save("intake.vsdx")

Pass :class:`~vsdxkit.layout.LayoutOptions` as ``layout=`` to flow top down
instead of left to right, or to change the spacing. Lanes need the left-to-right
flow.

Lanes and groups
----------------

When a page has lanes, every node on it is in exactly one. A group holds nodes
from one lane only, and groups nest one level. ``node_ids`` of a lane or a group
is a list of ids; a bare string is refused, because it would read as one id per
character.

A page with lanes is drawn with the swimlane support described in
:doc:`swimlanes`, so it has the same limits: at most five lanes, each 0.5 to 6
inches tall, a lane label of at most 11 characters for each inch of the lane's
height, and a diagram at most 60 inches wide. How tall and wide the lanes come
out is known only after layout, so :meth:`~vsdxkit.builder.Diagram.build` refuses
a laid-out page that does not fit, with a :class:`~vsdxkit.errors.GraphError`
that says so. Fewer layers or nodes in a row bring it back within the limits.

Shape Data
----------

Every node, lane, group and edge the builder draws carries a Shape Data row
``Source``, which holds ``Node.data["Source"]`` when given and the id
otherwise, and a row ``Kind``. The rest of ``Node.data`` follows, sorted by
name. Reading a shape back by ``Source`` is how a test, or a reviewer, maps a
shape in Visio to the node it came from.

Pages
-----

A diagram with several pages becomes a document with several pages, in order.
An ``off_page`` node can be joined to an ``off_page`` node on another page by
an edge of kind ``page-link``, listed on the page of its source. The link is not
drawn as a connector; each end records the other's page and node in the Shape
Data rows ``Linked page`` and ``Linked node``. Those two names are reserved on
an ``off_page`` node, so a ``data`` entry with either is refused, and an
``off_page`` node ends at most one ``page-link``.

.. code-block:: python

   from vsdxkit.builder import Diagram, Edge, Node, Page

   handoff = Diagram(
       "Handoff",
       [
           Page(
               "Intake",
               [Node("a", "process", "Take the request"), Node("a-out", "off_page", "To review")],
               [Edge("a", "a-out"), Edge("a-out", "r-in", kind="page-link")],
           ),
           Page(
               "Review",
               [Node("r-in", "off_page", "From intake"), Node("r", "process", "Review the request")],
               [Edge("r-in", "r")],
           ),
       ],
   )
   handoff.save("handoff.vsdx")

Starting a document yourself
----------------------------

The builder starts from :meth:`vsdxkit.document.Document.new`, a blank
one-page drawing with no file behind it. It can be used directly, to build on
with :meth:`~vsdxkit.pages.Page.create_shape`,
:meth:`~vsdxkit.pages.Page.connect` and
:meth:`~vsdxkit.pages.Page.create_swimlanes`, and saved with
``save(path, deterministic=True)`` for byte-identical output.
