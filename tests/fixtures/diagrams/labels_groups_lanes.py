"""Case: labels that stay in a lane, parallel labelled edges, a labelled edge into a headed group, and a label wider than its gap, over three lanes."""

from vsdxkit.builder import Diagram, Edge, Group, Lane, Node, Page
from vsdxkit.document import Document


def build() -> Document:
    """The document the Visio harness is shown for this case, built with no coordinates."""
    nodes = [
        Node(i, "process", t)
        for i, t in [("r1", "Draft"), ("r2", "Submit"), ("v1", "Check"), ("v2", "Decide"), ("a1", "File")]
    ]
    edges = [
        Edge("r1", "r2", "yes"),
        Edge("r1", "r2", "no"),
        Edge("r1", "r2", "maybe"),
        Edge("r2", "v1", "needs a second look"),
        Edge("v1", "v2"),
        Edge("v2", "a1", "archive when approved"),
    ]
    lanes = [Lane("l1", "Requester", ["r1", "r2"]), Lane("l2", "Reviewer", ["v1", "v2"]), Lane("l3", "Archive", ["a1"])]
    groups = [Group("g1", "Review step", ["v1"])]
    return Diagram("Labels", [Page("Labels", nodes, edges, groups, lanes)]).build()
