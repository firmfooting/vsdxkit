"""Case: two lanes drawn by the builder, so the title bar carries the page name."""

from vsdxkit.builder import Diagram, Lane, Node, Page
from vsdxkit.document import Document


def build() -> Document:
    """The document the Visio harness is shown for this case, built with no coordinates."""
    nodes = [Node("a", "process", "Draft"), Node("b", "process", "Check")]
    lanes = [Lane("l1", "Requester", ["a"]), Lane("l2", "Reviewer", ["b"])]
    return Diagram("Title", [Page("Intake and review", nodes, lanes=lanes)]).build()
