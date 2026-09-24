"""Time the reads a shape serves, on s05 and on a generated page of about 1,000 shapes.

Run it before and after a change to how shapes read their XML: the cache
policy (#102) is decided by these numbers, and the pull request that changes
it records them.

    uv run python tools/bench_shape_reads.py
"""

import copy
import os
import shutil
import tempfile
import time
from collections.abc import Callable

from vsdxkit import namespace
from vsdxkit.document import Document
from vsdxkit.pages import Page

HERE = os.path.dirname(os.path.abspath(__file__))
S05 = os.path.join(HERE, "..", "tests", "fixtures", "com_reference", "s05_swimlanes_cfflow.vsdx")
REPEATS = 5


def _grow(page: Page, target: int) -> None:
    """Append copies of the page's top-level shapes until it holds about `target` shapes."""
    shapes = page.xml.getroot().find(f"{namespace}Shapes")
    originals = list(shapes)
    next_id = 10_000
    while len(page.shapes) < target:
        for original in originals:
            clone = copy.deepcopy(original)
            for element in clone.iter(f"{namespace}Shape"):
                element.attrib["ID"] = str(next_id)
                next_id += 1
            shapes.append(clone)


def _workloads(page: Page) -> dict[str, Callable[[], object]]:
    def walk() -> object:
        return [shape.ID for shape in page.shapes]

    def geometry() -> object:
        return [(s.x, s.y, s.width, s.height, s.text) for s in page.shapes]

    def reread() -> object:
        shapes = list(page.shapes)
        return [(s.x, s.y, s.width, s.height) for _ in range(10) for s in shapes]

    def cells() -> object:
        return [len(s.cells) for s in page.shapes]

    def properties() -> object:
        return [len(s.data_properties) for s in page.shapes]

    def reproperties() -> object:
        shapes = list(page.shapes)
        return [len(s.data_properties) for _ in range(10) for s in shapes]

    def background() -> object:
        return [page.background for _ in range(1000)]

    return {
        "walk": walk,
        "geometry": geometry,
        "reread x10": reread,
        "cells": cells,
        "properties": properties,
        "reproperties x10": reproperties,
        "background x1000": background,
    }


def _best(work: Callable[[], object]) -> float:
    times = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        work()
        times.append(time.perf_counter() - start)
    return min(times)


def _report(label: str, page: Page) -> None:
    print(f"{label}: {len(page.shapes)} shapes")
    for name, work in _workloads(page).items():
        print(f"  {name:<18} {_best(work) * 1000:9.2f} ms")


def main() -> None:
    workdir = tempfile.mkdtemp()
    try:
        path = shutil.copy(S05, workdir)
        vis = Document.open(path)
        _report("s05 page 1", vis.pages[0])
        _grow(vis.pages[0], 1000)
        _report("s05 page 1 grown", vis.pages[0])
    finally:
        shutil.rmtree(workdir)


if __name__ == "__main__":
    main()
