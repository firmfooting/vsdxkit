"""The one owner of a document's masters: index, lookup, bootstrap and import.

A document's masters are `masters.xml`, its relationships part, one part per
master, and the wiring that makes the package declare them. `MasterCatalog`
holds all of it for one package. It never imports the document class: the
document hands it a factory for the `Page` each master is read as.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from xml.etree.ElementTree import Element

from vsdxkit import namespace, r_namespace, relationships
from vsdxkit.errors import MissingPartError
from vsdxkit.package import PackageStore, check_relationship_target
from vsdxkit.pages import Page
from vsdxkit.partnames import (
    CONTENT_TYPES_PART,
    DOCUMENT_PART,
    MASTERS_PART,
    folder_of,
    relationship_target,
    relationships_part_name,
    target_part_name,
)
from vsdxkit.xmlio import PartTree, require_attribute, require_element

MASTERS_RELATIONSHIP = "http://schemas.microsoft.com/visio/2010/relationships/masters"
MASTER_RELATIONSHIP = "http://schemas.microsoft.com/visio/2010/relationships/master"
MASTERS_CONTENT_TYPE = "application/vnd.ms-visio.masters+xml"
MASTER_CONTENT_TYPE = "application/vnd.ms-visio.master+xml"

# How a document reads one master as a page: the master part's tree, its part
# name, the master's name, its ID in masters.xml and its relationship id there.
MasterPageFactory = Callable[[PartTree, str, str, str, str], Page]


def _empty_relationships() -> PartTree:
    return ET.ElementTree(
        ET.fromstring('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
    )


def _master_name(master: Element) -> str:
    """The name a master is matched by: `NameU`, else `Name`, else "" for a master with neither."""
    return master.attrib.get("NameU") or master.attrib.get("Name") or ""


def _page_name(master: Element) -> str:
    """The name a master's page carries. A page cannot be nameless: `Page.name` would go looking in pages.xml."""
    return _master_name(master) or "Unknown"


