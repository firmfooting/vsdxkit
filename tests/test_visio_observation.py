"""Tests for the Visio differential oracle's comparison layer.

These run without Visio. The point of the harness is that judgment lives in
Python where it can be tested; this file is what makes that claim true.
"""

import json

import pytest
from helpers.visio_observation import (
    PLACEMENT_CELLS,
    SCHEMA_VERSION,
    CellObservation,
    ConnectObservation,
    Observation,
    PageObservation,
    ShapeObservation,
    _com_cells,
    _package_cell,
    compare,
    observation_from_com_json,
    observation_from_package,
)


def _page(index=1, name="Page-1", shapes=(), connects=()):
    return PageObservation(index=index, name=name, shapes=tuple(shapes), connects=tuple(connects))


def _shape(shape_id, parent_id=None, name="", cells=()):
    return ShapeObservation(id=shape_id, parent_id=parent_id, name=name, cells=tuple(cells))


def _cell(name, constant, result=None):
    """A cell whose formula is the constant itself, as either side would state it."""
    return CellObservation(name=name, formula=repr(constant), constant=constant, result=result)


def _cell_formula(name, formula, result=None):
    return CellObservation(name=name, formula=formula, constant=None, result=result)


def _com(formula, result):
    """One cell as the COM reader builds it, bypassing the JSON envelope."""
    return _com_cells([{"name": "PinX", "formula": formula, "result": result}])[0]


def _package(formula, value):
    """One cell as the package reader builds it, from a formula and its cached `V`."""
    return _package_cell("PinX", formula, value)


def test_identical_observations_have_no_differences():
    one = Observation(label="package", pages=(_page(shapes=(_shape(1), _shape(2))),))
    other = Observation(label="visio", pages=(_page(shapes=(_shape(1), _shape(2))),))
    assert compare(one, other) == ()


def test_a_shape_the_second_side_never_reports_is_a_difference():
    """Visio silently drops a shape: the file loses data and nothing says so."""
    package = Observation(label="package", pages=(_page(shapes=(_shape(1), _shape(2))),))
    visio = Observation(label="visio", pages=(_page(shapes=(_shape(1),)),))

    differences = compare(package, visio)

    assert [d.kind for d in differences] == ["shape-missing"]
    assert differences[0].locus == "page 1 shape 2"
    # the message has to name which side is short, or the reader cannot tell a
    # dropped shape from an invented one
    assert "package" in differences[0].detail and "visio" in differences[0].detail


def test_a_shape_name_alone_is_not_a_difference():
    """Visio synthesises a name for a shape the package never named.

    `Sheet.1` is not stored anywhere in the file; Visio derives it. Comparing
    names would report a difference on almost every shape and bury the real
    ones, so the name is carried for the failure message and nothing else.
    """
    package = Observation(label="package", pages=(_page(shapes=(_shape(1, name="Rounded"),)),))
    visio = Observation(label="visio", pages=(_page(shapes=(_shape(1, name="Sheet.1"),)),))

    assert compare(package, visio) == ()


def test_a_shape_that_left_its_group_is_a_difference_not_a_match():
    """Ids alone would call this file identical; the shape moved out of a group."""
    package = Observation(label="package", pages=(_page(shapes=(_shape(5), _shape(6, parent_id=5))),))
    visio = Observation(label="visio", pages=(_page(shapes=(_shape(5), _shape(6, parent_id=None))),))

    differences = compare(package, visio)

    assert [d.kind for d in differences] == ["shape-parent"]
    assert "group 5" in differences[0].detail and "the page" in differences[0].detail


def test_glue_is_compared_as_a_set_not_a_sequence():
    """Visio does not preserve the order of its Connects collection."""
    first = ConnectObservation(9, "BeginX", 5, "PinX")
    second = ConnectObservation(9, "EndX", 6, "PinX")
    package = Observation(label="package", pages=(_page(connects=(first, second)),))
    visio = Observation(label="visio", pages=(_page(connects=(second, first)),))

    assert compare(package, visio) == ()


def test_glue_that_only_one_side_reports_is_a_difference():
    package = Observation(label="package", pages=(_page(connects=(ConnectObservation(9, "BeginX", 5, "PinX"),)),))
    visio = Observation(label="visio", pages=(_page(),))

    differences = compare(package, visio)

    assert [d.kind for d in differences] == ["connect-missing"]
    assert "package glues shape 9 cell BeginX to shape 5 cell PinX" in differences[0].detail


