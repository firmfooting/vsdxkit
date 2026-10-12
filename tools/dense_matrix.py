"""Time layered_layout on dense random graphs and print a markdown table of seconds, search steps and outcome.

Run it before and after a change to the router; the pull request that changes it records both tables.

    uv run python tools/dense_matrix.py [--seed N] [--quick]

Steps are the search steps charged against the work cap, summed over every layout pass of the call.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from helpers.graphs import random_graph

from vsdxkit import layout as layout_module
from vsdxkit.errors import GraphError
from vsdxkit.layout import LayoutNode, LayoutOptions, layered_layout

CELLS = [
    (60, 200, 0, 6, "left_to_right"),
    (60, 200, 0, 6, "top_down"),
    (100, 160, 0, 0, "left_to_right"),
    (150, 240, 4, 4, "left_to_right"),
    (200, 320, 4, 4, "left_to_right"),
    (200, 400, 0, 0, "left_to_right"),
    (200, 400, 0, 0, "top_down"),
    (200, 400, 0, 20, "left_to_right"),
    (200, 400, 0, 20, "top_down"),
]


def measure(seed: int, n: int, m: int, lanes: int, groups: int, direction: str) -> tuple[float, int, str]:
    """(seconds, search steps, outcome) of one layout; the outcome is 'laid out' or the GraphError text."""
    rows, edges, lane_ids, group_ids, parents = random_graph(seed, n, m, lanes, groups)
    nodes = tuple(LayoutNode(*row) for row in rows)
    options = LayoutOptions(direction=direction, parents=parents)
    meters: list[list[int]] = []
    real = layout_module._lay_out

    def spy(*args):  # the last argument is the step counter of that pass
        meters.append(args[-1])
        return real(*args)

    layout_module._lay_out = spy
    start = time.perf_counter()
    try:
        layered_layout(nodes, edges, lane_ids, group_ids, options)
        outcome = "laid out"
    except GraphError as error:
        outcome = str(error)
    finally:
        layout_module._lay_out = real
    seconds = time.perf_counter() - start
    return seconds, sum({id(w): w[0] for w in meters}.values()), outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--quick", action="store_true", help="only the cells that finish in a few seconds")
    args = parser.parse_args()
    print("| nodes | edges | lanes | groups | direction | seconds | steps | outcome |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for n, m, lanes, groups, direction in CELLS[: 3 if args.quick else None]:
        seconds, steps, outcome = measure(args.seed, n, m, lanes, groups, direction)
        print(f"| {n} | {m} | {lanes} | {groups} | {direction} | {seconds:.1f} | {steps:,} | {outcome} |", flush=True)


if __name__ == "__main__":
    main()
