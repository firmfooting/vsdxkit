"""Case: a 25 step chain with two decisions that skip a step, and one feedback edge."""

from vsdxkit.builder import Diagram, Edge, Node, Page
from vsdxkit.document import Document

OPTIONS = None

DECISIONS = (8, 17)


def page() -> Page:
    """The page, built with no coordinates."""
    nodes = [Node(f"p{i}", "decision" if i in DECISIONS else "process", f"Step {i}") for i in range(1, 26)]
    edges = []
    for i in range(1, 25):
        if i in DECISIONS:
            nodes.append(Node(f"alt{i}", "process", f"Skip {i}"))
            edges += [
                Edge(f"p{i}", f"p{i + 1}", "Yes", "yes-path"),
                Edge(f"p{i}", f"alt{i}", "No", "no-path"),
                Edge(f"alt{i}", f"p{i + 2}"),
                Edge(f"p{i + 1}", f"p{i + 2}"),
            ]
        elif i - 1 not in DECISIONS:
            edges.append(Edge(f"p{i}", f"p{i + 1}"))
    edges.append(Edge("p20", "p14"))
    return Page("chain25", nodes, edges)


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    return Diagram("chain25", [page()]).build(layout=OPTIONS)