def test_a_page_only_one_side_reports_is_a_difference():
    package = Observation(label="package", pages=(_page(index=1), _page(index=2, name="Page-2")))
    visio = Observation(label="visio", pages=(_page(index=1),))

    differences = compare(package, visio)

    assert [d.kind for d in differences] == ["page-missing"]
    assert differences[0].locus == "page 2"


def test_an_observation_written_under_another_schema_is_refused():
    """A recorded observation outlives the code that reads it.

    Silently misreading an old recording would turn the harness into a source of
    false confidence, which is worse than having no harness: the run goes green
    on a comparison that was never made.
    """
    with pytest.raises(ValueError, match="schema"):
        observation_from_com_json(json.dumps({"schema": SCHEMA_VERSION + 1, "pages": []}))


class TestReadingARealPackage:
    def test_it_finds_the_pages_in_the_order_visio_numbers_them(self, basedir):
        observation = observation_from_package(f"{basedir}/test1.vsdx")

        assert [page.index for page in observation.pages] == list(range(1, len(observation.pages) + 1))
        assert all(page.name for page in observation.pages)

    def test_it_descends_into_groups(self, basedir):
        observation = observation_from_package(f"{basedir}/test10_nested_shapes.vsdx")

        shapes = [shape for page in observation.pages for shape in page.shapes]
        assert any(shape.parent_id is not None for shape in shapes), "no group members found in a nested fixture"

    def test_it_reads_glue_records(self, basedir):
        observation = observation_from_package(f"{basedir}/test4_connectors.vsdx")

        connects = [connect for page in observation.pages for connect in page.connects]
        assert connects, "no glue found in a connector fixture"
        assert all(connect.from_cell for connect in connects)


def test_a_duplicated_id_is_reported_when_one_of_the_two_is_inside_a_group():
    """The duplicate need not be a pair of siblings.

    Shapes are ordered by id and then by whatever distinguishes two that share
    one, and a group member sorts against a top-level shape whose parent is
    None. Getting that wrong does not produce a wrong answer, it produces a
    TypeError out of the reader - so the harness crashes on precisely the file
    it was built to describe.
    """
    package = Observation(
        label="package",
        pages=(_page(shapes=(_shape(2, parent_id=None), _shape(2, parent_id=5), _shape(5))),),
    )
    visio = Observation(label="visio", pages=(_page(shapes=(_shape(2), _shape(5))),))

    differences = compare(package, visio)

    assert [d.kind for d in differences] == ["shape-duplicate-id"]


def test_a_page_declaring_one_id_twice_is_reported_even_when_the_sides_agree():
    """Duplicate ids are what this harness was built for, so they get their own name.

    Shapes are joined between the two sides by id, so a page using an id twice
    makes the join ambiguous: Visio keeps one of them and discards the other
    without a word, and a comparison keyed on ids sees two matching sets. The
    only honest answer is to say the question cannot be asked of this file.
    """
    package = Observation(label="package", pages=(_page(shapes=(_shape(1), _shape(2), _shape(2))),))
    visio = Observation(label="visio", pages=(_page(shapes=(_shape(1), _shape(2))),))

    differences = compare(package, visio)

    assert "shape-duplicate-id" in [d.kind for d in differences]
    duplicate = next(d for d in differences if d.kind == "shape-duplicate-id")
    assert duplicate.locus == "page 1 shape 2"
    assert "package" in duplicate.detail


@pytest.mark.allow_invalid_package  # the package is broken on purpose
def test_reading_a_package_whose_group_member_collides_with_a_top_level_id(tmp_path, basedir):
    """The same collision, through the reader that has to sort real shapes."""
    import zipfile

    source = f"{basedir}/test10_nested_shapes.vsdx"
    broken = str(tmp_path / "collide.vsdx")
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(broken, "w") as rewritten:
        for entry in original.infolist():
            data = original.read(entry.filename)
            if entry.filename == "visio/pages/page1.xml":
                # shape 7 is top level and shape 1 sits two groups deep
                data = data.decode("utf-8").replace("<Shape ID='1'", "<Shape ID='7'", 1).encode("utf-8")
            rewritten.writestr(entry, data)

    observation = observation_from_package(broken)

    assert any(d.kind == "shape-duplicate-id" for d in compare(observation, observation))


