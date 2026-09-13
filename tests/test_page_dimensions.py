"""Page dimension setters must reject unusable values instead of writing zeros."""

import math

import pytest

import vsdxkit


@pytest.fixture
def page(vsdx_copy):
    with vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as visio:
        yield visio.pages[0]


@pytest.mark.parametrize("setter", ["width", "height"])
def test_dimension_setters_reject_none(page, setter):
    with pytest.raises(TypeError, match="cannot be None"):
        setattr(page, setter, None)
    assert getattr(page, setter) > 0  # unchanged, not overwritten with 0


@pytest.mark.parametrize("setter", ["width", "height"])
def test_dimension_setters_reject_non_numeric(page, setter):
    with pytest.raises(ValueError, match="must be a finite positive number"):
        setattr(page, setter, "wide")
    assert getattr(page, setter) > 0


@pytest.mark.parametrize("setter", ["width", "height"])
def test_dimension_setters_reject_non_finite(page, setter):
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="must be a finite positive number"):
            setattr(page, setter, value)
        assert getattr(page, setter) > 0


@pytest.mark.parametrize("setter", ["width", "height"])
def test_dimension_setters_reject_non_positive(page, setter):
    for value in (0, 0.0, -1, -2.5):
        with pytest.raises(ValueError, match="must be a finite positive number"):
            setattr(page, setter, value)
    assert getattr(page, setter) > 0


@pytest.mark.parametrize("setter", ["width", "height"])
def test_dimension_setters_accept_numeric_and_string(page, setter):
    current = getattr(page, setter)
    setattr(page, setter, current + 1)
    assert math.isclose(getattr(page, setter), current + 1)
    setattr(page, setter, str(current + 2))
    assert math.isclose(getattr(page, setter), current + 2)
