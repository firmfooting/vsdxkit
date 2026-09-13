"""Tests for the Visio differential oracle's comparison layer.

These run without Visio. The point of the harness is that judgment lives in
Python where it can be tested; this file is what makes that claim true.
"""

import json

import pytest
from helpers.visio_observation import (
    SCHEMA_VERSION,
    ConnectObservation,
    Observation,
    PageObservation,
    ShapeObservation,
    compare,
    observation_from_com_json,
    observation_from_package,
)


def _page(index=1, name="Page-1", shapes=(), connects=()):
    return PageObservation(index=index, name=name, shapes=tuple(shapes), connects=tuple(connects))


def _shape(shape_id, parent_id=None, name=""):
    return ShapeObservation(id=shape_id, parent_id=parent_id, name=name)


def test_identical_observations_have_no_differences():
    one = Observation(label="package", pages=(_page(shapes=(_shape(1), _shape(2))),))
    other = Observation(label="visio", pages=(_page(shapes=(_shape(1), _shape(2))),))
    assert compare(one, other) == ()


def test_a_shape_the_second_side_never_reports_is_a_difference():
    """The bug this whole harness exists for: Visio silently drops a shape.

    A package declaring four shapes that Visio opens as three is a data-losing
    file, and Visio says nothing at all - it reports success and saves happily.
    """
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

    `Sheet.5` is not stored anywhere in the file; Visio derives it. Comparing
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

    def test_a_package_is_identical_to_itself(self, basedir):
        """The comparison's floor: if this ever fails, no other result means anything."""
        path = f"{basedir}/test4_connectors.vsdx"

        assert compare(observation_from_package(path, "a"), observation_from_package(path, "b")) == ()


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
