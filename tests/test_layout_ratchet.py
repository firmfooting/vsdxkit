"""The 0.10 crossing counts are a ceiling the new layout must not exceed."""

import json
from pathlib import Path

import layout_corpus as corpus
from helpers import route_metrics as rm

BASELINE = json.loads((Path(__file__).parent / "fixtures" / "layout_baseline.json").read_text(encoding="utf-8"))


def test_crossings_do_not_exceed_the_0_10_baseline():
    """A4 ratchet. Lower a baseline entry by regenerating the file; raising one needs a reason in the pull request."""
    for name, lay in corpus.all_layouts().items():
        assert rm.crossings(lay) <= BASELINE["metrics"][name]["crossings"], name
