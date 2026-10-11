"""Case: the smallest and largest lanes and the narrowest diagram the creation is checked on, a process in the tall lane."""

from vsdxkit.document import Document
from vsdxkit.shape_kind import ShapeKind


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    document = Document.new(page_name="Lanes")
    page = document.pages[0]
    page.width, page.height = 7.0, 9.0
    diagram = page.create_swimlanes([("WW", 0.5), ("W" * 30, 6.0)], left=0.5, top=8.0, width=5.0)
    page.create_shape(ShapeKind.PROCESS, x=3.5, y=diagram.lanes[1].y or 0.0, text="Step")
    return document
