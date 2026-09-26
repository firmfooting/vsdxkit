"""How a connector is glued and routed.

``page.connect(a, b, glue=..., routing=...)`` takes a :class:`Glue` and a
:class:`Routing`, and ``connector.retarget(..., options=...)`` takes all four
settings as one :class:`ConnectorOptions`. The cells and ``<Connect>``
records each choice writes are worked out inside the library, from Visio's
own formulas.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from vsdxkit.errors import InvalidOperationError


class Glue(Enum):
    """How a connector's ends attach to the shapes they name."""

    DYNAMIC = "dynamic"
    """Shape glue: the end walks round the shape to the nearest side."""

    POINT = "point"
    """Glue to one row of the shape's ``Connection`` section."""


class Routing(Enum):
    """The path a connector takes between its ends."""

    DEFAULT = "default"
    """Visio's own: dynamic glue reroutes at right angles, point glue stays straight."""

    STRAIGHT = "straight"
    RIGHT_ANGLE = "rightangle"
    CURVED = "curved"


@dataclass(frozen=True)
class ConnectorOptions:
    """How a connector is glued and routed.

    ``from_point`` and ``to_point`` are 0-based rows of each shape's
    ``Connection`` section, and are read only when ``glue`` is
    :attr:`Glue.POINT`.
    """

    glue: Glue = Glue.DYNAMIC
    routing: Routing = Routing.DEFAULT
    from_point: int = 0
    to_point: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.glue, Glue):
            raise TypeError(f"glue must be a Glue, not {self.glue!r}")
        if not isinstance(self.routing, Routing):
            members = ", ".join(f"Routing.{member.name}" for member in Routing)
            raise TypeError(f"routing must be one of {members}, not {self.routing!r}")
        for point in (self.from_point, self.to_point):
            if type(point) is not int or point < 0:
                raise InvalidOperationError(f"a connection point is a 0-based row index, not {point!r}")

    def end_point(self, *, begin: bool) -> int | None:
        """The connection point one end glues to, or ``None`` for dynamic glue."""
        if self.glue is Glue.DYNAMIC:
            return None
        return self.from_point if begin else self.to_point
