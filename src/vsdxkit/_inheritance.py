"""One marker for a row a shape inherits from its master.

A shape with a master reads through the master's rows. :class:`vsdxkit.geometry.Geometry`
merges the master's :class:`vsdxkit.geometry.GeometryRow` objects into its own, and
:attr:`vsdxkit.shapes.Shape.data_properties` merges the master's
:class:`vsdxkit.shapes.DataProperty` objects. Either way the object handed back holds the
*master page's* XML, so a setter that writes to it edits the master and changes
every other shape drawn from it.

:class:`InheritedRow` is what tells the two apart. A row merged down from a
master is flagged :attr:`inherited`, and a setter that calls :meth:`make_local`
before it writes materialises an override row on the instance and clears the
flag, leaving the master untouched. An override row on the instance is what
Visio itself writes. A row the shape already owns is written in place.

The coordinate setters of :class:`vsdxkit.geometry.GeometryRow` and
:class:`vsdxkit.geometry.Geometry` call it, as do the ``value``, ``formula``
and ``name`` setters of a :class:`vsdxkit.geometry.GeometryCell` in an
inherited row, and :attr:`vsdxkit.shapes.DataProperty.value`. Not every
setter does yet: :class:`vsdxkit.geometry.GeometryRow`'s ``row_type``,
``index`` and ``del_bool`` setters, and
:meth:`vsdxkit.shapes.DataProperty.set_attribute`, write the XML as it
stands, so on an inherited row they edit the master's row rather than the
instance's own (#273).
"""

from __future__ import annotations


class InheritedRow:
    """Mixin for a row that may still belong to a shape's master."""

    inherited: bool = False
    """Whether this row still belongs to a master, and so is shared with every other instance of it."""

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
