"""Case: lanes of different heights, three processes in one lane, none in another."""

from vsdxkit.document import Document
from vsdxkit.shape_kind import ShapeKind


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    document = Document.new(page_name="Lanes")
    page = document.pages[0]
    page.width, page.height = 12.0, 9.0
    diagram = page.create_swimlanes([("Tall", 3.5), ("Empty", 0.8), ("Short", 1.5)], left=0.5, top=8.5, width=10.0)
    tall, _empty, short = diagram.lanes
    for x in (2.5, 5.0, 7.5):
        page.create_shape(ShapeKind.PROCESS, x=x, y=tall.y or 0.0, text=f"Step at {x:g}")
    page.create_shape(ShapeKind.PROCESS, x=5.0, y=short.y or 0.0, text="Last")
    return document
