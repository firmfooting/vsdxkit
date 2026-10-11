"""Case 1: one node of each kind in a chain, an edge of each kind, a long edge, a self-loop, and labels on edges and nodes."""

from vsdxkit.builder import Diagram, Edge, Node, Page
from vsdxkit.document import Document

KINDS = ("start", "process", "decision", "data_store", "external", "document", "subprocess", "off_page", "end")
"""Every node kind, in the order the case draws them."""


def build() -> Document:
    """The document the Visio harness is shown for this case, built with no coordinates."""
    nodes = [Node(f"n{i}", kind, f"Step {i}", sublabel="detail" if i % 2 else None) for i, kind in enumerate(KINDS)]
    edges = [
        Edge(f"n{i}", f"n{i + 1}", kind=k)
        for i, k in enumerate(["flow", "yes-path", "no-path", "data", "call", "flow", "flow", "flow"])
    ]
    edges += [Edge("n0", "n4", "skips three"), Edge("n3", "n3", "again")]
    return Diagram("Every kind", [Page("Kinds", nodes, edges)]).build()
