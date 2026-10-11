"""A blank document from Document.new() with two shapes: the case Visio is asked to open for the template."""

from vsdxkit.document import Document
from vsdxkit.shape_kind import ShapeKind


def build() -> Document:
    """The document, built the way a caller would build it."""
    document = Document.new(page_name="Blank")
    page = document.pages[0]
    page.create_shape(ShapeKind.PROCESS, x=2.0, y=2.0, text="First")
    page.create_shape(ShapeKind.DECISION, x=5.0, y=2.0, text="Second")
    return document
