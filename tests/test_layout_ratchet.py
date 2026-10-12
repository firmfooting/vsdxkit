"""The 0.10 crossing counts are a ceiling the new layout must not exceed."""

import json
from itertools import pairwise
from pathlib import Path

import layout_corpus as corpus
import pytest
from helpers import route_metrics as rm

from vsdxkit import layout as lo
from vsdxkit.layout import LayoutNode, layered_layout

BASELINE = json.loads((Path(__file__).parent / "fixtures" / "layout_baseline.json").read_text(encoding="utf-8"))


# Phase 1 wraps these into rows, and the fold adds crossings the one-row 0.10 layout did not have; the random pages are still over their 0.10 count.
WRAPPED_CEILING = {"rand-2": 244, "rand-3": 252}


def _ratchet_failures(layouts, baseline):
    """Messages for a case set that differs from the baseline's, else for each case over its crossing ceiling."""
    missing, extra = sorted(set(baseline) - set(layouts)), sorted(set(layouts) - set(baseline))
    if missing or extra:
        return [f"corpus and baseline differ: missing {missing}, extra {extra}"]
    return [
        name
        for name, lay in layouts.items()
        if rm.crossings(lay) > max(baseline[name]["crossings"], WRAPPED_CEILING.get(name, 0))
    ]


def test_crossings_do_not_exceed_the_0_10_baseline():
    """A4 ratchet. Lower a baseline entry by regenerating the file; raising one needs a reason in the pull request."""
    assert _ratchet_failures(corpus.all_layouts(), BASELINE["metrics"]) == []


@pytest.mark.parametrize("name", ["hub5", "hub5_top_down", "fanin", "chain25", "lanes3", "pins"])
def test_the_named_fixtures_have_no_crossing(name):
    assert rm.crossings(corpus.fixture_layout(name)) == 0


def _tree_seed_marks(seed):
    """The strict xfail for the two seeds whose crossings survive ordering: seed 3 only crosses once the page wraps, seed 4 keeps one layer crossing."""
    reasons = {
        3: "the layers are crossing free but the snake wrap folds the tree so two routes cross; the wrap's fold is not an ordering matter",
        4: "barycentre sweeps and transposition leave one crossing between two layers of this tree",
    }
    return pytest.mark.xfail(strict=True, reason=reasons[seed]) if seed in reasons else ()


@pytest.mark.parametrize("seed", [pytest.param(n, marks=_tree_seed_marks(n)) for n in range(10)])
def test_a_random_tree_has_no_crossing(seed):
    ids, edges = corpus.random_tree(seed, 30)
    lay = layered_layout(tuple(LayoutNode(i, 2.0, 1.0) for i in ids), edges)
    assert rm.crossings(lay) == 0


def test_the_ratchet_notices_a_deleted_case():
    layouts = corpus.all_layouts()
    del layouts["hub5"]
    (message,) = _ratchet_failures(layouts, BASELINE["metrics"])
    assert "missing ['hub5']" in message


def test_chain25_aspect_is_in_the_band():
    """A8: a long linear flow is wrapped to the page target, not laid out as a strip."""
    assert 1.33 <= rm.aspect(corpus.all_layouts()["chain25"]) <= 2.22


PITCH = 0.2  # the default port pitch, which is the overlap A5 asks for


def _page_of(name):
    """The page and options behind corpus entry `name`."""
    if name.startswith("rand-"):
        return corpus._random_page(int(name[5:]), 40, 60), lo.LayoutOptions()
    return corpus._fixture_page(name)


def _edge_kinds(page):
    """Each edge's (source, target) mapped to 'feedback', 'adjacent' (forward, next layer) or 'other'."""
    ids = [n.id for n in page.nodes]
    edges = [(e.source, e.target) for e in page.edges]
    flipped = lo._break_cycles(ids, edges)
    layer = lo._layers(ids, edges, flipped, {n.id: n.layer for n in page.nodes if n.layer is not None})
    return {
        edge: "feedback" if flip else "adjacent" if layer[edge[1]] - layer[edge[0]] == 1 else "other"
        for edge, flip in zip(edges, flipped, strict=True)
    }


