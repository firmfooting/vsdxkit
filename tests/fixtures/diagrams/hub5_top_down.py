"""Case: a hub with five children, two of which feed one target (spec 7.1), laid out top down."""

from vsdxkit.builder import Diagram, Edge, Node, Page
from vsdxkit.document import Document
from vsdxkit.layout import LayoutOptions

OPTIONS = LayoutOptions(direction="top_down")


def page() -> Page:
    """The page, built with no coordinates."""
    children = [Node(f"c{i}", "process", f"Child {i}") for i in range(1, 6)]
    nodes = [Node("hub", "process", "Intake"), *children, Node("archive", "end", "Archive")]
    edges = [Edge("hub", f"c{i}") for i in range(1, 6)] + [Edge("c2", "archive"), Edge("c4", "archive")]
    return Page("hub5_top_down", nodes, edges)


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    return Diagram("hub5_top_down", [page()]).build(layout=OPTIONS)
