"""Case: a cross-functional flowchart made on a blank page by create_swimlanes, with one process in each lane."""

from vsdxkit.document import Document
from vsdxkit.shape_kind import ShapeKind


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    document = Document.new(page_name="Lanes")
    page = document.pages[0]
    page.width, page.height = 12.0, 8.0
    diagram = page.create_swimlanes([("Requester", 1.5), ("Reviewer", 2.0), ("Archive", 1.0)], left=0.5, top=7.0, width=10.0)
    for lane, x in zip(diagram.lanes, (3.0, 6.0, 9.0), strict=True):
        page.create_shape(ShapeKind.PROCESS, x=x, y=lane.y or 0.0, text=f"Step at {x:g}")
    return document


def style_checks(document: Document) -> tuple[tuple[int, str, float | str], ...]:
    """What Visio must show for each step: Shape Data from its master (so it is an instance), the heading of its lane, and the master's height."""
    page = document.pages[0]
    diagram = page.require_swimlanes()
    checks: list[tuple[int, str, float | str]] = []
    for step in (s for s in page.children if s.text and s.text.startswith("Step at")):
        lane = diagram.lane_for(step)
        assert lane is not None
        label = next(r for r in lane.xml.iter() if r.tag.endswith("}Row") and r.attrib.get("N") == "visHeadingText")[0].attrib[
            "V"
        ]
        checks += [(int(step.ID), "Prop.Function", label), (int(step.ID), "Height", 0.5905511811023622)]
    return tuple(checks)
