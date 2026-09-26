vsdxkit documentation
=====================

``vsdxkit`` creates, edits and analyses Microsoft Visio ``.vsdx`` files with
Python. Microsoft Visio is not required at runtime. The distribution and the
import package are both called ``vsdxkit``.

The library works on the XML parts inside an existing Visio package. It can
query and edit shapes, create common flowchart shapes, create and retarget
connectors, extend existing cross-functional flowcharts, copy pages and render
Jinja-backed templates.

.. note::

   **The 1.0 API.** These pages describe the 1.0 API, which ``main`` carries
   and which is not yet released. Code written for 0.x will not run
   unchanged: :doc:`migration-1.0` gives the replacement for every 0.x name
   1.0 removes. Pin ``vsdxkit<1`` to stay on the 0.x names.

Install
-------

The 1.0 API is not on PyPI yet. Install it from GitHub:

.. code-block:: console

   python -m pip install "vsdxkit @ git+https://github.com/firmfooting/vsdxkit.git"

``pip install vsdxkit`` installs 0.8.0, the latest release, which has the 0.x
API and imports as ``vsdx``. :doc:`quickstart` says more about both.

Where to go next
----------------

* Install, open a document and save it: :doc:`quickstart`.
* Select, add, copy and delete pages, and find shapes: :doc:`find_shape`.
* Create, connect, retarget and delete shapes: :doc:`create_connect`.
* Extend a cross-functional flowchart: :doc:`swimlanes`.
* Fill a Visio template with data: :doc:`templating`.
* Look up a class or an error: the :doc:`API reference <api/index>`.
* Move code from 0.x to 1.0: :doc:`migration-1.0`.

.. toctree::
   :maxdepth: 2
   :caption: Guides
   :hidden:

   quickstart
   create_connect
   swimlanes
   templating
   find_shape
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

Contributing: `CONTRIBUTING.md
<https://github.com/firmfooting/vsdxkit/blob/main/CONTRIBUTING.md>`_

Descended from: https://github.com/dave-howard/vsdx

* :ref:`genindex`
