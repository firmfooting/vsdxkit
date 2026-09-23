from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .errors import NotFoundError, VisioFileNotOpen
from .shapes import Shape
from .vsdxfile import VisioFile


def _media_path(filename: str) -> str:
    """Path to a bundled media vsdx in the module-adjacent 'media' folder."""
    return str(Path(__file__).resolve().parent / "media" / filename)


class Media:
    straight_connector_text = "STRAIGHT_CONNECTOR"
    curved_connector_text = "CURVED_CONNECTOR"
    rectangle_text = "RECTANGLE"
    circle_text = "CIRCLE"

    def __init__(self) -> None:
        self._closed = False
        self._media_vsdx: VisioFile | None = None
        self._palette_vsdx: VisioFile | None = None

    def _require_open(self) -> None:
        """Refuse to reopen a donor once close() has run.

        Reopening on demand was the same leak `VisioFile._shared_media` used to
        have one layer up: the owner has already let go, so nothing is left
        holding the replacement to close it (issue #242).
        """
        if self._closed:
            raise VisioFileNotOpen("the bundled media documents have been closed")

    @property
    def media(self) -> VisioFile:
        """The sentinel media document."""
        self._require_open()
        if self._media_vsdx is None:
            self._media_vsdx = VisioFile(_media_path("media.vsdx"))
        return self._media_vsdx

    @property
    def palette(self) -> VisioFile:
        """The extended shape palette (sentinel-text shapes: PALETTE_PROCESS,
        PALETTE_DECISION, PALETTE_START_END, PALETTE_PARALLELOGRAM,
        PALETTE_DATABASE)."""
        self._require_open()
        if self._palette_vsdx is None:
            self._palette_vsdx = VisioFile(_media_path("palette_extended.vsdx"))
        return self._palette_vsdx

    def close(self) -> None:
        self._closed = True
        if self._media_vsdx is not None:
            self._media_vsdx.close_vsdx()
            self._media_vsdx = None
        if self._palette_vsdx is not None:
            self._palette_vsdx.close_vsdx()
            self._palette_vsdx = None

    def _sentinel(self, text: str) -> Shape:
        """The media shape carrying a given sentinel text.

        A missing sentinel means the bundled media.vsdx is wrong, so fail loudly
        rather than handing callers a None shape.
        """
        shape = self.media.pages[0].find_shape_by_text(text)
        if shape is None:
            raise NotFoundError(f"media document has no shape with sentinel text {text!r}")
        return shape

    @property
    def rels_xml(self) -> ET.ElementTree[ET.Element] | None:
        return self.media.pages[0].rels_xml

    @property
    def straight_connector(self) -> Shape:
        return self._sentinel(Media.straight_connector_text)

    @property
    def curved_connector(self) -> Shape:
        return self._sentinel(Media.curved_connector_text)

    @property
    def rectangle(self) -> Shape:
        return self._sentinel(Media.rectangle_text)

    @property
    def circle(self) -> Shape:
        return self._sentinel(Media.circle_text)
