"""Case: a decision node and a rounded start node, each with three edges arriving and leaving at offset points."""

from vsdxkit.builder import Diagram, Edge, Node, Page
from vsdxkit.document import Document


def build() -> Document:
    """The document the Visio harness is shown for this case, built with no coordinates."""
    nodes = [
        Node("a", "process", "Source"),
        Node("d", "decision", "Choice"),
        Node("e", "start", "Rounded"),
        Node("b", "process", "Sink"),
    ]
    edges = [Edge("a", "d") for _ in range(3)] + [Edge("d", "e") for _ in range(3)] + [Edge("e", "b") for _ in range(3)]
    return Diagram("Node outlines", [Page("Outlines", nodes, edges)]).build()
