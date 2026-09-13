import os
from datetime import datetime

import pytest

from vsdxkit import (
    Shape,
    VisioFile,
)


@pytest.mark.parametrize(
    ("filename", "context"),
    [
        ("test_jinja.vsdx", {"date": datetime.now(), "scenario": "Scenario One", "x": 2, "y": 2}),
        ("test_jinja.vsdx", {"date": datetime.now(), "scenario": "Scenario Two", "x": 2, "y": 2}),
        ("test_jinja.vsdx", {"date": datetime.now(), "scenario": "Scenario Three", "x": 2, "y": 2}),
    ],
)
def test_basic_jinja(filename: str, context: dict, tmp_path, basedir):

    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_basic_jinja.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[0]

        # each key string in context dict will be replaced with value, record against shape Ids for validation
        shape_id_values = dict()
        for k, v in context.items():
            shape_id = page.find_shape_by_text(k).ID
            shape_id_values[shape_id] = v
        vis.jinja_render_vsdx(context=context)
        vis.save_vsdx(out_file)

    # open file and validate each shape id has expected text
    with VisioFile(out_file) as vis:
        page = vis.pages[0]
        for shape_id, text in shape_id_values.items():
            if type(text) is str:
                print(f"Testing that shape {shape_id} has text '{text}' in: {page.find_shape_by_id(shape_id).text}")
                assert str(text) in page.find_shape_by_id(shape_id).text


@pytest.mark.parametrize(
    ("filename", "context", "shape_count"),
    [
        ("test_jinja.vsdx", {"date": datetime.now(), "scenario": "One", "x": 0, "y": 2}, 1),
        ("test_jinja.vsdx", {"date": datetime.now(), "scenario": "Two", "x": 5, "y": 2}, 2),
        ("test_jinja.vsdx", {"date": datetime.now(), "scenario": "Three", "x": 20, "y": 2}, 3),
    ],
)
def test_jinja_if(filename: str, context: dict, shape_count: int, tmp_path, basedir):

    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_jinja_if_{context['scenario']}.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        vis.jinja_render_vsdx(context=context)
        vis.save_vsdx(out_file)

    # open file and validate each shape id has expected text
    with VisioFile(out_file) as vis:
        page = vis.pages[1]  # second page has the shapes with if statements
        count = len(page.child_shapes)
        print(f"expected {shape_count} and found {count}")
        assert count == shape_count


