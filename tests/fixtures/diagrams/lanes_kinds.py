"""Case: sized Start/End, Decision and Process steps in a created diagram, so every number they inherit is checked at the size given."""

from vsdxkit.document import Document
from vsdxkit.shape_kind import ShapeKind


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    document = Document.new(page_name="Lanes")
    page = document.pages[0]
    page.width, page.height = 12.0, 8.0
    diagram = page.create_swimlanes([("Requester", 2.0), ("Reviewer", 2.0)], left=0.5, top=7.0, width=10.0)
    top, bottom = diagram.lanes
    page.create_shape(ShapeKind.START_END, x=2.0, y=top.y or 0.0, width=2.4, height=0.8, text="Start")
    page.create_shape(ShapeKind.DECISION, x=5.5, y=top.y or 0.0, width=3.0, height=1.2, text="Approved?")
    page.create_shape(ShapeKind.PROCESS, x=3.0, y=bottom.y or 0.0, width=2.5, height=0.9, text="Review")
    page.create_shape(ShapeKind.START_END, x=8.0, y=bottom.y or 0.0, text="End")
    return document
