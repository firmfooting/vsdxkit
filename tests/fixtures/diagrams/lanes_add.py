"""Case: a created two-lane diagram with a lane added above it by add_lane, a process in each lane."""

from vsdxkit.document import Document
from vsdxkit.shape_kind import ShapeKind
from vsdxkit.swimlanes import LANE_PITCH_INCHES


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    document = Document.new(page_name="Lanes")
    page = document.pages[0]
    page.width, page.height = 12.0, 10.0
    diagram = page.create_swimlanes(
        [("Requester", LANE_PITCH_INCHES), ("Reviewer", LANE_PITCH_INCHES)], left=0.5, top=7.0, width=10.0
    )
    diagram.add_lane()  # a label would land on the band, not the heading (#337)
    for lane, x in zip(diagram.lanes, (3.0, 6.0, 9.0), strict=True):
        page.create_shape(ShapeKind.PROCESS, x=x, y=lane.y or 0.0, text=f"Step at {x:g}")
    return document
