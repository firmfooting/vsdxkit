"""Case: a top-down flow whose edge enters a grouped node, so the connector must keep clear of the group's heading text."""

from vsdxkit.builder import Diagram, Edge, Group, Node, Page
from vsdxkit.document import Document
from vsdxkit.layout import LayoutOptions


def build() -> Document:
    """The document the Visio harness is shown for this case, built with no coordinates."""
    nodes = [Node("a", "process", "Start here"), Node("b", "process", "Inside the group")]
    page = Page("Heading", nodes, [Edge("a", "b")], groups=[Group("g", "G", ["b"])])
    return Diagram("Group heading", [page]).build(layout=LayoutOptions(direction="top_down"))
