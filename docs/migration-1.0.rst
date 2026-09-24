Migrating to 1.0
================

1.0 removes the names and behaviour listed here. Each entry gives the 0.x call
and what replaces it. The guide grows with each 1.0 change until the release.

``Document`` replaces ``VisioFile``
-----------------------------------

The class is :class:`vsdxkit.document.Document`, in the module
``vsdxkit.document``. ``vsdxkit.vsdxfile`` is gone.

``from vsdxkit.vsdxfile import VisioFile``
   ``from vsdxkit.document import Document``

``VisioFile(path)``, ``VisioFile(path, limits=..., limits_path=...)``
   ``Document.open(path)``, with the same keyword arguments. ``path`` may be
   a ``str`` or a :class:`pathlib.Path`.

``VisioFile(path, debug=True)``
   Configure logging instead. The library logs under ``vsdxkit`` and never
   configures a handler itself:

   .. code-block:: python

      import logging

      logging.basicConfig()
      logging.getLogger("vsdxkit").setLevel(logging.DEBUG)

``VisioFile.save_vsdx(new_filename=None)``
   ``Document.save(target=None)``, which returns the absolute
   :class:`pathlib.Path` it wrote. ``target`` may be a ``str`` or a ``Path``.

``VisioFile.jinja_render_vsdx(context)``
   ``Document.render(context)``.

``VisioFile.open_vsdx_file()``
   ``Document.open(path)`` opens a fresh document from the file.

``VisioFile.debug``, ``VisioFile.limits``
   Gone. The limits a document was opened with are applied at open and not
   kept.

A document has no close state
-----------------------------

A document reads its whole package into memory when it opens and holds no
file, so there is nothing to close. The context manager, ``close_vsdx()`` and
the closed-document error are gone, and a document can be edited for as long
as you hold it.

``with VisioFile(path) as vis:``
   Assign instead. ``with`` now raises ``TypeError`` (``AttributeError`` on
   Python 3.10).

   .. code-block:: python

      # 0.x
      with VisioFile("diagram.vsdx") as vis:
          vis.pages[0].name = "Current state"
          vis.save_vsdx()

      # 1.0
      vis = Document.open("diagram.vsdx")
      vis.pages[0].name = "Current state"
      vis.save()

``VisioFile.close_vsdx()``
   Delete the call. Nothing needs releasing.

``VisioFile.file_open``
   Delete the check. A document is always open.

``vsdxkit.errors.VisioFileNotOpen``
   Delete the ``except`` clause. Nothing raises it. A write through a shape
   that has been deleted from its page still raises
   :class:`vsdxkit.errors.InvalidOperationError`.

A page creates its own shapes
-----------------------------

Shapes are created by the page they go on, from a
:class:`vsdxkit.shape_kind.ShapeKind` or from a shape already in the document.
Palette-name strings are gone.

``vis.create_shape(page, "PALETTE_PROCESS", x, y, w, h, text="...")``
   ``page.create_shape(ShapeKind.PROCESS, x=x, y=y, width=w, height=h, text="...")``,
   with ``from vsdxkit.shape_kind import ShapeKind``. The position is
   keyword-only and ``w``/``h`` are now ``width``/``height``. ``PALETTE_X``
   becomes ``ShapeKind.X`` for ``PROCESS``, ``DECISION``, ``START_END``,
   ``PARALLELOGRAM`` and ``DATABASE``; ``RECTANGLE``, ``CIRCLE`` and ``LINE``
   are new. A string raises ``TypeError``.

A copy of an existing shape
   ``page.create_shape(shape, x=x, y=y)`` places a copy of ``shape``, with its
   text, on ``page``. ``shape`` must belong to the same document.

``ConnectorOptions(routing=None)``
   ``ConnectorOptions(routing=Routing.DEFAULT)``, which is also the default:
   the connector keeps the routing Visio gives it. ``None`` raises
   ``TypeError``.
