"""Random flow graphs for the layout tests and the builder corpus tests."""

import random


def random_graph(seed: int, n: int, m: int, lanes: int, groups: int):
    """A cyclic random graph as (nodes, edges, lane ids, group ids, group parents).

    A node is (id, width, height, lane, group), the arguments of ``LayoutNode``. With two or more groups the
    second nests in the first, and a group and its child stay in one lane.
    """
    rng = random.Random(seed)
    lane_ids = tuple(f"L{i}" for i in range(lanes))
    group_ids = tuple(f"G{i}" for i in range(groups))
    group_lane: dict[str, str | None] = {}
    nodes = []
    for i in range(n):
        lane = lane_ids[i % lanes] if lanes else None
        group = rng.choice(group_ids) if groups and rng.random() < 0.5 else None
        if group is not None:
            # a group stays in one lane, and so does its child
            root = "G0" if group in ("G0", "G1") else group
            lane = group_lane.setdefault(root, lane)
        nodes.append((f"n{i}", rng.choice([1.5, 2.0, 2.5]), rng.choice([0.8, 1.0, 1.2]), lane, group))
    edges = tuple((f"n{rng.randrange(n)}", f"n{rng.randrange(n)}") for _ in range(m))
    parents = (("G1", "G0"),) if groups >= 2 else ()
    return tuple(nodes), edges, lane_ids, group_ids, parents


def random_tree(seed: int, n: int):
    """A random out-tree as (node ids, edges): node i's parent is a random earlier node."""
    rng = random.Random(seed)
    ids = [f"n{i}" for i in range(n)]
    return ids, tuple((ids[rng.randrange(i)], ids[i]) for i in range(1, n))
