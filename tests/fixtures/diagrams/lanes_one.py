"""Case: a cross-functional flowchart of one lane, with a process in it."""

from vsdxkit.document import Document
from vsdxkit.shape_kind import ShapeKind


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    document = Document.new(page_name="Lanes")
    page = document.pages[0]
    page.width, page.height = 12.0, 6.0
    diagram = page.create_swimlanes([("Only lane", 3.0)], left=0.5, top=5.5, width=10.0)
    page.create_shape(ShapeKind.PROCESS, x=5.0, y=diagram.lanes[0].y or 0.0, text="Step")
    return document
