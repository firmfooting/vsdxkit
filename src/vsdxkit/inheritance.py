"""One marker for a row a shape inherits from its master.

A shape with a master reads through the master's rows. :class:`vsdxkit.Geometry`
merges the master's :class:`vsdxkit.GeometryRow` objects into its own, and
:attr:`vsdxkit.Shape.data_properties` merges the master's
:class:`vsdxkit.DataProperty` objects. Either way the object handed back holds the
*master page's* XML, so a setter that writes to it edits the master and changes
every other shape drawn from it.

:class:`InheritedRow` is what tells the two apart. A row merged down from a
master is flagged :attr:`inherited`, and every setter calls :meth:`make_local`
before it writes. That materialises an override row on the instance and clears
the flag, leaving the master untouched. An override row on the instance is what
Visio itself writes. A row the shape already owns is written in place.
"""

from __future__ import annotations


class InheritedRow:
    """Mixin for a row that may still belong to a shape's master."""

    inherited: bool = False

    def make_local(self) -> None:
        """Give this row to the instance if it still belongs to a master.

        Idempotent: a row that is already the instance's own is left alone, so
        a setter can call this unconditionally before every write.
        """
        if self.inherited:
            self._materialise()
            self.inherited = False

    def _materialise(self) -> None:
        """Create the override row on the instance and repoint ``xml`` at it."""
        raise NotImplementedError
