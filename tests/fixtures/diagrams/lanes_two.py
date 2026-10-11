"""Case: a cross-functional flowchart of two lanes, a process in each."""

from vsdxkit.document import Document
from vsdxkit.shape_kind import ShapeKind


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    document = Document.new(page_name="Lanes")
    page = document.pages[0]
    page.width, page.height = 12.0, 7.0
    diagram = page.create_swimlanes([("Requester", 2.0), ("Reviewer", 2.0)], left=0.5, top=6.5, width=10.0)
    for lane, x in zip(diagram.lanes, (3.0, 7.0), strict=True):
        page.create_shape(ShapeKind.PROCESS, x=x, y=lane.y or 0.0, text=f"Step at {x:g}")
    return document