def test_the_same_glue_record_written_twice_is_reported():
    """Comparing glue as a plain set would lose the repetition.

    A writer that emits one `<Connect>` twice produces a file whose glue Visio
    keeps once. Both sides then hold the same distinct records, and a set
    comparison calls them equal - the same silent join that duplicate shape ids
    get a guard for.
    """
    connect = ConnectObservation(9, "BeginX", 5, "PinX")
    package = Observation(label="package", pages=(_page(connects=(connect, connect)),))
    visio = Observation(label="visio", pages=(_page(connects=(connect,)),))

    differences = compare(package, visio)

    assert [d.kind for d in differences] == ["connect-duplicate"]
    assert "twice" in differences[0].detail


@pytest.mark.allow_invalid_package  # the package is broken on purpose
def test_a_page_whose_relationship_does_not_resolve_keeps_its_position(tmp_path, basedir):
    """A page that cannot be read must not renumber the pages after it.

    Dropping it would shift every later page down one, so page 3 would be
    compared against page 2 and the result is a pile of shape differences
    pointing at the wrong page. The unreadable page is reported as itself.
    """
    import zipfile

    source = f"{basedir}/test4_connectors.vsdx"
    broken = str(tmp_path / "badrel.vsdx")
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(broken, "w") as rewritten:
        for entry in original.infolist():
            data = original.read(entry.filename)
            if entry.filename == "visio/pages/pages.xml":
                # point page 1's relationship at an id that is not in the rels part
                data = data.decode("utf-8").replace("r:id='rId1'", "r:id='rIdMissing'", 1).encode("utf-8")
            rewritten.writestr(entry, data)

    observation = observation_from_package(broken)

    assert [page.index for page in observation.pages] == [1, 2, 3], "page numbering shifted"
    assert observation.pages[0].unresolved
    assert not observation.pages[1].unresolved


class TestPlacementCells:
    """The cells that decide where a shape is and how big it is.

    Structure alone cannot see a shape that moved: the ids, the grouping and the
    glue are all unchanged when a rectangle slides a millimetre to the left. The
    cells below are what makes that visible.
    """

    def test_a_cell_only_one_side_reports_is_a_difference(self):
        package = Observation(label="package", pages=(_page(shapes=(_shape(1, cells=(_cell("PinX", 1.0),)),)),))
        visio = Observation(label="visio", pages=(_page(shapes=(_shape(1),)),))

        differences = compare(package, visio)

        assert [d.kind for d in differences] == ["cell-missing"]
        assert differences[0].locus == "page 1 shape 1 cell PinX"

    def test_a_constant_that_moved_further_than_the_tolerance_is_a_difference(self):
        """A millimetre is 0.0394 internal units: far outside any float noise."""
        package = Observation(label="package", pages=(_page(shapes=(_shape(1, cells=(_cell("PinX", 1.0),)),)),))
        visio = Observation(
            label="visio", pages=(_page(shapes=(_shape(1, cells=(_cell("PinX", 1.0 + 0.03937, result=1.03937),)),)),)
        )

        differences = compare(package, visio)

        assert [d.kind for d in differences] == ["cell-value"]
        assert "PinX" in differences[0].locus
        assert "1.0" in differences[0].detail and "1.03937" in differences[0].detail

    def test_a_constant_that_differs_only_by_float_noise_is_not_a_difference(self):
        """Inches to millimetres and back does not return the same double.

        An exact comparison here fails on arithmetic that is correct. See
        PLACEMENT_TOLERANCE for the measured case and the margin.
        """
        package = Observation(label="package", pages=(_page(shapes=(_shape(1, cells=(_cell("PinX", 1.332677148526936),)),)),))
        visio = Observation(label="visio", pages=(_page(shapes=(_shape(1, cells=(_cell("PinX", 1.33267714852694),)),)),))

        assert compare(package, visio) == ()

    def test_the_same_expression_spelled_differently_is_not_a_difference(self):
        """Visio re-renders a formula from its parse tree, not from our bytes."""
        package = Observation(
            label="package", pages=(_page(shapes=(_shape(1, cells=(_cell_formula("LocPinX", "Width * 0.5"),)),)),)
        )
        visio = Observation(label="visio", pages=(_page(shapes=(_shape(1, cells=(_cell_formula("LocPinX", "WIDTH*0.5"),)),)),))

        assert compare(package, visio) == ()

    def test_a_rewritten_expression_is_a_difference_and_says_where_it_lands(self):
        """The result is not compared, but it is the half a reader can act on.

        Two formulas on a line do not say whether the shape moved by a hair or
        off the page, and only Visio can answer that.
        """
        package = Observation(
            label="package", pages=(_page(shapes=(_shape(1, cells=(_cell_formula("LocPinX", "Width*0.5"),)),)),)
        )
        visio = Observation(
            label="visio",
            pages=(_page(shapes=(_shape(1, cells=(_cell_formula("LocPinX", "Width*0.25", result=0.25),)),)),),
        )

        differences = compare(package, visio)

        assert [d.kind for d in differences] == ["cell-formula"]
        assert "Width*0.5" in differences[0].detail and "Width*0.25" in differences[0].detail
        assert "result 0.25" in differences[0].detail

    def test_a_literal_against_an_expression_is_a_difference(self):
        """The two are different facts about the cell, whatever they evaluate to.

        A package whose formula we replaced with the constant it happened to
        evaluate to at write time has lost the link that kept the shape in place,
        and the next change to Width moves it, even though the two agree
        numerically today.
        """
        package = Observation(label="package", pages=(_page(shapes=(_shape(1, cells=(_cell("LocPinX", 0.5),)),)),))
        visio = Observation(
            label="visio",
            pages=(_page(shapes=(_shape(1, cells=(_cell_formula("LocPinX", "Width*0.5", result=0.5),)),)),),
        )

        differences = compare(package, visio)

        assert [d.kind for d in differences] == ["cell-formula"]
        assert "Width*0.5" in differences[0].detail

    def test_results_are_not_compared_because_only_one_side_can_have_them(self):
        """Visio evaluates; the package's `V` is a cache nothing here recomputes."""
        package = Observation(label="package", pages=(_page(shapes=(_shape(1, cells=(_cell("PinX", 1.0, result=99.0),)),)),))
        visio = Observation(label="visio", pages=(_page(shapes=(_shape(1, cells=(_cell("PinX", 1.0, result=1.0),)),)),))

        assert compare(package, visio) == ()


