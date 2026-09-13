"""Master-part import for vsdx documents.

Methods defined here are bound onto VisioFile at import time
(see vsdxfile._bind_extracted_support) so the public API is unchanged
while vsdxfile.py stays reviewable.
"""

from __future__ import annotations

import copy as copy_module
import io
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, cast

from vsdx import namespace, r_namespace

from . import relationships
from .logging_support import get_logger
from .pages import Page
from .shapes import Shape
from .xmlio import file_to_xml, xml_to_file

if TYPE_CHECKING:
    from .vsdxfile import VisioFile

logger = get_logger(__name__)


class MastersImportMixin:
    # attributes provided by the VisioFile host class
    zip_file_contents: dict[str, io.BytesIO]
    master_pages: list[Page]
    master_index: dict[str, Page]
    masters_xml: ET.Element | None
    directory: str

    @property
    def _masters_folder(self) -> str: ...
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
        if source_master_page is None or source_master_page.filename not in src_vis.zip_file_contents:
            return ""

        # 1. copy the master part bytes under the next free filename
        prefix = f"{self._masters_folder}/master"
        existing_numbers = [
            int(f[len(prefix) : -4])
            for f in self.zip_file_contents
            if f.startswith(prefix) and f.endswith(".xml") and f[len(prefix) : -4].isdigit()
        ]
        master_rels_path = f"{self._masters_folder}/_rels/masters.xml.rels"
        rels_tree = file_to_xml(master_rels_path, self.zip_file_contents)
        rels_root = rels_tree.getroot() if rels_tree is not None else None
        if rels_root is None:
            rels_root = ET.fromstring('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')

        # The part name is settled against the existing targets before the bytes
        # are written, and the rel id is allocated separately.
        taken_targets = {r.attrib.get("Target") for r in relationships.all_of(rels_root)}
        next_num = max(existing_numbers, default=0) + 1
        while f"master{next_num}.xml" in taken_targets:
            next_num += 1
        part_name = f"master{next_num}.xml"
        part_path = f"{self._masters_folder}/{part_name}"
        self.zip_file_contents[part_path] = src_vis.zip_file_contents[source_master_page.filename]

        # 2. ensure this document has a masters.xml to append to
        if self.masters_xml is None:
            self._bootstrap_masters()

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
        # persist masters.xml (save_vsdx does not write it)
        xml_to_file(ET.ElementTree(self.masters_xml), f"{self._masters_folder}/masters.xml", self.zip_file_contents)
        xml_to_file(ET.ElementTree(rels_root), master_rels_path, self.zip_file_contents)

        # 5. package wiring (helpers are idempotent); PartName paths are
        # archive-relative, never absolute
        self._add_content_types_override(
            part_name_path="/visio/masters/masters.xml", content_type="application/vnd.ms-visio.masters+xml"
        )
        self._add_content_types_override(
            part_name_path=f"/visio/masters/{part_name}", content_type="application/vnd.ms-visio.master+xml"
        )
        self._add_document_rel(
            rel_type="http://schemas.microsoft.com/visio/2010/relationships/masters", target="masters/masters.xml"
        )

        # 6. register the new master directly - a full load_master_pages()
        # reload would re-append every existing master to master_pages
        master_page_xml = file_to_xml(part_path, self.zip_file_contents)
        if master_page_xml is None:
            raise ValueError(f"imported master part {part_path} missing from package")
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
        """Create an empty masters part + wiring for documents without masters."""
        masters_root = ET.fromstring(
            '<Masters xmlns="http://schemas.microsoft.com/office/visio/2012/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
        )
        self.masters_xml = masters_root
        self.zip_file_contents[f"{self._masters_folder}/masters.xml"] = io.BytesIO(
            ET.tostring(masters_root, xml_declaration=True, encoding="UTF-8")
        )
        self.zip_file_contents[f"{self._masters_folder}/_rels/masters.xml.rels"] = io.BytesIO(
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
        )
        self._add_content_types_override(
            part_name_path="/visio/masters/masters.xml", content_type="application/vnd.ms-visio.masters+xml"
        )
        self._add_document_rel(
            rel_type="http://schemas.microsoft.com/visio/2010/relationships/masters", target="masters/masters.xml"
        )
