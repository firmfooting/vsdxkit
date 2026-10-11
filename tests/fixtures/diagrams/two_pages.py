"""Case 3: two pages joined by a page link between off-page nodes."""

from vsdxkit.builder import Diagram, Edge, Node, Page
from vsdxkit.document import Document


def build() -> Document:
    """The document the Visio harness is shown for this case, built with no coordinates."""
    one = Page(
        "Start",
        [Node("a", "start", "Begin"), Node("b", "process", "Work"), Node("out", "off_page", "Continue")],
        [Edge("a", "b"), Edge("b", "out"), Edge("out", "in", kind="page-link")],
    )
    two = Page(
        "Finish",
        [Node("in", "off_page", "From start"), Node("c", "process", "More work"), Node("z", "end", "Done")],
        [Edge("in", "c"), Edge("c", "z")],
    )
    return Diagram("Pages", [one, two]).build()