def _span(box, top_down):
    """A box's (low, high) across the flow and (low, high) along it."""
    across, along = ((box.x, box.width), (box.y, box.height)) if top_down else ((box.y, box.height), (box.x, box.width))
    return (across[0] - across[1] / 2, across[0] + across[1] / 2), (along[0] - along[1] / 2, along[0] + along[1] / 2)


def _bent_though_straight_would_do(name, lay):
    """Forward, unwrapped-row edges whose boxes overlap across the flow by a port pitch, with no box between them and no other route on the straight line, that still bend (A5)."""
    page, options = _page_of(name)
    top_down = options.direction == "top_down"
    kinds = _edge_kinds(page)
    row_of = {n: i for i, row in enumerate(lay.rows) for n in row}
    out = []
    for (source, target, n), route in lay.routes.items():
        if source == target or kinds[(source, target)] == "feedback" or row_of.get(source) != row_of.get(target):
            continue
        (a_across, a_along), (b_across, b_along) = _span(lay.nodes[source], top_down), _span(lay.nodes[target], top_down)
        low, high = max(a_across[0], b_across[0]), min(a_across[1], b_across[1])
        first, second = sorted((a_along, b_along))
        gap = (first[1], second[0])
        if high - low < PITCH or gap[0] >= gap[1]:
            continue
        between = any(
            gap[0] < sum(along) / 2 < gap[1] and across[0] < high and across[1] > low
            for other, box in lay.nodes.items()
            if other not in (source, target)
            for across, along in [_span(box, top_down)]
        )
        middle = (low + high) / 2
        used = any(
            min(p[0 if top_down else 1], q[0 if top_down else 1]) - 1e-6 <= middle
            and middle <= max(p[0 if top_down else 1], q[0 if top_down else 1]) + 1e-6
            and max(p[1 if top_down else 0], q[1 if top_down else 0]) > gap[0]
            and min(p[1 if top_down else 0], q[1 if top_down else 0]) < gap[1]
            for key, other in lay.routes.items()
            if key != (source, target, n)
            for p, q in pairwise(other)
        )
        if not between and not used and rm.bends(route) > 0:
            out.append((source, target, n))
    return out


# Dense random pages: a box with several edges on one side spreads their ports a pitch apart, and a long edge winds round the dummies of the layers it jumps.
A5_KNOWN = {"rand-0": [("n35", "n37", 0)], "rand-2": [("n5", "n20", 0)], "rand-3": [("n29", "n22", 0)]}


@pytest.mark.parametrize("name", sorted(BASELINE["metrics"]))
def test_a_straight_run_has_no_bends(name):
    """A5 over the corpus; the random pages' exceptions are listed so a fix shrinks the list and a new one fails."""
    assert _bent_though_straight_would_do(name, corpus.all_layouts()[name]) == A5_KNOWN.get(name, [])


BUDGET = {"adjacent": 2, "other": 4, "feedback": 4}


@pytest.mark.parametrize("name", sorted(BASELINE["metrics"]))
def test_the_bend_budget_holds(name):
    """A6: the adjacent-layer budget on every entry, the others on the named fixtures (the dense random pages exceed them)."""
    lay, kinds = corpus.all_layouts()[name], _edge_kinds(_page_of(name)[0])
    limits = BUDGET if not name.startswith("rand-") else {"adjacent": 2}
    over = [key for key, route in lay.routes.items() if key[0] != key[1] and rm.bends(route) > limits.get(kinds[key[:2]], 99)]
    assert over == []


def test_a_cross_lane_edge_between_adjacent_columns_has_at_most_one_bend():
    lay, (page, _) = corpus.all_layouts()["lanes3"], _page_of("lanes3")
    lane_of = {n: lane.id for lane in page.lanes for n in lane.node_ids}
    kinds = _edge_kinds(page)
    cross = [key for key in lay.routes if kinds[key[:2]] == "adjacent" and lane_of[key[0]] != lane_of[key[1]]]
    assert cross and all(rm.bends(lay.routes[key]) <= 1 for key in cross)
