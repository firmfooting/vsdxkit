"""The layouts the metrics, the ratchet and the digests measure: the fixtures plus a seeded random set."""

import importlib.util
from dataclasses import replace
from pathlib import Path
from types import ModuleType

from helpers.graphs import random_graph, random_tree  # noqa: F401  (random_tree is re-exported)

from vsdxkit import builder
from vsdxkit.builder import Edge, Node, Page
from vsdxkit.layout import Layout, LayoutOptions

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "diagrams"
FIXTURES = ("hub5", "hub5_top_down", "chain25", "lanes3", "fanin")
KINDS = ("process", "decision", "document", "subprocess")


def _load(stem: str) -> ModuleType:
    """The case file `stem` as a module; an import error propagates with the file's name."""
    spec = importlib.util.spec_from_file_location(f"corpus_{stem}", FIXTURE_DIR / f"{stem}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load the fixture {stem}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_layout(stem: str, override: LayoutOptions | None = None) -> Layout:
    """The layout of fixture `stem` under its own options, as the builder would draw it; `override` replaces only the options' page target."""
    module = _load(stem)
    options = module.OPTIONS or LayoutOptions()
    if override is not None:
        options = replace(options, page=override.page)
    return builder._layout_page(module.page(), options)[0]


def random_layout(seed: int, n: int, m: int, override: LayoutOptions | None = None) -> Layout:
    """A seeded random page of `n` nodes and `m` edges, no lanes or groups, default options (or `override`)."""
    rows, edges, *_ = random_graph(seed, n, m, 0, 0)
    nodes = [Node(row[0], KINDS[i % len(KINDS)], f"Step {i}") for i, row in enumerate(rows)]
    return builder._layout_page(Page("rand", nodes, [Edge(s, t) for s, t in edges]), override or LayoutOptions())[0]


def all_layouts() -> dict[str, Layout]:
    """Every corpus layout by name: the fixtures, then rand-0 to rand-4 (40 nodes, 60 edges)."""
    out = {stem: fixture_layout(stem) for stem in FIXTURES}
    out.update({f"rand-{seed}": random_layout(seed, 40, 60) for seed in range(5)})
    return out
