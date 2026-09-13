Quick start
===========

Installation
------------

``vsdxkit`` is not yet published on PyPI. Install the current GitHub version:

.. code-block:: console

   python -m pip install "vsdxkit @ git+https://github.com/firmfooting/vsdxkit.git"

The distribution name and import name differ deliberately:

.. code-block:: python

   from vsdx import VisioFile

Python 3.10–3.14 is supported.

Open a document
---------------

Use :class:`vsdx.vsdxfile.VisioFile` as a context manager. This closes the
package and any temporary resources when the block exits.

.. code-block:: python

   from vsdx import VisioFile

   with VisioFile("diagram.vsdx") as vis:
       page = vis.pages[0]
       print(page.name)

Find and edit a shape
---------------------

Finder methods return ``None`` when there is no match. Check the result before
editing it.

.. code-block:: python

   with VisioFile("diagram.vsdx") as vis:
       page = vis.pages[0]
       shape = page.find_shape_by_text("Draft")

       if shape is not None:
           shape.text = "Approved"

       vis.save_vsdx("approved.vsdx")

Save in place
-------------

Call :meth:`vsdx.vsdxfile.VisioFile.save_vsdx` without a filename to replace
the source file. Saving remains explicit; leaving the context manager does not
save automatically.

.. code-block:: python

   with VisioFile("diagram.vsdx") as vis:
       vis.pages[0].name = "Current state"
       vis.save_vsdx()

Development install
-------------------

.. code-block:: console

   git clone https://github.com/firmfooting/vsdxkit.git
   cd vsdxkit
   uv sync --locked --group docs
   uv run --no-sync python -m pytest tests -q
   uv run --no-sync ruff check vsdx tests/test_imports.py tests/test_shape_coordinates.py
   uv run --no-sync ruff format --check vsdx tests/test_imports.py tests/test_shape_coordinates.py
   uv run --no-sync pyrefly check vsdx --min-severity warn --output-format min-text
   uv run --no-sync sphinx-build -W --keep-going -b html docs docs/_build/html

The ``docs`` group pins Sphinx, which requires Python 3.12 or later. Drop
``--group docs`` from the sync to work on the library itself under Python 3.10
or 3.11.
