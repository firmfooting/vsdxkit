"""Case: a cross-functional flowchart of 3 lanes, 60 inches wide, on a page widened to hold it."""

from vsdxkit.document import Document
from vsdxkit.shape_kind import ShapeKind


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    document = Document.new(page_name="Lanes")
    page = document.pages[0]
    page.width, page.height = 61.0, 3 * 1.5 + 1.5
    diagram = page.create_swimlanes([(f"Lane {k}", 1.5) for k in range(1, 3 + 1)], left=0.5, top=3 * 1.5 + 1.0, width=60.0)
    for lane, x in zip(diagram.lanes, (4.0, 18.0, 31.0, 45.0, 57.0), strict=False):
        page.create_shape(ShapeKind.PROCESS, x=x, y=lane.y or 0.0, text=f"Step at {x:g}")
    return document
