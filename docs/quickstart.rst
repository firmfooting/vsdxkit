Quick start
===========

Installation
------------

**As of 2026-09-13 there is no release on PyPI.** The first release was
withdrawn after a security defect and cannot be republished, so
``pip install vsdxkit`` finds no versions until the next one lands. The `PyPI
project page <https://pypi.org/project/vsdxkit/>`_ shows the current state.

Install from GitHub in the meantime:

.. code-block:: console

   python -m pip install "vsdxkit @ git+https://github.com/firmfooting/vsdxkit.git"

That tracks ``main``, so pin a commit if you need a reproducible install. Once
there is a release on the index, install it with ``pip install vsdxkit``.

Import each name from the module that defines it; the package root re-exports
nothing:

.. code-block:: python

   from vsdxkit.vsdxfile import VisioFile

Python 3.10–3.14 is supported.

Open a document
---------------

Open a document with :class:`vsdxkit.vsdxfile.VisioFile`. Opening reads the
whole package into memory and holds no file, so there is nothing to close.

.. code-block:: python

   from vsdxkit.vsdxfile import VisioFile

   vis = VisioFile("diagram.vsdx")
   page = vis.pages[0]
   print(page.name)

Find and edit a shape
---------------------

Finder methods return ``None`` when there is no match. Check the result before
editing it.

.. code-block:: python

   vis = VisioFile("diagram.vsdx")
   page = vis.pages[0]
   shape = page.shapes.by_text("Draft")

   if shape is not None:
       shape.text = "Approved"

   vis.save_vsdx("approved.vsdx")

Save in place
-------------

Call :meth:`vsdxkit.vsdxfile.VisioFile.save_vsdx` without a filename to replace
the source file. Nothing is saved until you call it.

.. code-block:: python

   vis = VisioFile("diagram.vsdx")
   vis.pages[0].name = "Current state"
   vis.save_vsdx()

Development install
-------------------

.. code-block:: console

   git clone https://github.com/firmfooting/vsdxkit.git
   cd vsdxkit
   uv sync --locked --group docs
   uv run --no-sync python -m pytest tests -q
   uv run --no-sync ruff check src tests tools
   uv run --no-sync ruff format --check src tests tools
   uv run --no-sync pyrefly check src/vsdxkit --min-severity warn --output-format min-text
   uv run --no-sync sphinx-build -W --keep-going -b html docs docs/_build/html

The ``docs`` group pins Sphinx, which requires Python 3.12 or later. Drop
``--group docs`` from the sync to work on the library itself under Python 3.10
or 3.11.
