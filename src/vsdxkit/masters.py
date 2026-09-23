"""Master-part import for vsdx documents.

Methods defined here are bound onto VisioFile at import time
(see vsdxfile._bind_extracted_support) so the public API is unchanged
while vsdxfile.py stays reviewable.
"""

from __future__ import annotations

import copy as copy_module
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, cast

from vsdxkit import namespace, r_namespace

from . import relationships
from .errors import MissingPartError
from .logging_support import get_logger
from .package import PackageStore
from .pages import Page
from .partnames import MASTERS_PART, folder_of, relationships_part_name, target_part_name
from .shapes import Shape

if TYPE_CHECKING:
    from .vsdxfile import VisioFile

logger = get_logger(__name__)


class MastersImportMixin:
    # attributes provided by the VisioFile host class
    _package: PackageStore
    master_pages: list[Page]
    master_index: dict[str, Page]
    masters_xml: ET.Element | None

    def _add_content_types_override(self, part_name_path: str, content_type: str) -> None: ...
    def _add_document_rel(self, rel_type: str, target: str) -> None: ...
    def load_master_pages(self) -> None: ...
    def _ensure_masters_for_shape(self, source_shape: Shape) -> str:
        """Ensure this document contains the master that source_shape uses.

        Call with the SOURCE shape (still attached to its original document)
        BEFORE copying it into this document. Master identity is by NAME
        (NameU), matching Visio's MatchByName semantics: numeric master IDs
        are per-document and coincide across documents by chance.

        :param source_shape: the shape in its source document
        :return: the logical master ID the copied shape should reference in
                 this document ('' when the shape references no master or the
                 source reference is dangling)
        """
        src_vis = source_shape.page.vis
        master_ref = source_shape.xml.attrib.get("Master")
        if not master_ref:
            return ""  # shape has no master - nothing to import
        src_masters = src_vis.masters_xml
        if src_masters is None or isinstance(src_masters, list):
            return ""  # source document has no masters part

        # locate the source Master element by numeric ID within the source doc
        source_element = None
        for m in src_masters:
            if m.attrib.get("ID") == master_ref:
                source_element = m
                break
        if source_element is None:
            return ""  # dangling reference - drop rather than corrupt

        master_name = source_element.attrib.get("NameU") or source_element.attrib.get("Name") or ""

        # already present in this document, by name?
        existing = self.master_index.get(master_name)
        if existing is not None:
            return existing.page_id

        source_master_page = src_vis.get_master_page_by_id(master_ref)
        if source_master_page is None or src_vis._package.part(source_master_page.filename) is None:
            return ""
        # read before anything here is changed, so a failure leaves this
        # package as it was. The check above says the part is there, so None
        # is a source store contradicting itself; writing empty bytes in its
        # place would make a master part no reader can parse.
        master_bytes = src_vis._package.read_bytes(source_master_page.filename)
        if master_bytes is None:
            raise MissingPartError(
                f"source master part {source_master_page.filename} could not be read, though the package lists it"
            )

        # 1. ensure this document has a masters.xml (and rels) to append to,
        # BEFORE resolving master_rels_path below. A masters relationship can
        # be declared in document.xml.rels with the masters parts themselves
        # missing (a crafted or partially-written package), so `masters_xml`
        # being None here is reachable through the public API, not only from
        # a freshly opened document. Bootstrapping after building a rels tree
        # of our own would have `_bootstrap_masters` write a second, empty
        # rels tree over the one just constructed, orphaning it and silently
        # dropping the relationship appended to it below.
        if self.masters_xml is None:
            self._bootstrap_masters()

        # 2. copy the master part bytes under the next free filename
        prefix = folder_of(MASTERS_PART) + "master"
        existing_numbers = [
            int(name[len(prefix) : -4])
            for name in self._package.names()
            if name.startswith(prefix) and name.endswith(".xml") and name[len(prefix) : -4].isdigit()
        ]
        master_rels_path = relationships_part_name(MASTERS_PART)
        rels_tree: ET.ElementTree[ET.Element] | None = self._package.read_xml(master_rels_path)
        if rels_tree is None:
            rels_tree = ET.ElementTree(
                ET.fromstring('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
            )
            self._package.write_xml(master_rels_path, rels_tree)
        rels_root = rels_tree.getroot()
        assert rels_root is not None  # freshly built above, or parsed from real bytes: always has a root

        # The part name is settled against the existing targets before the bytes
        # are written, and the rel id is allocated separately.
        taken_targets = {r.attrib.get("Target") for r in relationships.all_of(rels_root)}
        next_num = max(existing_numbers, default=0) + 1
        while f"master{next_num}.xml" in taken_targets:
            next_num += 1
        part_name = f"master{next_num}.xml"
        part_path = target_part_name(MASTERS_PART, part_name)
        self._package.write_bytes(part_path, master_bytes)

        # 3. append the Master element with a fresh logical ID
        assert self.masters_xml is not None  # bootstrap above guarantees it
        numeric_ids = [int(m.attrib["ID"]) for m in self.masters_xml if m.attrib.get("ID", "").isdigit()]
        new_id = max(numeric_ids, default=1) + 1
        if new_id < 2:
            new_id = 2
        new_master_element = copy_module.deepcopy(source_element)
        new_master_element.attrib["ID"] = str(new_id)

        # 4. masters.xml.rels: map a fresh rel id to the part filename
        relationship = relationships.append_if_absent(
            rels_root,
            rel_type="http://schemas.microsoft.com/visio/2010/relationships/master",
            target=part_name,
        )
        rel_el = new_master_element.find(f"{namespace}Rel")
        if rel_el is not None:
            rel_el.attrib[f"{r_namespace}id"] = relationship.attrib["Id"]
        self.masters_xml.append(new_master_element)
        # masters.xml and its rels are the store's own trees (promoted above,
        # or written by `_bootstrap_masters`), and appending to them mutates
        # what the store already holds -- there is nothing left to persist.

        # 5. package wiring (helpers are idempotent); PartName paths are
        # archive-relative, never absolute
        self._add_content_types_override(part_name_path=MASTERS_PART, content_type="application/vnd.ms-visio.masters+xml")
        self._add_content_types_override(part_name_path=part_path, content_type="application/vnd.ms-visio.master+xml")
        self._add_document_rel(
            rel_type="http://schemas.microsoft.com/visio/2010/relationships/masters", target="masters/masters.xml"
        )

        # 6. register the new master directly - a full load_master_pages()
        # reload would re-append every existing master to master_pages
        master_page_xml = self._package.read_xml(part_path)
        if master_page_xml is None:
            raise MissingPartError(f"imported master part {part_path} missing from package")
        new_master_page = Page(
            master_page_xml,
            part_path,
            master_name,
            str(new_id),
            relationship.attrib["Id"],
            cast("VisioFile", self),
        )
        new_master_page.master_unique_id = new_master_element.attrib.get("UniqueID")
        new_master_page.master_base_id = new_master_element.attrib.get("BaseID")
        self.master_pages.append(new_master_page)
        self.master_index[master_name] = new_master_page
        return str(new_id)

    def _bootstrap_masters(self):
        """Create an empty masters part + wiring for documents without masters.

        `masters.xml.rels` is written only when the package does not already
        have one. A masters relationship can be declared in document.xml.rels
        while only `masters.xml` itself is missing -- `masters_xml is None`
        does not imply the rels part is absent too -- and replacing an
        existing rels part here would discard whatever relationships it
        already held (issue found in review: `_ensure_masters_for_shape`
        calls this and then appends to a rels tree of its own; if this
        overwrote it unconditionally, that append would be lost).
        """
        masters_root = ET.fromstring(
            '<Masters xmlns="http://schemas.microsoft.com/office/visio/2012/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
        )
        # written as trees, not bytes literals (#366): the store holds both
        # from the moment this document gets masters, and `masters_xml`'s own
        # getter reads the tree straight back from it.
        self._package.write_xml(MASTERS_PART, ET.ElementTree(masters_root))
        master_rels_path = relationships_part_name(MASTERS_PART)
        if self._package.part(master_rels_path) is None:
            self._package.write_xml(
                master_rels_path,
                ET.ElementTree(
                    ET.fromstring('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
                ),
            )
        self._add_content_types_override(part_name_path=MASTERS_PART, content_type="application/vnd.ms-visio.masters+xml")
        self._add_document_rel(
            rel_type="http://schemas.microsoft.com/visio/2010/relationships/masters", target="masters/masters.xml"
        )
