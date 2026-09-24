"""The built-in shapes :meth:`vsdxkit.pages.Page.create_shape` can create.

Each kind is a shape in one of the documents bundled with the library, and a
new one is a copy of it. Which document and which shape is private to
:mod:`vsdxkit.media`.
"""

from __future__ import annotations

from enum import Enum


class ShapeKind(Enum):
    """A built-in shape: the five basic flowchart shapes, and three plain ones."""

    PROCESS = "process"
    DECISION = "decision"
    START_END = "start_end"
    PARALLELOGRAM = "parallelogram"
    DATABASE = "database"
    RECTANGLE = "rectangle"
    CIRCLE = "circle"
    LINE = "line"
