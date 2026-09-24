vsdxkit documentation
=====================

``vsdxkit`` creates, edits and analyses Microsoft Visio ``.vsdx`` files with
Python. The distribution and the import package are both called ``vsdxkit``.
Microsoft Visio is not required at runtime.

.. note::

   **The 1.0 API.** These pages describe the 1.0 API. Code written for 0.x
   will not run unchanged: :doc:`migration-1.0` gives the replacement for
   every 0.x name 1.0 removes. Pin ``vsdxkit<1`` to stay on the 0.x names.

The library works on the XML parts inside an existing Visio package. It can
query and edit shapes, create common flowchart shapes, create and retarget
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
   migration-1.0

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
as ``.vsdx`` (or a plain drawing as ``.vsdm``) raises
``vsdxkit.errors.InvalidOperationError`` rather than writing a file Visio reports as
corrupt. Stripping macros to convert a ``.vsdm`` into a ``.vsdx`` is not
supported.

Project
-------

Source and issues: https://github.com/firmfooting/vsdxkit

Descended from: https://github.com/dave-howard/vsdx

* :ref:`genindex`
