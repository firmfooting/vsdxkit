"""Case: a cross-functional flowchart of five lanes, a process in each."""

from vsdxkit.document import Document
from vsdxkit.shape_kind import ShapeKind


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    document = Document.new(page_name="Lanes")
    page = document.pages[0]
    page.width, page.height = 12.0, 11.0
    diagram = page.create_swimlanes([(f"Lane {n}", 1.5) for n in range(1, 6)], left=0.5, top=10.5, width=10.0)
    for lane, x in zip(diagram.lanes, (2.0, 4.0, 6.0, 8.0, 9.0), strict=True):
        page.create_shape(ShapeKind.PROCESS, x=x, y=lane.y or 0.0, text=f"Step at {x:g}")
    return document
