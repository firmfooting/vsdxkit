"""Label placement (A7): a label sits on its own route, in one lane band, clear of everything else."""

from types import SimpleNamespace as NS

import layout_corpus as corpus
import pytest
from helpers import route_metrics as rm

from vsdxkit.errors import GraphError


def box(x, y, w, h):
    return NS(x=x, y=y, width=w, height=h)


def lay(routes, labels, nodes=None, lanes=None):
    return NS(nodes=nodes or {}, routes=routes, labels=labels, lanes=lanes or {}, width=10, height=6)


def test_a_label_on_its_own_segment_is_clean():
    assert rm.label_violations(lay({("a", "b", 0): ((0, 1), (6, 1))}, {("a", "b", 0): box(3, 1, 1, 0.3)})) == []


def test_a_label_off_its_route_is_a_violation():
    assert rm.label_violations(lay({("a", "b", 0): ((0, 1), (6, 1))}, {("a", "b", 0): box(3, 2, 1, 0.3)}))


def test_a_label_across_a_lane_border_is_a_violation():
    lanes = {"L0": box(5, 1.5, 10, 3), "L1": box(5, 4.5, 10, 3)}
    routes = {("a", "b", 0): ((3, 0.5), (3, 5))}
    assert rm.label_violations(lay(routes, {("a", "b", 0): box(3, 3, 1, 0.3)}, lanes=lanes))


def test_a_label_on_another_routes_segment_is_a_violation():
    routes = {("a", "b", 0): ((0, 1), (6, 1)), ("c", "d", 0): ((3, 0), (3, 2))}
    assert rm.label_violations(lay(routes, {("a", "b", 0): box(3, 1, 1, 0.3)}))


def test_a_label_on_a_node_another_label_or_an_obstacle_is_a_violation():
    routes = {("a", "b", 0): ((0, 1), (6, 1)), ("c", "d", 0): ((0, 1), (6, 1))}
    mine = {("a", "b", 0): box(3, 1, 1, 0.3)}
    assert rm.label_violations(lay(routes, mine, nodes={"n": box(3, 1, 1, 1)}))
    assert rm.label_violations(lay(routes, {**mine, ("c", "d", 0): box(3.2, 1, 1, 0.3)}))
    assert rm.label_violations(lay({("a", "b", 0): ((0, 1), (6, 1))}, mine), obstacles=[box(3, 1, 1, 1)])


@pytest.mark.parametrize("seed", range(8))
def test_a_label_sits_on_its_own_segment_or_the_build_raises(seed):
    try:
        layout = corpus.labelled_random_layout(seed, 24, 36)
    except GraphError as error:
        assert "->" in str(error) or "label" in str(error)  # names the edge; there is no third outcome
        return
    assert rm.label_violations(layout) == []


@pytest.mark.parametrize("seed", range(5))
def test_labels_in_lanes_stay_in_one_band(seed):
    try:
        layout = corpus.labelled_lane_layout(seed)
    except GraphError:
        return
    assert rm.label_violations(layout) == []
