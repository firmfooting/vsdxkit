"""The 0.10 crossing counts are a ceiling the new layout must not exceed."""

import json
from pathlib import Path

import layout_corpus as corpus
import pytest
from helpers import route_metrics as rm

from vsdxkit.layout import LayoutNode, layered_layout

BASELINE = json.loads((Path(__file__).parent / "fixtures" / "layout_baseline.json").read_text(encoding="utf-8"))


# Phase 1 wraps these into rows, and the fold adds crossings the one-row 0.10 layout did not have; Phases 2 and 3 remove the entries.
WRAPPED_CEILING = {"chain25": 1, "rand-2": 244, "rand-3": 252}


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


@pytest.mark.parametrize("name", ["hub5", "hub5_top_down", "fanin"])
def test_the_fan_fixtures_have_no_crossing(name):
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
