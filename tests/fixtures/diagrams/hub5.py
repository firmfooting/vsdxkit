"""Case: a hub with five children, two of which feed one target (spec 7.1, fixture hub5)."""

from vsdxkit.builder import Diagram, Edge, Node, Page
from vsdxkit.document import Document

OPTIONS = None


def page() -> Page:
    """The page, built with no coordinates."""
    children = [Node(f"c{i}", "process", f"Child {i}") for i in range(1, 6)]
    nodes = [Node("hub", "process", "Intake"), *children, Node("archive", "end", "Archive")]
    edges = [Edge("hub", f"c{i}") for i in range(1, 6)] + [Edge("c2", "archive"), Edge("c4", "archive")]
    return Page("hub5", nodes, edges)


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    return Diagram("hub5", [page()]).build(layout=OPTIONS)
