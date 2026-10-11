"""Case 2: three lanes, a group holding a group, and edges between lanes."""

from vsdxkit.builder import Diagram, Edge, Group, Lane, Node, Page
from vsdxkit.document import Document


def build() -> Document:
    """The document the Visio harness is shown for this case, built with no coordinates."""
    nodes = [Node(f"s{i}", "process", f"Task {i}") for i in range(6)]
    edges = [Edge(f"s{i}", f"s{i + 1}") for i in range(5)] + [Edge("s1", "s4", "late")]
    lanes = [
        Lane("l1", "Requester", ["s0", "s1"]),
        Lane("l2", "Reviewer", ["s2", "s3", "s4"]),
        Lane("l3", "Archive", ["s5"]),
    ]
    groups = [Group("g1", "Review", ["s2"], [Group("g2", "Second look", ["s3", "s4"])])]
    return Diagram("Lanes", [Page("Lanes", nodes, edges, groups, lanes)]).build()
