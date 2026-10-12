"""The routes of the corpus equal one committed digest, on every platform."""

import copy
from pathlib import Path

import layout_corpus as corpus
from helpers.route_metrics import layout_digest

GOLDEN = Path(__file__).parent / "fixtures" / "routes.sha256"


def test_the_routes_equal_the_digest_every_platform_is_held_to():
    digest = layout_digest(corpus.all_layouts())
    assert digest == GOLDEN.read_text(encoding="utf-8").strip(), (
        "the routes moved; if the bytes digest test also fails the change moved routes, "
        "and tools/regen_digests.py is part of the phase-close procedure"
    )


def test_the_digest_ignores_float_noise_below_the_grid():
    layouts = corpus.all_layouts()
    noisy = copy.deepcopy(layouts)
    first = next(iter(noisy["hub5"].routes))
    noisy["hub5"].routes[first] = tuple((x + 1e-9, y - 1e-9) for x, y in noisy["hub5"].routes[first])
    assert layout_digest(noisy) == layout_digest(layouts)
