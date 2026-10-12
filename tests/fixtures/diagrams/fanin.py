"""Case: four sources feeding one target, which feeds an end node."""

from vsdxkit.builder import Diagram, Edge, Node, Page
from vsdxkit.document import Document

OPTIONS = None


def page() -> Page:
    """The page, built with no coordinates."""
    sources = [Node(f"a{i}", "process", f"Source {i}") for i in range(1, 5)]
    nodes = [*sources, Node("target", "process", "Collect"), Node("done", "end", "Done")]
    edges = [Edge(f"a{i}", "target") for i in range(1, 5)] + [Edge("target", "done")]
    return Page("fanin", nodes, edges)


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    return Diagram("fanin", [page()]).build(layout=OPTIONS)