class TestReadingPlacementCellsFromAPackage:
    def test_it_reads_the_cells_a_shape_states_itself(self, basedir):
        observation = observation_from_package(f"{basedir}/test4_connectors.vsdx")

        shape = observation.pages[0].shapes_by_id[1]
        cells = shape.cells_by_name
        assert set(PLACEMENT_CELLS) >= set(cells)
        assert cells["PinX"].constant == pytest.approx(1.332677148526936)
        # LocPinX carries a formula, so it is compared as text and has no constant
        assert cells["LocPinX"].formula == "Width*0.5"
        assert cells["LocPinX"].constant is None

    def test_a_two_dimensional_shape_states_no_endpoints(self, basedir):
        observation = observation_from_package(f"{basedir}/test4_connectors.vsdx")

        shape = observation.pages[0].shapes_by_id[1]
        assert "BeginX" not in shape.cells_by_name

    def test_a_one_dimensional_shape_states_its_endpoints(self, basedir):
        observation = observation_from_package(f"{basedir}/test4_connectors.vsdx")

        connectors = [shape for page in observation.pages for shape in page.shapes if "BeginX" in shape.cells_by_name]
        assert connectors, "no 1-D shape found in a connector fixture"
        assert {"BeginX", "BeginY", "EndX", "EndY"} <= set(connectors[0].cells_by_name)

    def test_it_takes_cells_the_shape_inherits_from_its_master(self, basedir):
        """A shape that states only `PinX` is still somewhere and still a size.

        The rest of its placement comes from the master, and a comparison that
        could not see it would report a difference against Visio on every
        instance of every stencil shape.
        """
        observation = observation_from_package(f"{basedir}/test5_master.vsdx")

        shape = observation.pages[0].shapes_by_id[1]
        assert "Width" in shape.cells_by_name, "master-inherited cells were not resolved"
        assert shape.cells_by_name["Width"].constant == pytest.approx(1.0)

    def test_a_cell_whose_formula_says_inherit_resolves_to_the_master_formula(self, basedir):
        """`F='Inh'` points at the master's formula; the `V` beside it is that formula, evaluated.

        Reading that number as the cell's own formula would turn every connector
        in the corpus from something tracking its endpoints into a constant that
        happens to sit where the connector was, and the comparison would then
        agree with Visio about a file that had lost its glue.
        """
        observation = observation_from_package(f"{basedir}/test4_connectors.vsdx")

        # shape 6 is a connector: PinX is `<Cell N='PinX' V='2.733...' F='Inh'/>`
        connector = observation.pages[0].shapes_by_id[6]
        pin_x = connector.cells_by_name["PinX"]
        assert pin_x.formula == "GUARD((BeginX+EndX)/2)"
        assert pin_x.constant is None

    def test_every_shape_in_every_fixture_states_a_full_placement(self, basedir):
        """The comparison is symmetric on presence, which is only honest if this holds.

        Visio always has these cells; the package has them only where its XML or
        a master says so. If some shape legitimately said nothing, `cell-missing`
        would fire on a correct file and the check would have to be loosened into
        one that could no longer see a dropped cell.
        """
        import glob

        two_dimensional = set(PLACEMENT_CELLS) - {"BeginX", "BeginY", "EndX", "EndY"}
        for path in sorted(glob.glob(f"{basedir}/*.vsdx")):
            observation = observation_from_package(path)
            for page in observation.pages:
                for shape in page.shapes:
                    missing = two_dimensional - set(shape.cells_by_name)
                    assert not missing, f"{path} shape {shape.id} states nothing about {sorted(missing)}"


