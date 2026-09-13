"""Jinja expressions in a document must not reach the interpreter.

`jinja_render_vsdx()` renders text taken from the .vsdx being processed. On
Jinja's default environment that text is executable: a document can reach
`__init__.__globals__` and from there the `os` module. A caller rendering a
document they did not write would be handing it a shell.
"""

import os
import shutil

import pytest
from jinja2.exceptions import SecurityError

from vsdxkit import VisioFile

FIXTURES = os.path.dirname(os.path.realpath(__file__))

# Reaches os.popen through a builtin's globals on an unsandboxed environment.
# The payload only echoes a marker: the point is whether it evaluates at all.
ESCAPE = "{{ cycler.__init__.__globals__.os.popen('echo reached').read() }}"


def _copy(tmp_path, name="test1.vsdx"):
    destination = os.path.join(str(tmp_path), name)
    shutil.copy(os.path.join(FIXTURES, name), destination)
    return destination


def test_document_text_cannot_reach_the_interpreter(tmp_path):
    """A sandbox escape in shape text is refused, not executed."""
    with VisioFile(_copy(tmp_path)) as vis:
        vis.pages[0].child_shapes[0].text = ESCAPE
        with pytest.raises(SecurityError):
            vis.jinja_render_vsdx(context={"safe": "value"})


def test_a_shape_name_cannot_reach_the_interpreter(tmp_path):
    """The same applies to the per-shape render path, not only the page one."""
    with VisioFile(_copy(tmp_path)) as vis:
        page = vis.pages[0]
        shape = page.child_shapes[0]
        shape.text = f"{{% if {ESCAPE[3:-3]} %}}x{{% endif %}}"
        with pytest.raises(SecurityError):
            vis.jinja_render_vsdx(context={"safe": "value"})


def test_ordinary_templating_still_works(tmp_path):
    """The sandbox must not cost the templating this library exists to do."""
    out = os.path.join(str(tmp_path), "rendered.vsdx")
    with VisioFile(_copy(tmp_path)) as vis:
        vis.pages[0].child_shapes[0].text = "{{ project }} has {{ 1.0 + 2.4 * 3 }}"
        vis.jinja_render_vsdx(context={"project": "Ward refurbishment"})
        vis.save_vsdx(out)

    with VisioFile(out) as vis:
        assert vis.pages[0].child_shapes[0].text.startswith("Ward refurbishment has 8.2")
