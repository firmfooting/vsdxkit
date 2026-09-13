vsdxkit documentation
=====================

``vsdxkit`` creates, edits and analyses Microsoft Visio ``.vsdx`` files with
Python. The distribution is called ``vsdxkit``; code imports it as ``vsdx``.
Microsoft Visio is not required at runtime.

.. warning::

   **0.x API notice.** The 0.x line carries the inherited API and is changing
   under it: 0.8 alone made seven breaking changes, each listed in the
   changelog. 1.0 renames ``VisioFile`` to ``Document`` and ``Container`` to
   ``SwimlaneDiagram``, splits ``Connect`` into an internal
   ``ConnectionRecord`` and a public ``Connector``, and drops the context
   manager: opening closes the archive before it returns, and ``save()`` is
   the only write. The `1.0 design
   <https://github.com/firmfooting/vsdxkit/blob/main/.hermes/plans/2026-09-12_simplification-usability-refactor.md>`_
   lists every change. Pin ``vsdxkit<1`` to stay on the 0.x names.

The library works on the XML parts inside an existing Visio package. It can
query and edit shapes, create common flowchart shapes, create and re-anchor
connectors, extend existing cross-functional flowcharts, copy pages and render
Jinja-backed templates.

.. note::

   **As of 2026-09-13 there is no release on PyPI.** The first release was
   withdrawn after a security defect and cannot be republished, so
   ``pip install vsdxkit`` finds no versions until the next one lands. Install
   from the GitHub repository as described in :doc:`quickstart`. The `PyPI
   project page <https://pypi.org/project/vsdxkit/>`_ shows the current state.

.. toctree::
   :maxdepth: 2
   :caption: Guides

   quickstart
   create_connect
   swimlanes
   templating
   find_shape
   classes

Format support
--------------

* Python 3.10–3.14 on Linux, Windows and macOS
* read, edit and save ``.vsdx``
* read, edit and save ``.vsdm``, which must stay ``.vsdm``
* no Microsoft Visio dependency at runtime
* generated connectors and swimlanes checked against real Visio through COM

The library starts from an existing package. It does not construct a complete
Visio document from an empty file. A macro-enabled ``.vsdm`` can be edited and
saved, but only back to a ``.vsdm`` destination: the package kind is decided by
the content type of ``visio/document.xml``, not by the filename, so saving one
as ``.vsdx`` (or a plain drawing as ``.vsdm``) raises ``ValueError`` rather than
writing a file Visio reports as corrupt. Stripping macros to convert a ``.vsdm``
into a ``.vsdx`` is not supported.

Project
-------

Source and issues: https://github.com/firmfooting/vsdxkit

Descended from: https://github.com/dave-howard/vsdx

* :ref:`genindex`