@pytest.mark.parametrize(
    ("filename", "context"),
    [
        ("test_jinja.vsdx", {"x": 2, "y": 2}),
        ("test_jinja.vsdx", {"x": 3, "y": 4}),
        ("test_jinja.vsdx", {"x": 12, "y": 9}),
    ],
)
def test_jinja_calc(filename: str, context: dict, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_jinja_calc.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        vis.jinja_render_vsdx(context=context)
        vis.save_vsdx(out_file)

    # open file and validate each shape id has expected text
    with VisioFile(out_file) as vis:
        page = vis.pages[0]
        # check a shape exists with product of x and y values
        x_y = str(context["x"] * context["y"])
        assert page.find_shape_by_text(x_y)


@pytest.mark.parametrize(
    ("filename", "context"),
    [
        ("test_jinja_loop.vsdx", {"date": datetime.now(), "scenario": "Scenario One", "test_list": [1, 2, 3]}),
        ("test_jinja_loop.vsdx", {"date": datetime.now(), "scenario": "Scenario Two", "test_list": ["One", "Two", "Three"]}),
        ("test_jinja_loop.vsdx", {"date": datetime.now(), "scenario": "Scenario Three", "test_list": [1, 2, 3, 4, 5, 6]}),
    ],
)
def test_basic_jinja_loop(filename: str, context: dict, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_{context['scenario']}_test_basic_jinja_loop.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[0]

        # each key string in context dict will be replaced with value, record against shape Ids for validation
        shape_id_values = dict()
        for k, v in context.items():
            shape_id = page.find_shape_by_text(k).ID
            shape_id_values[shape_id] = v
        vis.jinja_render_vsdx(context=context)
        vis.save_vsdx(out_file)

    # open file and validate each shape id has expected text, and that a shape exists with each loop value
    with VisioFile(out_file) as vis:
        page = vis.pages[0]
        for shape_id, text in shape_id_values.items():
            if type(text) is str:
                print(f"Testing that shape {shape_id} has text '{text}' in: {page.find_shape_by_id(shape_id).text}")
                assert str(text) in page.find_shape_by_id(shape_id).text
            if type(text) is list:
                for item in text:
                    print(f"Testing that shape with text '{item}' exists")
                    assert page.find_shape_by_text(str(item))


@pytest.mark.parametrize(
    ("filename", "context"),
    [
        ("test_jinja_inner_loop.vsdx", {"test_list": [[1, 2, 3], [1, 2, 3], [1, 2, 3]]}),
        ("test_jinja_inner_loop.vsdx", {"test_list": ["One", "Two", "Three"]}),
    ],
)
def test_jinja_inner_loop(filename: str, context: dict, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_jinja_inner_loop.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        vis.jinja_render_vsdx(context=context)
        vis.save_vsdx(out_file)

    # open file and validate each shape id has expected text, and that a shape exists with each loop value
    test_list = context["test_list"]
    with VisioFile(out_file) as vis:
        page = vis.pages[0]
        for o in test_list:
            for p in o:
                print(f"p={p}")
                s = page.find_shape_by_text(str(p))
                assert s


@pytest.mark.parametrize(
    ("filename", "out_name", "context"),
    [
        ("test_jinja_loop_showif.vsdx", "1234", {"test_list": [1, 2, 3, 4]}),
        ("test_jinja_loop_showif.vsdx", "3456", {"test_list": [3, 4, 5, 6]}),
    ],
)
def test_jinja_loop_showif(filename: str, out_name: str, context: dict, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}{out_name}.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        vis.jinja_render_vsdx(context=context)
        vis.save_vsdx(out_file)

    with VisioFile(out_file) as vis:
        page = vis.pages[0]
        for o in context["test_list"]:
            s = page.find_shape_by_text(f"In this instance, o={o}")
            # test that {% show if o > 2 %} has worked
            print(f"for {o} found {s}")
            if o > 2:
                assert s  # check that shape is found (not removed by showif)
            else:
                assert not s  # check that shape is not found (has been removed by showif)


@pytest.mark.parametrize(
    ("filename", "context", "shape_id", "expected_x", "expected_text"),
    [
        ("test_jinja_self_refs.vsdx", {"n": 1}, "1", 2.0, "This text should remain  and x should be 2.0"),
        ("test_jinja_self_refs.vsdx", {"n": 2}, "2", 4.0, "This shape sets x to n * 2"),
        ("test_jinja_self_refs.vsdx", {"n": 1}, "3", 1.0, "This shape sets x to 1 if n else 2"),
        ("test_jinja_self_refs.vsdx", {"n": 0}, "3", 2.0, "This shape sets x to 1 if n else 2"),
    ],
)
def test_jinja_self_refs(filename: str, context: dict, shape_id, expected_x, expected_text, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_jinja_self_refs.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[0]  # type: Page
        # there should be one shape on page 0
        shape = page.find_shape_by_id(shape_id)  # type: Shape
        print(f"DEBUG: ID={shape.ID} shape.text={shape.text}")
        print(f"DEBUG: ID={shape.ID} shape.x={shape.x}")
        vis.jinja_render_vsdx(context=context)
        vis.save_vsdx(out_file)

    # open file and check shape has moved
    with VisioFile(out_file) as vis:
        page = vis.pages[0]
        shape = page.find_shape_by_id(shape_id)  # type: Shape
        print(f"DEBUG: ID={shape.ID} shape.text='{shape.text}' expected='{expected_text}'")
        print(f"DEBUG: ID={shape.ID} shape.x={shape.x}")
        assert shape.x == expected_x
        assert shape.text == expected_text


@pytest.mark.parametrize(
    ("filename", "context", "shape_id", "expected_y", "expected_text"),
    [
        ("test_jinja_self_refs.vsdx", {"n": 2}, "4", 10.12368731806121, "This shape should move down by 1.0"),
        ("test_jinja_self_refs.vsdx", {"n": 1}, "5", 8.726049539918966, "This shape should move down by n"),
        ("test_jinja_self_refs.vsdx", {"n": 2}, "5", 7.726049539918966, "This shape should move down by n"),
    ],
)
def test_jinja_self_ref_calculations(filename: str, context: dict, shape_id, expected_y, expected_text, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_jinja_self_ref_calcs.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[0]  # type: Page
        # there should be one shape on page 0
        shape = page.find_shape_by_id(shape_id)  # type: Shape
        if shape:
            print(f"DEBUG: ID={shape.ID} shape.text={shape.text}")
            print(f"DEBUG: ID={shape.ID} shape.y={shape.y}")
        vis.jinja_render_vsdx(context=context)
        vis.save_vsdx(out_file)

    # open file and check shape has moved
    with VisioFile(out_file) as vis:
        page = vis.pages[0]
        shape = page.find_shape_by_id(shape_id)  # type: Shape
        print(f"DEBUG: ID={shape.ID} shape.text='{shape.text}' expected='{expected_text}'")
        print(f"DEBUG: ID={shape.ID} shape.x={shape.y}")
        assert shape.y == expected_y
        assert shape.text == expected_text


@pytest.mark.parametrize(
    ("filename", "context", "expected_page_count", "expected_page_names"),
    [
        ("test_jinja_page_showif.vsdx", {"show": True}, 2, ["Normal Page", "Page2"]),
        ("test_jinja_page_showif.vsdx", {"show": 1}, 2, ["Normal Page", "Page2"]),
        ("test_jinja_page_showif.vsdx", {"show": "true"}, 2, ["Normal Page", "Page2"]),
        ("test_jinja_page_showif.vsdx", {"show": 4.0}, 2, ["Normal Page", "Page2"]),
        ("test_jinja_page_showif.vsdx", {"show": False}, 2, ["Normal Page", "Page3"]),
        ("test_jinja_page_showif.vsdx", {"show": []}, 2, ["Normal Page", "Page3"]),
        ("test_jinja_page_showif.vsdx", {"show": {}}, 2, ["Normal Page", "Page3"]),
    ],
)
def test_jinja_page_showif(filename: str, context: dict, expected_page_count, expected_page_names, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_show_{context['show']}.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        print(f"len(vis.pages)={len(vis.pages)} context={context}")
        print("BEFORE", [(p.index_num, p.name) for p in vis.pages])
        vis.jinja_render_vsdx(context=context)
        print("AFTER", [(p.index_num, p.name) for p in vis.pages])
        vis.save_vsdx(out_file)

    # open file and check shape has moved
    with VisioFile(out_file) as vis:
        page_names = []
        for p in vis.pages:  # type: Page
            print(f"page:{p.name}")
            page_names.append(p.name)
        assert len(vis.pages) == expected_page_count
        assert page_names == expected_page_names


# --------------------------------------------------------------------------
# `{% set self.x = ... %}` reference resolution (#351)
# --------------------------------------------------------------------------
#
# Every statement in `test_jinja_self_refs.vsdx` uses a one-character attribute
# name, and for one character "the first character of the name" and "the name"
# are the same string. That coincidence is what let the resolver read
# `self_ref[0]` off a string for so long. These tests supply the statement
# themselves rather than adding fixture shapes, so each fault is reached by the
# shortest thing that reaches it.


def _render_one_self_statement(path: str, shape_id: str, statement: str, context: dict) -> Shape:
    """Put `statement` on a real shape, run the self-ref pass, return the shape."""
    with VisioFile(path) as vis:
        shape = vis.pages[0].find_shape_by_id(shape_id)
        shape.text = statement
        VisioFile.jinja_set_selfs(shape, context)
        return shape


def test_a_self_reference_to_a_multi_character_attribute_reads_the_whole_name(basedir):
    """`self.width` must read `width`, not `w`.

    Fails if the resolver goes back to indexing a `findall` result, which
    returns strings rather than the tuples the old annotation claimed.
    """
    path = os.path.join(basedir, "test_jinja_self_refs.vsdx")
    with VisioFile(path) as vis:
        expected = vis.pages[0].find_shape_by_id("4").width
    shape = _render_one_self_statement(path, "4", "{% set self.y=self.width %}", {})
    assert shape.y == expected


def test_every_self_reference_in_one_expression_is_resolved(basedir):
    """`self.x+self.y` has two references, and the greedy `(.*)` only ever found one.

    Fails if the name pattern stops being bounded to an identifier: an
    unresolved `self.y` is left in the string as literal text, and Jinja then
    resolves `self` to its own `TemplateReference`.
    """
    path = os.path.join(basedir, "test_jinja_self_refs.vsdx")
    with VisioFile(path) as vis:
        start = vis.pages[0].find_shape_by_id("4")
        expected = start.x + start.y
    shape = _render_one_self_statement(path, "4", "{% set self.x=self.x+self.y %}", {})
    assert shape.x == pytest.approx(expected)


def test_a_self_reference_to_an_unknown_attribute_names_the_statement(basedir):
    """The failure has to say which statement is wrong, in the document's own terms.

    A bare `AttributeError: 'Shape' object has no attribute 'nope'` escaping a
    template render names something the document never mentioned and points at
    no part of it.
    """
    path = os.path.join(basedir, "test_jinja_self_refs.vsdx")
    with pytest.raises(ValueError) as failure:
        _render_one_self_statement(path, "4", "{% set self.x=self.nope %}", {})
    message = str(failure.value)
    assert "self.nope" in message
    assert "{% set self.x=self.nope %}" in message


class _SelfRefShape:
    """The smallest thing `jinja_set_selfs` needs: attributes, and text.

    Stands in for a `Shape` only where the real one cannot express the case.
    `Shape` today has no pair of *numeric* attributes where one name is a prefix
    of the other, so the substitution hazard below is unreachable through it --
    `loc_x`/`loc_x_f` are the closest pair and the second is a formula string.
    The parser is what is under test, and it reaches the parser exactly.
    """

    def __init__(self, text: str, **attributes: float) -> None:
        self.text = text
        for name, value in attributes.items():
            setattr(self, name, value)

    @property
    def x(self) -> float:
        return self._x

    @x.setter
    def x(self, value: float | str) -> None:
        # `Shape.x` parses what the render produced; a stand-in that stored the
        # string would make these tests agree with a resolver that emitted
        # anything at all.
        self._x = float(value)


def test_one_reference_is_not_substituted_into_a_longer_one():
    """`self.ab` must not be rewritten inside `self.abc`.

    `re.findall` yields names in the order they appear, so substituting them
    one at a time turns `self.ab + self.abc` into `<value>` followed by the
    orphan text `c`. Fails if the substitution goes back to a sequence of
    `str.replace` calls instead of a single pass.
    """
    shape = _SelfRefShape("{% set self.x=self.ab+self.abc %}", ab=1.0, abc=20.0, x=0.0)
    VisioFile.jinja_set_selfs(shape, {})
    assert shape.x == pytest.approx(21.0)


def test_spaces_around_the_equals_sign_do_not_drop_the_statement():
    """`{% set self.x  =  2.0 %}` has to assign, not vanish.

    The statement pattern allowed a single optional space either side, while the
    pattern that strips the statement out of the text allowed any. So a second
    space meant the assignment was skipped and the statement removed anyway --
    a template that silently did nothing.
    """
    shape = _SelfRefShape("keep me {% set self.x  =  2.0 %}", x=0.0)
    VisioFile.jinja_set_selfs(shape, {})
    assert shape.x == pytest.approx(2.0)
    assert shape.text == "keep me "
