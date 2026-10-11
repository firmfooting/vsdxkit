"""Case: a diagram made in a document that has no style 7, so the Separator's styles are imported under the IDs it names."""

from vsdxkit.document import Document
from vsdxkit.shape_kind import ShapeKind


def _without_style_7(document: Document) -> None:
    """Number the document's style 7 as 9 and follow it in every reference, as a document made elsewhere might."""
    attributes = ("LineStyle", "FillStyle", "TextStyle")
    roots = [document._style_sheets(), *(master.xml.getroot() for master in document._masters.pages)]
    for root in roots:
        for element in root.iter():
            for attribute in attributes:
                if element.attrib.get(attribute) == "7":
                    element.attrib[attribute] = "9"
    for sheet in document._style_sheets():
        if sheet.attrib.get("ID") == "7":
            sheet.attrib["ID"] = "9"


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    document = Document.new(page_name="Lanes")
    _without_style_7(document)
    page = document.pages[0]
    page.width, page.height = 12.0, 8.0
    diagram = page.create_swimlanes([("Requester", 1.5), ("Reviewer", 2.0)], left=0.5, top=7.0, width=10.0)
    for lane, x in zip(diagram.lanes, (3.0, 6.0), strict=True):
        page.create_shape(ShapeKind.PROCESS, x=x, y=lane.y or 0.0, text=f"Step at {x:g}")
    return document


def style_checks(document: Document) -> tuple[tuple[int, str, str], ...]:
    """The style cells Visio must show for the Separator's sub-shapes: Flow Normal's 2 pt margins, where Connector's are 4 pt."""
    (separator,) = (s for s in document.pages[0].children if s.xml.attrib.get("NameU") == "Separator")
    return tuple((int(part.ID), "LeftMargin", "2.0000pt") for part in separator.descendants)
