"""Case: a diagram wider than the default page, on a page the case widens to hold it."""

from vsdxkit.document import Document
from vsdxkit.shape_kind import ShapeKind


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    document = Document.new(page_name="Lanes")
    page = document.pages[0]
    page.width, page.height = 24.0, 7.0
    diagram = page.create_swimlanes([("Requester", 1.5), ("Reviewer", 2.0)], left=0.5, top=6.5, width=22.0)
    for lane, x in zip(diagram.lanes, (3.0, 18.0), strict=True):
        page.create_shape(ShapeKind.PROCESS, x=x, y=lane.y or 0.0, text=f"Step at {x:g}")
    return document
