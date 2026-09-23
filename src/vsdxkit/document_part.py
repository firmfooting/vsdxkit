"""The closed-document guard, reachable from any part of a document.

The guard belongs to the operation, not to the call sites that happen to reach
it. Issue #242 put it on :class:`vsdxkit.vsdxfile.VisioFile` and :class:`vsdxkit.pages.Page`; every
other mutator - a shape's text, a cell's value, a geometry row's coordinate, a
container's lane label - edited a closed document and returned normally,
because nothing else knew how to find the :class:`vsdxkit.vsdxfile.VisioFile` to ask
(issue #329). A part answers :attr:`_document`, and guards itself with one line.

:class:`vsdxkit.pages.Page` and :class:`vsdxkit.vsdxfile.VisioFile` are not parts: a Page already
holds ``vis``, and the document is the thing being asked about.
"""

from __future__ import annotations

from typing import Protocol


class GuardedDocument(Protocol):
    """What a part needs from the document it belongs to: a refusal once it is closed."""

    def _require_open(self, operation: str) -> None: ...


class DocumentPart:
    @property
    def _document(self) -> GuardedDocument:
        """The document whose XML this part would change."""
        raise NotImplementedError

    def _require_open(self, operation: str) -> None:
        """Refuse ``operation`` on a closed document, whose result no save can reach."""
        self._document._require_open(operation)