@pytest.mark.parametrize(
    "formula",
    ["0", "1.25", ".5", "-3e-2", "33.849999572584 mm", "0.19685039370079DL", "0 deg", "TRUE", "FALSE", "1.5 in."],
)
def test_both_sides_agree_that_a_literal_is_a_literal(formula):
    """The two readers share one classifier, and this is what that buys.

    If the COM side called `FALSE` an expression where the package side called
    `0` a constant, every shape in every file would report a kind mismatch. The
    classifier is the only thing standing between the two spellings.
    """
    package = _com(formula, 0.0).constant
    visio = _package(formula, "0").constant

    assert package is not None and visio is not None


@pytest.mark.parametrize("formula", ["Width*0.5", "GUARD((BeginX+EndX)/2)", "_WALKGLUE(a,b,c)", "Sheet.7!Width*1", ""])
def test_both_sides_agree_that_an_expression_is_an_expression(formula):
    assert _com(formula, 0.0).constant is None
    assert _package(formula, "0").constant is None


class TestReadingPlacementCellsFromCom:
    def _payload(self, cells):
        return {
            "schema": SCHEMA_VERSION,
            "pages": [{"index": 1, "name": "Page-1", "shapes": [{"id": 1, "parent_id": None, "cells": cells}]}],
        }

    def test_a_literal_formula_takes_its_number_from_the_result(self):
        """Visio spells the constant in the document's units; the result is in ours.

        `33.849999572584 mm` and `1.33267714852694` are the same fact. Only the
        second is in internal units, which is the unit the package writes, so it
        is the one the comparison can use - and taking it from the result costs
        no unit parser, because a literal formula evaluates to itself.
        """
        observation = observation_from_com_json(
            self._payload([{"name": "PinX", "formula": "33.849999572584 mm", "result": 1.33267714852694}])
        )

        cell = observation.pages[0].shapes_by_id[1].cells_by_name["PinX"]
        assert cell.constant == pytest.approx(1.33267714852694)
        assert cell.result == pytest.approx(1.33267714852694)

    def test_an_expression_has_no_constant(self):
        observation = observation_from_com_json(self._payload([{"name": "LocPinX", "formula": "Width*0.5", "result": 0.5}]))

        cell = observation.pages[0].shapes_by_id[1].cells_by_name["LocPinX"]
        assert cell.constant is None
        assert cell.result == pytest.approx(0.5)

    def test_a_boolean_formula_is_a_literal(self):
        """Visio renders FlipX as `FALSE` where the package writes `0`.

        Reading that as an expression would report a difference on every shape in
        every file.
        """
        observation = observation_from_com_json(self._payload([{"name": "FlipX", "formula": "FALSE", "result": 0.0}]))

        cell = observation.pages[0].shapes_by_id[1].cells_by_name["FlipX"]
        assert cell.constant == pytest.approx(0.0)
