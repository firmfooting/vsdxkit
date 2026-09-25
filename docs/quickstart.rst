Quick start
===========

Installation
------------

Python 3.10–3.14 is supported on Linux, Windows and macOS.

These pages describe the 1.0 API, which ``main`` carries. It is not on PyPI
yet, so install it from GitHub:

.. code-block:: console

   python -m pip install "vsdxkit @ git+https://github.com/firmfooting/vsdxkit.git"

That tracks ``main``, so pin a commit if you need a reproducible install. Until
1.0 is released, an install from ``main`` reports its version as 0.8.0, because
the version is only bumped when a release is cut.

``pip install vsdxkit`` installs 0.8.0, the latest release on `PyPI
<https://pypi.org/project/vsdxkit/>`_, published on 2026-09-13. It has the 0.x
API: it imports as ``vsdx``, its document class is ``VisioFile``, and the
examples on these pages do not run on it. Pin ``vsdxkit<1`` to stay on the 0.x
names once 1.0 is released, and read :doc:`migration-1.0` when you move.

0.7.0 was withdrawn from PyPI because its Jinja rendering could run code from a
crafted document. 0.7.1 and later render templates in Jinja's sandbox.

Import each name from the module that defines it; the package root re-exports
nothing:

.. code-block:: python

   from vsdxkit.document import Document

Open a document
---------------

Open a document with :class:`vsdxkit.document.Document`. Opening reads the
whole package into memory and holds no file, so there is nothing to close.

.. code-block:: python

   from vsdxkit.document import Document

   vis = Document.open("diagram.vsdx")
   page = vis.pages[0]
   print(page.name)

Find and edit a shape
---------------------

A ``by_*`` lookup returns ``None`` when nothing matches, so check the result
before editing it. A ``require_*`` lookup raises
:class:`vsdxkit.errors.NotFoundError` instead.

.. code-block:: python

   vis = Document.open("diagram.vsdx")
   page = vis.pages[0]
   shape = page.shapes.by_text("Draft")

   if shape is not None:
       shape.text = "Approved"

   vis.save("approved.vsdx")

Save in place
-------------

Call :meth:`vsdxkit.document.Document.save` without a filename to replace
the source file. Nothing is saved until you call it.

.. code-block:: python

   vis = Document.open("diagram.vsdx")
   vis.pages[0].name = "Current state"
   vis.save()

Where next
----------

* :doc:`find_shape` to select pages and look shapes up.
* :doc:`create_connect` to add shapes and connectors.
* :doc:`swimlanes` to extend a cross-functional flowchart.
* :doc:`templating` to fill a template with data.

Development install
-------------------

To work on vsdxkit itself, follow the development environment and checks in
`CONTRIBUTING.md
<https://github.com/firmfooting/vsdxkit/blob/main/CONTRIBUTING.md>`_.
