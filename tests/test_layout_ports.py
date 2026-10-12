"""Port pitch: parallel routes meet a side of a box at a set spacing."""

from itertools import pairwise

import layout_corpus as corpus
import pytest
from helpers import route_metrics as rm

from vsdxkit import layout as lo
from vsdxkit.errors import GraphError
from vsdxkit.layout import LayoutNode, LayoutOptions, layered_layout


def test_five_ports_on_a_three_inch_side_sit_at_the_pitch():
    offsets = lo._spread(5, 3.0, "n", 0.2)
    assert [round(b - a, 2) for a, b in pairwise(offsets)] == [0.2] * 4


def test_a_short_side_shrinks_the_pitch_and_a_tiny_one_is_still_refused_by_name():
    offsets = lo._spread(4, 0.6, "n", 0.2)
    assert min(b - a for a, b in pairwise(offsets)) >= 0.01
    assert offsets[-1] - offsets[0] <= 0.48 + 1e-9
    with pytest.raises(GraphError, match="node 'n' is too small"):
        lo._spread(5, 0.04, "n", 0.2)


def test_ports_cover_at_most_eighty_percent_of_a_side():
    offsets = lo._spread(9, 1.0, "n", 0.2)
    assert offsets[-1] - offsets[0] <= 0.8 + 1e-9


@pytest.mark.parametrize("name", ["hub5", "hub5_top_down", "fanin"])
def test_no_two_ports_on_a_side_are_closer_than_the_pitch(name):
    assert rm.port_gap_violations(corpus.fixture_layout(name)) == []


@pytest.mark.parametrize("option", ["port_pitch", "channel_pitch"])
@pytest.mark.parametrize("bad", [0.0, 0.005, float("nan"), float("inf"), -1.0, True])
def test_a_pitch_that_is_not_valid_is_refused_by_name(option, bad):
    with pytest.raises(GraphError, match=option):
        layered_layout((LayoutNode("a", 2, 1),), (), options=LayoutOptions(**{option: bad}))
