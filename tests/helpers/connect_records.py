"""A page's ``<Connect>`` records, read straight from its XML.

The records are internal to vsdxkit: 1.0 exposes :class:`Connector` and its
graph queries instead. Tests that check what a connection, a retarget or a
deletion leaves in the package read the records here, without the library.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import NamedTuple, Protocol

NS = "{http://schemas.microsoft.com/office/visio/2012/main}"


class _Page(Protocol):
    @property
    def xml(self) -> ET.ElementTree: ...


class _Shape(Protocol):
    @property
    def ID(self) -> str | None: ...

    @property
    def page(self) -> _Page: ...


class Record(NamedTuple):
    """One ``<Connect>`` element: which end of which connector is glued to what."""

    from_id: str | None
    from_rel: str | None
    to_id: str | None
    to_rel: str | None
    xml: ET.Element


def page_records(page: _Page) -> list[Record]:
    """Every ``<Connect>`` record on the page, in document order."""
    return [
        Record(
            element.attrib.get("FromSheet"),
            element.attrib.get("FromCell"),
            element.attrib.get("ToSheet"),
            element.attrib.get("ToCell"),
            element,
        )
        for element in page.xml.getroot().iter(f"{NS}Connect")
    ]


def records_naming(shape: _Shape) -> list[Record]:
    """The records that name the shape on either side: as the connector, or as what it is glued to."""
    return [record for record in page_records(shape.page) if shape.ID in (record.from_id, record.to_id)]


def unglue(page: _Page, connector_id: str | None) -> None:
    """Remove every record leading from the connector, leaving it glued at neither end."""
    for connects in page.xml.getroot().iter(f"{NS}Connects"):
        for element in [e for e in connects if e.attrib.get("FromSheet") == connector_id]:
            connects.remove(element)
