"""Case: a diamond whose first and last boxes are aligned on one row and whose last is pinned to layer 3, on a page that is not wrapped."""

from vsdxkit.builder import Diagram, Edge, Node, Page
from vsdxkit.document import Document
from vsdxkit.layout import LayoutOptions

OPTIONS = LayoutOptions(page=None)


def page() -> Page:
    """The page, built with no coordinates."""
    nodes = [
        Node("top", "start", "Intake"),
        Node("left", "process", "Check"),
        Node("right", "process", "Review"),
        Node("bottom", "end", "Archive", layer=3),
    ]
    edges = [Edge("top", "left"), Edge("top", "right"), Edge("left", "bottom"), Edge("right", "bottom")]
    return Page("pins", nodes, edges, align=(("top", "bottom"),))


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    return Diagram("pins", [page()]).build(layout=OPTIONS)
