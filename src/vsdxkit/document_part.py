"""The closed-document guard, reachable from any part of a document.

The guard belongs to the operation, not to the call sites that happen to reach
it. Issue #242 put it on :class:`vsdxkit.VisioFile` and :class:`vsdxkit.Page`; every
other mutator - a shape's text, a cell's value, a geometry row's coordinate, a
container's lane label - edited a closed document and returned normally,
because nothing else knew how to find the :class:`vsdxkit.VisioFile` to ask
(issue #329). A part answers :attr:`_document`, and guards itself with one line.

:class:`vsdxkit.Page` and :class:`vsdxkit.VisioFile` are not parts: a Page already
holds ``vis``, and the document is the thing being asked about.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vsdxkit.vsdxfile import VisioFile


class DocumentPart:
    @property
    def _document(self) -> VisioFile:
        """The VisioFile whose XML this part would change."""
        raise NotImplementedError

    def _require_open(self, operation: str) -> None:
        """Refuse ``operation`` on a closed document, whose result no save can reach."""
        self._document._require_open(operation)
