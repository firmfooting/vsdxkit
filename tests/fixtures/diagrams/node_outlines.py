"""Case: a decision, a rounded start, a default data store and a tall data store, each with three edges arriving and leaving at offset points."""

from vsdxkit.builder import Diagram, Edge, Node, Page
from vsdxkit.document import Document


def build() -> Document:
    """The document the Visio harness is shown for this case, built with no coordinates."""
    nodes = [
        Node("a", "process", "Source"),
        Node("d", "decision", "Choice"),
        Node("e", "start", "Rounded"),
        Node("b", "process", "Sink"),
        Node("s", "data_store", "Store"),
        Node("t", "data_store", "Tall\nstore\nof three lines"),
    ]
    edges = [Edge("a", "d") for _ in range(3)] + [Edge("d", "e") for _ in range(3)] + [Edge("e", "b") for _ in range(3)]
    edges += [Edge("b", "s") for _ in range(3)] + [Edge("s", "t") for _ in range(3)]
    return Diagram("Node outlines", [Page("Outlines", nodes, edges)]).build()
