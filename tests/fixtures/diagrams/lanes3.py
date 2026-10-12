"""Case: a three-lane approval flow with a decision that splits into two lanes."""

from vsdxkit.builder import Diagram, Edge, Lane, Node, Page
from vsdxkit.document import Document

OPTIONS = None


def page() -> Page:
    """The page, built with no coordinates."""
    nodes = [
        Node("s1", "start", "Request"),
        Node("s2", "process", "Fill in form"),
        Node("s3", "process", "Check form"),
        Node("s4", "decision", "Complete?"),
        Node("s5", "process", "File it"),
        Node("s6", "process", "Return it"),
        Node("s7", "process", "Update register"),
        Node("s8", "end", "Done"),
    ]
    edges = [
        Edge("s1", "s2"),
        Edge("s2", "s3"),
        Edge("s3", "s4"),
        Edge("s4", "s5", "Approved", "yes-path"),
        Edge("s4", "s6", "Returned", "no-path"),
        Edge("s6", "s7"),
        Edge("s5", "s7"),
        Edge("s7", "s8"),
    ]
    lanes = [
        Lane("requester", "Requester", ["s1", "s2"]),
        Lane("reviewer", "Reviewer", ["s3", "s4", "s6"]),
        Lane("records", "Records", ["s5", "s7", "s8"]),
    ]
    return Page("lanes3", nodes, edges, lanes=lanes)


def build() -> Document:
    """The document the Visio harness is shown for this case."""
    return Diagram("lanes3", [page()]).build(layout=OPTIONS)
