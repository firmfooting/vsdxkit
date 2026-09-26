"""The one owner of a document's masters: index, lookup, bootstrap and import.

A document's masters are `masters.xml`, its relationships part, one part per
master, and the wiring that makes the package declare them. `MasterCatalog`
holds all of it for one package. It never imports the document class: the
document hands it a factory for the `Page` each master is read as.
"""

from __future__ import annotations

import copy
import weakref
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from xml.etree.ElementTree import Element

from vsdxkit import namespace, r_namespace
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
from vsdxkit.relationships import all_of, append_if_absent, ensure_override
from vsdxkit.shape_tree import is_connector_element, iter_children, iter_descendants
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


def _identity(master: Element) -> str | None:
    """What makes two masters of one batch the same master, as `MasterCatalog.matching` would decide it.

    The `UniqueID` where there is one, else the name; a master with neither
    is like no other.
    """
    unique_id = master.attrib.get("UniqueID")
    if unique_id:
        return f"U{unique_id}"
    name = _master_name(master)
    return f"N{name}" if name else None


def _page_name(master: Element) -> str:
    """The name a master's page carries. A page cannot be nameless: `Page.name` would go looking in pages.xml."""
    return _master_name(master) or "Unknown"


class MasterCatalog:
    """Every master in one package, and the only code that changes them."""

    def __init__(self, store: PackageStore, make_page: MasterPageFactory) -> None:
        self._store = store
        self._make_page = make_page
        self._pages: list[Page] = []
        self._revision = 0
        # which master here each source master was imported as, by the
        # source's ID: an import renamed to avoid a collision no longer
        # matches by name, and would be imported again by every later copy
        self._imported: weakref.WeakKeyDictionary[MasterCatalog, dict[str, str]] = weakref.WeakKeyDictionary()
        # every wrapper a walk builds looks its master up by id; which page has
        # an id changes only when the revision does
        self._by_id: dict[str, Page] = {}
        self._by_id_revision = -1

    @property
    def pages(self) -> list[Page]:
        """The masters as pages, in `masters.xml` order. A copy: adding a master goes through the catalog."""
        return list(self._pages)

    @property
    def revision(self) -> int:
        """Counts the changes to which masters the catalog holds: every load and every master added.

        A master resolved while this is unchanged is still the master: IDs
        are never reused, and nothing else here adds, drops or replaces one.
        """
        return self._revision

    @property
    def root(self) -> Element | None:
        """The `<Masters>` element, or None for a package with no masters part."""
        tree = self._store.read_xml(MASTERS_PART)
        return None if tree is None else tree.getroot()

    def by_id(self, master_id: str) -> Page | None:
        if self._by_id_revision != self._revision:
            self._by_id = {}
            for page in self._pages:
                self._by_id.setdefault(page._page_id, page)
            self._by_id_revision = self._revision
        return self._by_id.get(master_id)

    def by_name(self, name: str) -> Page | None:
        """The first master whose `NameU` (or `Name`, where it has no `NameU`) is `name`."""
        for page in self._pages:
            if page.name == name:
                return page
        return None

    def matching(self, master: Element) -> Page | None:
        """The master here that an instance of `master`, from another document, would use.

        Visio's rule on a drop: the same `UniqueID` is the same master, and a
        document master that sets `MatchByName` answers for any master of its
        name. That flag is how every document shares one Dynamic connector.
        Otherwise a master of the same name is a different master. Where
        neither master carries a `UniqueID`, as some producers write them, the
        name is all there is to go on.
        """
        unique_id = master.attrib.get("UniqueID")
        name = _master_name(master)
        for page in self._pages:
            element = self.element_by_id(page._page_id)
            if element is None:
                continue
            if unique_id and element.attrib.get("UniqueID") == unique_id:
                return page
            if not name or _master_name(element) != name:
                continue
            if element.attrib.get("MatchByName") in ("1", "true"):
                return page
            if not unique_id and not element.attrib.get("UniqueID"):
                return page
        return None

    def is_one_d(self, master_id: str, master_shape_id: str | None) -> bool:
        """Whether the master shape an instance inherits from is 1-D: the master's top shape, or the one `master_shape_id` names.

        The master shape is looked up afresh on every call, and its cells read,
        so a master edited or replaced in place is seen at once.
        """
        element = self._find_shape_element(master_id, master_shape_id)
        return element is not None and is_connector_element(element)

    def _find_shape_element(self, master_id: str, master_shape_id: str | None) -> Element | None:
        page = self.by_id(master_id)
        root = None if page is None else page.xml.getroot()
        top = None if root is None else next(iter_children(root), None)
        if top is None or master_shape_id is None:
            return top
        if top.attrib.get("ID") == master_shape_id:
            return top
        return next((shape for shape in iter_descendants(top) if shape.attrib.get("ID") == master_shape_id), None)

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
        for relationship in [] if rels_tree is None else all_of(require_element(rels_tree.getroot(), "masters.xml.rels")):
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
            tree = self._store.require_xml(part_name)
            page = self._make_page(
                tree,
                part_name,
                _page_name(master),
                require_attribute(master, "ID", "masters.xml Master"),
                rel_id,
            )
            page._master_unique_id = master.attrib.get("UniqueID")
            pages.append(page)
        self._pages = pages
        self._revision += 1

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
        append_if_absent(
            self._required_root(relationships_part_name(DOCUMENT_PART)),
            rel_type=MASTERS_RELATIONSHIP,
            target=relationship_target(DOCUMENT_PART, MASTERS_PART),
        )

    def import_masters(self, source: MasterCatalog, master_ids: Iterable[str]) -> dict[str, Page]:
        """This package's copy of each master `source` holds under `master_ids`, importing any it lacks.

        Keyed by the ID `source` uses. A master matches as `matching` decides:
        numeric master IDs are per-document and coincide across documents by
        chance. One that matches nothing is imported, under a name of its own
        if this package already has a master of its name. Within one batch,
        masters `matching` would treat as one are imported once. An ID `source`
        cannot resolve is left out: copying it would name a master no package
        declares.

        Every source part is read before anything here changes, so a master
        that cannot be read leaves this package as it was.
        """
        found: dict[str, Page] = {}
        pending: list[tuple[str, Element, bytes]] = []
        first_by_identity: dict[str, str] = {}
        aliases: dict[str, str] = {}
        for master_id in dict.fromkeys(master_ids):
            element = source.element_by_id(master_id)
            source_page = source.by_id(master_id)
            if element is None or source_page is None:
                continue
            existing = self._imported_from(source, master_id) or self.matching(element)
            if existing is not None:
                found[master_id] = existing
                continue
            identity = _identity(element)
            if identity is not None and identity in first_by_identity:
                aliases[master_id] = first_by_identity[identity]
                continue
            if source._store.part(source_page._filename) is None:
                continue
            # The check above says the part is there, so None is a source
            # store contradicting itself; empty bytes in its place would be a
            # master part no reader can parse.
            master_bytes = source._store.read_bytes(source_page._filename)
            if master_bytes is None:
                raise MissingPartError(
                    f"source master part {source_page._filename} could not be read, though the package lists it"
                )
            pending.append((master_id, element, master_bytes))
            if identity is not None:
                first_by_identity[identity] = master_id

        if pending:
            self.bootstrap()
            rels_root = self._required_root(relationships_part_name(MASTERS_PART))
            for master_id, element, master_bytes in pending:
                found[master_id] = self._add(element, master_bytes, rels_root)
                self._imported.setdefault(source, {})[master_id] = found[master_id]._page_id
        for master_id, first in aliases.items():
            if first in found:
                found[master_id] = found[first]
        return found

    def _imported_from(self, source: MasterCatalog, master_id: str) -> Page | None:
        """The master here that `source`'s master `master_id` was imported as, while both are open."""
        imported = self._imported.get(source, {}).get(master_id)
        return None if imported is None else self.by_id(imported)

    def _add(self, source_element: Element, master_bytes: bytes, rels_root: Element) -> Page:
        """Write one master part, declare and relate it, and record it."""
        part_name = self._unused_master_part(rels_root)
        self._store.write_bytes(part_name, master_bytes)

        masters_root = self.root
        assert masters_root is not None  # the caller bootstrapped
        numeric_ids = [int(m.attrib["ID"]) for m in masters_root if m.attrib.get("ID", "").isdigit()]
        new_id = str(max(max(numeric_ids, default=1) + 1, 2))
        relationship = append_if_absent(
            rels_root, rel_type=MASTER_RELATIONSHIP, target=relationship_target(MASTERS_PART, part_name)
        )
        element = copy.deepcopy(source_element)
        element.attrib["ID"] = new_id
        taken = {
            master.attrib[attribute]
            for master in masters_root
            for attribute in ("NameU", "Name")
            if attribute in master.attrib
        }
        nameless = not _master_name(element)
        if nameless or _master_name(element) in taken:
            # Two masters of one name would leave a lookup by name answering
            # for the wrong one. The `.ID` suffix is how Visio's own duplicate
            # shape names read; what it does for masters is not yet checked.
            # A nameless master is named as Visio names one it creates. Counting
            # up from the new ID finds a suffix no name already has.
            names = (
                {"NameU": "Master", "Name": "Master"}
                if nameless
                else {attribute: element.attrib[attribute] for attribute in ("NameU", "Name") if attribute in element.attrib}
            )
            suffix = int(new_id)
            while any(f"{name}.{suffix}" in taken for name in names.values()):
                suffix += 1
            for attribute, name in names.items():
                element.attrib[attribute] = f"{name}.{suffix}"
        rel = element.find(f"{namespace}Rel")
        if rel is not None:
            rel.attrib[f"{r_namespace}id"] = relationship.attrib["Id"]
        masters_root.append(element)
        self._declare(part_name, MASTER_CONTENT_TYPE)

        tree = self._store.require_xml(part_name)
        page = self._make_page(tree, part_name, _page_name(element), new_id, relationship.attrib["Id"])
        page._master_unique_id = element.attrib.get("UniqueID")
        self._pages.append(page)
        self._revision += 1
        return page

    def _unused_master_part(self, rels_root: Element) -> str:
        """The first `masterN.xml` neither the store nor `masters.xml.rels` already names."""
        prefix = folder_of(MASTERS_PART) + "master"
        taken = set(self._store.names())
        taken |= {target_part_name(MASTERS_PART, r.attrib.get("Target", "")) for r in all_of(rels_root)}
        number = 1
        while f"{prefix}{number}.xml" in taken:
            number += 1
        return f"{prefix}{number}.xml"

    def _declare(self, part_name: str, content_type: str) -> None:
        ensure_override(self._required_root(CONTENT_TYPES_PART), part_name, content_type)

    def _required_root(self, part_name: str) -> Element:
        return require_element(self._store.require_xml(part_name).getroot(), f"{part_name} root")
