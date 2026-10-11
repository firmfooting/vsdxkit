"""Case: a shape copied from a document whose style 7 is another style than the destination's, so the master's styles are imported."""

from pathlib import Path

from vsdxkit.document import Document

SOURCE = Path(__file__).resolve().parents[2] / "test_master_multiple_child_shapes.vsdx"
"""A document whose master's sub-shapes take style 7, "Default Svg Style"; a blank document's 7 is "Connector"."""

SOURCE_SHEET_IDS = {"9", "10", "11"}
"""The master shapes that take style 7, which an instance's sub-shapes name by `MasterShape`."""


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    document = Document.new(page_name="Copy")
    next(iter(Document.open(SOURCE).pages[0].shapes)).copy(document.pages[0])
    return document


def style_checks(document: Document) -> tuple[tuple[int, str, float], ...]:
    """The cells Visio must show for the sub-shapes that take style 7.

    The wanted values are 0 for both cells.
    """
    shapes = [
        s for s in next(iter(document.pages[0].shapes)).descendants if s.xml.attrib.get("MasterShape") in SOURCE_SHEET_IDS
    ]
    return tuple((int(s.ID), cell, 0.0) for s in shapes for cell in ("LinePattern", "LeftMargin"))
