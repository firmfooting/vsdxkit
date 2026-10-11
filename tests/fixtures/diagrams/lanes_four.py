"""Case: four lanes, one labelled with the widest letters and one with a label as long as ordinary text allows, a process in each."""

from vsdxkit.document import Document
from vsdxkit.shape_kind import ShapeKind


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    document = Document.new(page_name="Lanes")
    page = document.pages[0]
    page.width, page.height = 12.0, 9.0
    diagram = page.create_swimlanes(
        [("Intake", 1.0), ("W" * 10, 2.0), ("Final check", 1.0), ("Archive", 1.0)], left=0.5, top=8.0, width=10.0
    )
    for lane, x in zip(diagram.lanes, (3.0, 5.0, 7.0, 9.0), strict=True):
        page.create_shape(ShapeKind.PROCESS, x=x, y=lane.y or 0.0, text=f"Step at {x:g}")
    return document
