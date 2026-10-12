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
drawn on an opaque white background. The layout leaves room for each edge label
and each group heading: a gap widens to hold the labels that cross it, a group
box widens and grows at the top to hold its heading, and a label or heading that
cannot be placed clear of the nodes, headings, other groups and other labels, or
a heading that would make its box cover a node or group that is not its own, is
refused.

:meth:`~vsdxkit.builder.Diagram.validate` refuses a description that cannot be
drawn, naming the first thing wrong, as :class:`~vsdxkit.errors.GraphError`.
:meth:`~vsdxkit.builder.Diagram.build` and :meth:`~vsdxkit.builder.Diagram.save`
call it first.

Text must be a string, and a character XML 1.0 cannot carry (a control character
other than tab, newline and carriage return, a lone surrogate, U+FFFE or U+FFFF)
is refused, in the title, page names, ids, labels, sublabels and Shape Data. Shape
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

Page shape
----------

A long linear flow would draw as a strip, so the layout aims for a page shape
and wraps the flow into rows. The default is
``LayoutOptions(page=PageTarget(aspect=16 / 9))``: the layers are cut into rows,
each row runs against the one above it so a row ends over the start of the next,
and the number of rows is the one whose width over height lands nearest the
aspect. When ``LayoutOptions.direction`` is not given and ``PageTarget.direction`` is ``auto``,
the page is also laid out top down when its left-to-right shape misses the band, and the nearer result is kept. There is no
maximum size; the page grows as large as the content needs.

.. code-block:: python

   from vsdxkit.layout import LayoutOptions, PageTarget

   wide = LayoutOptions(page=PageTarget(aspect=16 / 9))
   one_row = LayoutOptions(page=None)

Pass ``page=None`` to keep one row. Top-down flows are not wrapped. A
``LayoutOptions(direction=...)`` you give is always kept; the target chooses the
direction only when you give none, and ``PageTarget(direction=...)`` pins it. A page with lanes is never wrapped,
because a lane runs the whole width, so its width is the number of layers; one
that grows past the lane limit (see "Lanes and groups" below) is refused with
the number of columns it needed, and the flow has to be split across pages.

Straightening, pinned layers and aligned nodes
----------------------------------------------

Within its lane and track a box moves toward the boxes it connects to, so that an
edge between boxes that overlap across the flow runs straight.
``LayoutOptions.straighten_sweeps`` sets how many down-and-up passes do this, and
zero keeps each run centred. Within a layer the order that crosses fewest edges is
kept.

``Node.layer`` pins a node to a layer, counted from zero (a column, or a row when
flowing top down). It must come after every layer that feeds the node, and the
nodes it feeds move after it. ``Page.align`` lists groups of node ids drawn on one
row (one column when flowing top down); the members of a group are in different
layers and one lane. A pin that precedes a feeder, a node in two groups and a
group that cannot share a row are refused with a :class:`~vsdxkit.errors.GraphError`
that names them. A page wrapped into rows can put group members in different
bands, so give such a page ``LayoutOptions(page=None)`` to align them.

.. code-block:: python

   from vsdxkit.layout import LayoutOptions

   nodes = [
       Node("top", "start", "Intake"),
       Node("left", "process", "Check"),
       Node("right", "process", "Review"),
       Node("bottom", "end", "Archive", layer=3),
   ]
   edges = [Edge("top", "left"), Edge("top", "right"), Edge("left", "bottom"), Edge("right", "bottom")]
   page = Page("pins", nodes, edges, align=[["top", "bottom"]])
   Diagram("pins", [page]).save("pins.vsdx", layout=LayoutOptions(page=None))

``LayoutOptions(columns="even")`` gives every column the widest column's width and
every gap the largest gap, so boxes in a row line up; the default, ``"natural"``,
sizes each to what it holds.

On a page without lanes, a feedback edge that jumps layers runs in a corridor
outside the drawing, and between neighbouring rows on a wrapped page, instead of
through a slot in each layer it jumps.

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

Each edge meets a box at a point of its own, ordered by where its other end lies,
and routes between layers run in channels, one line for each route. The spacing
is set by ``LayoutOptions.port_pitch`` (between points on one side of a box) and
``LayoutOptions.channel_pitch`` (between parallel routes in a gap between layers).

The layout keeps every route on a line of its own, and refuses a page it cannot
do that for, within a fixed number of search steps for each of its two passes
(border points of their own, then shared ones). Measured on random graphs, the
default options lay out 60 nodes and 200 edges in 6 groups, 150 nodes and 240
edges in 4 lanes and 4 groups, 200 nodes and 320 edges in 4 lanes and 4 groups
(about 17 seconds), and 200 nodes and 400 edges with no groups. 200 nodes and
400 edges in 20 groups is refused with a :class:`~vsdxkit.errors.GraphError`
that names the counts, after about 40 seconds. Groups and lanes lower the
ceiling more than nodes do; fewer edges or groups bring a refused page back.

Shape Data
----------

Every node, lane, group and edge the builder draws carries a Shape Data row
``Source``, which holds ``Node.data["Source"]`` when given and the id
otherwise, and a row ``Kind``. The rest of ``Node.data`` follows, sorted by
name. Reading a shape back by ``Source`` is how a test, or a reviewer, maps a
shape in Visio to the node it came from. On a page with lanes, nodes of kind
``start``, ``end``, ``process`` and ``decision`` are instances of Visio's flowchart
masters and so also carry that master's Shape Data rows (``Function`` is the
heading of the lane).

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
