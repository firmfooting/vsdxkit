"""The built-in shapes :meth:`vsdxkit.pages.Page.create_shape` can create.

Each kind is a shape in one of the documents bundled with the library, and a
new one is a copy of it. Which document and which shape is private to
the library.
"""

from __future__ import annotations

from enum import Enum


class ShapeKind(Enum):
    """A built-in shape: the five basic flowchart shapes, and three plain ones."""

    PROCESS = "process"
    """A rectangle, 2 inches by 1 unless sized: one step of a flowchart."""
    DECISION = "decision"
    """A diamond, 3 inches by 2 unless sized: a flowchart's decision, with a point to branch from on each side."""
    START_END = "start_end"
    """A rectangle with its corners rounded to a 0.25-inch radius, 2 inches by 1 unless sized: where a flowchart starts or ends."""
    PARALLELOGRAM = "parallelogram"
    """A parallelogram leaning to the right, 2.8 inches by 1 unless sized: a flowchart's input or output."""
    DATABASE = "database"
    """A rectangle with its corners rounded to a 0.5-inch radius, 2 inches by 1 unless sized, a size at which its ends are semicircles: a flowchart's data store."""
    RECTANGLE = "rectangle"
    """A plain rectangle, about 2.17 inches by 1.57 unless sized."""
    CIRCLE = "circle"
    """An ellipse about 1.14 inches wide and 1.18 high unless sized: give an equal ``width`` and ``height`` for a true circle."""
    LINE = "line"
    """A straight horizontal line, about 1.18 inches long unless sized: a 1-D shape, created as a :class:`~vsdxkit.shapes.Connector` whose ``width`` is its length."""
