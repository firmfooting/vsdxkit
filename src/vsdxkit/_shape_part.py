"""The detached-shape guard, reachable from any part of a shape.

A shape deleted from its page, or on a page removed from the document, is
detached (#101): its element is no longer in the package, so a write to it, or
to one of its cells, rows or properties, would change nothing that is saved.
A part answers :attr:`ShapePart._shape`, and guards itself with one line.
"""

from __future__ import annotations

from typing import Protocol


class AttachedShape(Protocol):
    """What a part needs from the shape it belongs to: a refusal once the shape is detached."""

    def _require_attached(self, operation: str) -> None:
        """Refuse `operation`, naming it, once the shape is no longer in its document."""
        ...


class ShapePart:
    """Mixin for any part of a shape - a cell, a row, a property - that guards its writes through `_shape`."""

    @property
    def _shape(self) -> AttachedShape:
        """The shape whose XML this part would change."""
        raise NotImplementedError

    def _require_attached(self, operation: str) -> None:
        """Refuse ``operation`` once the shape is no longer in its document."""
        self._shape._require_attached(operation)
