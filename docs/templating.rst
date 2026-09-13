Jinja templates
===============

``vsdxkit`` can render Jinja expressions stored in shape text and page names.
The source remains a normal ``.vsdx`` file, so a designer can maintain its
layout in Visio while Python supplies the data.

Render ordinary expressions
---------------------------

.. code-block:: python

   from vsdx import VisioFile

   context = {
       "project": "Ward refurbishment",
       "owner": "Facilities",
   }

   with VisioFile("template.vsdx") as vis:
       vis.jinja_render_vsdx(context)
       vis.save_vsdx("rendered.vsdx")

A shape containing ``{{ project }}`` becomes ``Ward refurbishment`` in the
saved document.

Loops and conditional groups
----------------------------

Visio XML does not provide a linear text stream around whole shapes. The
library therefore uses two diagram-specific conventions in addition to normal
Jinja expressions:

* a group shape beginning with a Jinja ``for`` statement is copied once per
  item and closed with an injected ``endfor``;
* a group shape or page containing ``{% showif expression %}`` is included only
  when the expression is true.

Nested loops and ``showif`` combinations are supported. Treat the tests as the
executable reference for the exact shape arrangement:

* ``tests/test_jinja.py``
* ``tests/test_jinja_loop.vsdx``
* ``tests/test_jinja_inner_loop.vsdx``
* ``tests/test_jinja_loop_showif.vsdx``
* ``tests/test_jinja_page_showif.vsdx``

Self assignments
----------------

Templates can assign selected geometry values on the current shape, including
``x`` and ``y``. For example, a repeated shape may contain:

.. code-block:: jinja

   {% set self.x = 1.5 + loop.index0 * 2.0 %}

Rendering runs in Jinja's sandboxed environment, because the templates come out
of the document rather than from the caller. Loops, conditionals, filters and
arithmetic all work; reaching through an object's attributes into the
interpreter does not, and raises ``jinja2.exceptions.SecurityError``.

The sandbox is a bound on what a malicious document can do, not a licence to
render anything. A template can still consume memory and time, and it sees
whatever you put in the context — so do not pass secrets to
``jinja_render_vsdx()`` alongside a document you do not trust.
