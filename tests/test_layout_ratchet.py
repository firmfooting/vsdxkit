"""The 0.10 crossing counts are a ceiling the new layout must not exceed."""

import json
from pathlib import Path

import layout_corpus as corpus
from helpers import route_metrics as rm

BASELINE = json.loads((Path(__file__).parent / "fixtures" / "layout_baseline.json").read_text(encoding="utf-8"))


def _ratchet_failures(layouts, baseline):
    """Messages for a case set that differs from the baseline's, else for each case over its crossing ceiling."""
    missing, extra = sorted(set(baseline) - set(layouts)), sorted(set(layouts) - set(baseline))
    if missing or extra:
        return [f"corpus and baseline differ: missing {missing}, extra {extra}"]
    return [name for name, lay in layouts.items() if rm.crossings(lay) > baseline[name]["crossings"]]


def test_crossings_do_not_exceed_the_0_10_baseline():
    """A4 ratchet. Lower a baseline entry by regenerating the file; raising one needs a reason in the pull request."""
    assert _ratchet_failures(corpus.all_layouts(), BASELINE["metrics"]) == []


def test_the_ratchet_notices_a_deleted_case():
    layouts = corpus.all_layouts()
    del layouts["hub5"]
    (message,) = _ratchet_failures(layouts, BASELINE["metrics"])
    assert "missing ['hub5']" in message


def test_chain25_aspect_is_in_the_band():
    """A8: a long linear flow is wrapped to the page target, not laid out as a strip."""
    assert 1.33 <= rm.aspect(corpus.all_layouts()["chain25"]) <= 2.22
