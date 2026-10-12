"""The layouts the metrics, the ratchet and the digests measure: the fixtures plus a seeded random set."""

import importlib.util
from dataclasses import replace
from pathlib import Path
from types import ModuleType

from helpers.graphs import random_graph, random_tree  # noqa: F401  (random_tree is re-exported)

from vsdxkit import builder
from vsdxkit.builder import Edge, Lane, Node, Page
from vsdxkit.layout import Layout, LayoutOptions

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "diagrams"
FIXTURES = ("hub5", "hub5_top_down", "chain25", "lanes3", "fanin", "pins")
KINDS = ("process", "decision", "document", "subprocess")


def _load(stem: str) -> ModuleType:
    """The case file `stem` as a module; an import error propagates with the file's name."""
    spec = importlib.util.spec_from_file_location(f"corpus_{stem}", FIXTURE_DIR / f"{stem}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load the fixture {stem}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture_page(stem: str, override: LayoutOptions | None = None) -> tuple[Page, LayoutOptions]:
    """Fixture `stem`'s page and its options; `override` replaces only the options' page target."""
    module = _load(stem)
    options = module.OPTIONS or LayoutOptions()
    if override is not None:
        options = replace(options, page=override.page)
    return module.page(), options


def _random_page(seed: int, n: int, m: int) -> Page:
    """A seeded random page of `n` nodes and `m` edges, no lanes or groups."""
    rows, edges, *_ = random_graph(seed, n, m, 0, 0)
    nodes = [Node(row[0], KINDS[i % len(KINDS)], f"Step {i}") for i, row in enumerate(rows)]
    return Page("rand", nodes, [Edge(s, t) for s, t in edges])


def fixture_layout(stem: str, override: LayoutOptions | None = None) -> Layout:
    """The layout of fixture `stem` under its own options, as the builder would draw it; `override` replaces only the options' page target."""
    page, options = _fixture_page(stem, override)
    return builder._layout_page(page, options)[0]


def random_layout(seed: int, n: int, m: int, override: LayoutOptions | None = None) -> Layout:
    """A seeded random page of `n` nodes and `m` edges, no lanes or groups, default options (or `override`)."""
    return builder._layout_page(_random_page(seed, n, m), override or LayoutOptions())[0]


def _drawn(page: Page, options: LayoutOptions) -> dict[tuple[str, str, int], tuple[tuple[float, float], ...]]:
    """The connector points the builder draws for `page`, from the builder's own function."""
    layout, sizes = builder._layout_page(page, options)
    return builder._drawn_paths(page, layout, sizes)


def all_layouts() -> dict[str, Layout]:
    """Every corpus layout by name: the fixtures, then rand-0 to rand-4 (40 nodes, 60 edges)."""
    out = {stem: fixture_layout(stem) for stem in FIXTURES}
    out.update({f"rand-{seed}": random_layout(seed, 40, 60) for seed in range(5)})
    return out


def all_drawn() -> dict[str, dict[tuple[str, str, int], tuple[tuple[float, float], ...]]]:
    """Every corpus entry's drawn connector points by name, keyed like `all_layouts`."""
    out = {stem: _drawn(*_fixture_page(stem)) for stem in FIXTURES}
    out.update({f"rand-{seed}": _drawn(_random_page(seed, 40, 60), LayoutOptions()) for seed in range(5)})
    return out


def _labelled_edges(edges: tuple[tuple[str, str], ...]) -> list[Edge]:
    """`edges` with every third one labelled `Label {i}`."""
    return [Edge(s, t, f"Label {i}" if i % 3 == 0 else None) for i, (s, t) in enumerate(edges)]


def labelled_random_layout(seed: int, n: int, m: int) -> Layout:
    """A seeded random page of `n` nodes and `m` edges, every third edge labelled, no lanes."""
    rows, edges, *_ = random_graph(seed, n, m, 0, 0)
    nodes = [Node(row[0], KINDS[i % len(KINDS)], f"Step {i}") for i, row in enumerate(rows)]
    return builder._layout_page(Page("rand", nodes, _labelled_edges(edges)), LayoutOptions())[0]


def labelled_lane_layout(seed: int) -> Layout:
    """A seeded random page of 12 nodes and 16 edges in three lanes, every third edge labelled."""
    rows, edges, lane_ids, *_ = random_graph(seed, 12, 16, 3, 0)
    nodes = [Node(row[0], KINDS[i % len(KINDS)], f"Step {i}") for i, row in enumerate(rows)]
    lanes = [Lane(lid, f"Lane {lid}", [row[0] for row in rows if row[3] == lid]) for lid in lane_ids]
    return builder._layout_page(Page("lanes", nodes, _labelled_edges(edges), lanes=lanes), LayoutOptions())[0]