class MasterCatalog:
    """Every master in one package, and the only code that changes them."""

    def __init__(self, store: PackageStore, make_page: MasterPageFactory) -> None:
        self._store = store
        self._make_page = make_page
        self._pages: list[Page] = []

    @property
    def pages(self) -> list[Page]:
        """The masters as pages, in `masters.xml` order. A copy: adding a master goes through the catalog."""
        return list(self._pages)

    @property
    def root(self) -> Element | None:
        """The `<Masters>` element, or None for a package with no masters part."""
        tree = self._store.read_xml(MASTERS_PART)
        return None if tree is None else tree.getroot()

    def by_id(self, master_id: str) -> Page | None:
        for page in self._pages:
            if page.page_id == master_id:
                return page
        return None

    def by_name(self, name: str) -> Page | None:
        """The first master whose `NameU` (or `Name`, where it has no `NameU`) is `name`."""
        for page in self._pages:
            if page.name == name:
                return page
        return None

    def element_by_id(self, master_id: str) -> Element | None:
        """The `<Master>` element with this ID."""
        root = self.root
        if root is None:
            return None
        for master in root:
            if master.attrib.get("ID") == master_id:
                return master
        return None

    def load(self) -> None:
        """Read every master from the package. Idempotent: it rebuilds rather than appends."""
        rels_tree = self._store.read_xml(relationships_part_name(MASTERS_PART))
        targets: dict[str, str] = {}
        for relationship in (
            [] if rels_tree is None else relationships.all_of(require_element(rels_tree.getroot(), "masters.xml.rels"))
        ):
            subject = "masters.xml.rels Relationship"
            targets[require_attribute(relationship, "Id", subject)] = require_attribute(relationship, "Target", subject)

        pages: list[Page] = []
        for master in [] if self.root is None else list(self.root):
            rel_id = require_attribute(
                require_element(master.find(f"{namespace}Rel"), "Master/Rel"), f"{r_namespace}id", "masters.xml Master/Rel"
            )
            target = targets.get(rel_id)
            if target is None:
                raise MissingPartError(f"no master part found for relationship {rel_id}")
            part_name = target_part_name(MASTERS_PART, target)
            check_relationship_target(part_name, f"masters.xml.rels Relationship {rel_id!r}", target)
            tree = self._store.read_xml(part_name)
            if tree is None:
                raise MissingPartError(f"expected XML part not found: master part ({part_name})")
            page = self._make_page(
                tree,
                part_name,
                _page_name(master),
                require_attribute(master, "ID", "masters.xml Master"),
                rel_id,
            )
            page.master_unique_id = master.attrib.get("UniqueID")
            page.master_base_id = master.attrib.get("BaseID")
            pages.append(page)
        self._pages = pages

    def bootstrap(self) -> None:
        """Give a package with no masters part an empty one, declared and related.

        The only bootstrap. A masters relationship can be declared while the
        parts behind it are missing, so each piece is written only when absent:
        replacing an existing `masters.xml.rels` would drop what it relates.
        """
        if self._store.part(MASTERS_PART) is None:
            self._store.write_xml(
                MASTERS_PART,
                ET.ElementTree(
                    ET.fromstring(
                        '<Masters xmlns="http://schemas.microsoft.com/office/visio/2012/main" '
                        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                        # Visio writes it on the masters part, and the part it bootstraps matches
                        'xml:space="preserve"/>'
                    )
                ),
            )
        rels_name = relationships_part_name(MASTERS_PART)
        if self._store.part(rels_name) is None:
            self._store.write_xml(rels_name, _empty_relationships())
        self._declare(MASTERS_PART, MASTERS_CONTENT_TYPE)
        relationships.append_if_absent(
            self._required_root(relationships_part_name(DOCUMENT_PART)),
            rel_type=MASTERS_RELATIONSHIP,
            target=relationship_target(DOCUMENT_PART, MASTERS_PART),
        )

    def import_masters(self, source: MasterCatalog, master_ids: Iterable[str]) -> dict[str, Page]:
        """This package's copy of each master `source` holds under `master_ids`, importing any it lacks.

        Keyed by the ID `source` uses. Masters match by name, as Visio's
        MatchByName does: numeric master IDs are per-document and coincide
        across documents by chance. A master with no name matches nothing and
        is always imported. An ID `source` cannot resolve is left out: copying
        it would name a master no package declares.

        Every source part is read before anything here changes, so a master
        that cannot be read leaves this package as it was.
        """
        found: dict[str, Page] = {}
        pending: list[tuple[str, Element, bytes]] = []
        first_by_name: dict[str, str] = {}
        aliases: dict[str, str] = {}
        for master_id in dict.fromkeys(master_ids):
            element = source.element_by_id(master_id)
            source_page = source.by_id(master_id)
            if element is None or source_page is None:
                continue
            name = _master_name(element)
            existing = self.by_name(name) if name else None
            if existing is not None:
                found[master_id] = existing
                continue
            if name in first_by_name:
                aliases[master_id] = first_by_name[name]
                continue
            if source._store.part(source_page.filename) is None:
                continue
            # The check above says the part is there, so None is a source
            # store contradicting itself; empty bytes in its place would be a
            # master part no reader can parse.
            master_bytes = source._store.read_bytes(source_page.filename)
            if master_bytes is None:
                raise MissingPartError(
                    f"source master part {source_page.filename} could not be read, though the package lists it"
                )
            pending.append((master_id, element, master_bytes))
            if name:
                first_by_name[name] = master_id

        if pending:
            self.bootstrap()
            rels_root = self._required_root(relationships_part_name(MASTERS_PART))
            for master_id, element, master_bytes in pending:
                found[master_id] = self._add(element, master_bytes, rels_root)
        for master_id, first in aliases.items():
            if first in found:
                found[master_id] = found[first]
        return found

    def _add(self, source_element: Element, master_bytes: bytes, rels_root: Element) -> Page:
        """Write one master part, declare and relate it, and record it."""
        part_name = self._unused_master_part(rels_root)
        self._store.write_bytes(part_name, master_bytes)

        masters_root = self.root
        assert masters_root is not None  # the caller bootstrapped
        numeric_ids = [int(m.attrib["ID"]) for m in masters_root if m.attrib.get("ID", "").isdigit()]
        new_id = str(max(max(numeric_ids, default=1) + 1, 2))
        relationship = relationships.append_if_absent(
            rels_root, rel_type=MASTER_RELATIONSHIP, target=relationship_target(MASTERS_PART, part_name)
        )
        element = copy.deepcopy(source_element)
        element.attrib["ID"] = new_id
        rel = element.find(f"{namespace}Rel")
        if rel is not None:
            rel.attrib[f"{r_namespace}id"] = relationship.attrib["Id"]
        masters_root.append(element)
        self._declare(part_name, MASTER_CONTENT_TYPE)

        tree = self._store.read_xml(part_name)
        if tree is None:
            raise MissingPartError(f"imported master part {part_name} missing from package")
        page = self._make_page(tree, part_name, _page_name(element), new_id, relationship.attrib["Id"])
        page.master_unique_id = element.attrib.get("UniqueID")
        page.master_base_id = element.attrib.get("BaseID")
        self._pages.append(page)
        return page

    def _unused_master_part(self, rels_root: Element) -> str:
        """The first `masterN.xml` neither the store nor `masters.xml.rels` already names."""
        prefix = folder_of(MASTERS_PART) + "master"
        taken = set(self._store.names())
        taken |= {target_part_name(MASTERS_PART, r.attrib.get("Target", "")) for r in relationships.all_of(rels_root)}
        number = 1
        while f"{prefix}{number}.xml" in taken:
            number += 1
        return f"{prefix}{number}.xml"

    def _declare(self, part_name: str, content_type: str) -> None:
        relationships.ensure_override(self._required_root(CONTENT_TYPES_PART), part_name, content_type)

    def _required_root(self, part_name: str) -> Element:
        tree = self._store.read_xml(part_name)
        if tree is None:
            raise MissingPartError(f"expected XML part not found: {part_name}")
        return require_element(tree.getroot(), f"{part_name} root")
