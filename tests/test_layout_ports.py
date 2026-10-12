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


def test_ports_cover_at_most_eighty_percent_of_a_side_where_the_cap_binds():
    offsets = lo._spread(12, 2.0, "n", 0.2)  # the uncapped pitch is 0.15 and would span 1.65
    assert offsets[-1] - offsets[0] <= 1.6 + 1e-9


def test_the_pitch_never_drops_below_a_tenth_until_the_side_cannot_hold_the_ports():
    held = lo._spread(10, 1.0, "n", 0.2)  # ten ports at 0.1 fit a one inch side, past the 80 percent cap
    assert round(held[1] - held[0], 2) == 0.1
    shrunk = lo._spread(12, 1.0, "n", 0.2)  # twelve at 0.1 do not
    assert min(b - a for a, b in pairwise(shrunk)) >= 0.01 and shrunk[1] - shrunk[0] < 0.1


def test_the_new_options_are_appended_after_the_existing_fields():
    opts = LayoutOptions(
        "left_to_right", 1.0, 0.4, 0.5, 0.25, 0.3, 0.6, 8, None, (("c", "p"),), (("c", 1.0, 0.2),), ((1.0, 0.2),)
    )
    assert (opts.page, opts.parents, opts.headings, opts.edge_labels) == (
        None,
        (("c", "p"),),
        (("c", 1.0, 0.2),),
        ((1.0, 0.2),),
    )
    assert (opts.port_pitch, opts.channel_pitch) == (0.2, 0.2)


def test_a_port_pitch_reaches_the_ports_of_a_layout():
    nodes = (LayoutNode("hub", 2, 4), *(LayoutNode(f"t{i}", 1, 1) for i in range(3)))
    edges = tuple(("hub", f"t{i}") for i in range(3))

    def gap(pitch):
        layout = layered_layout(nodes, edges, options=LayoutOptions(port_pitch=pitch, page=None))
        ys = sorted(r[0][1] for r in layout.routes.values())
        return round(min(b - a for a, b in pairwise(ys)), 2)

    assert gap(0.4) == 0.4 and gap(0.1) == 0.1


@pytest.mark.parametrize("name", ["hub5", "hub5_top_down", "fanin"])
def test_no_two_ports_on_a_side_are_closer_than_the_pitch(name):
    assert rm.port_gap_violations(corpus.fixture_layout(name)) == []


@pytest.mark.parametrize("option", ["port_pitch", "channel_pitch"])
@pytest.mark.parametrize("bad", [0.0, 0.005, float("nan"), float("inf"), -1.0, True])
def test_a_pitch_that_is_not_valid_is_refused_by_name(option, bad):
    with pytest.raises(GraphError, match=option):
        layered_layout((LayoutNode("a", 2, 1),), (), options=LayoutOptions(**{option: bad}))
