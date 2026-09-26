from __future__ import annotations

import copy
import logging
import os
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from logging import Logger
from pathlib import Path
from typing import NamedTuple
from xml.etree.ElementTree import Element

from vsdxkit import (
    cont_types_namespace,
    ext_prop_namespace,
    namespace,
    r_namespace,
    vt_namespace,
)
from vsdxkit.errors import InvalidOperationError, MalformedPackageError, MissingPartError
from vsdxkit.logging_support import get_logger
from vsdxkit.masters import MasterCatalog
from vsdxkit.media import MEDIA, _connector_shape, _kind_shape, _style_copy
from vsdxkit.package import PackageLimits, PackageStore, XmlPart, check_relationship_target
from vsdxkit.pages import Page, PageCollection, _DocumentSeam, _PagePosition
from vsdxkit.partnames import (
    APP_PART,
    CONTENT_TYPES_PART,
    DOCUMENT_PART,
    MASTERS_PART,
    PAGES_PART,
    relationships_part_name,
    target_part_name,
)
from vsdxkit.relationships import append_if_absent, ensure_override, remove, remove_override
from vsdxkit.shape_kind import ShapeKind
from vsdxkit.shapes import Connector, Shape
from vsdxkit.templating import render_document
from vsdxkit.xmlio import (
    PartTree,
    adopt_prefixes,
    pretty_print_element,
    register_namespaces,
    require_attribute,
    require_element,
    require_tree,
)

logger: Logger = get_logger(__name__)

register_namespaces()


def _page_part_taken(taken: set[str], filename: str) -> bool:
    """Whether a page part called `filename`, or the relationships part it would have, is already in `taken`."""
    part_name = target_part_name(PAGES_PART, filename)
    return part_name in taken or relationships_part_name(part_name) in taken


# The main document part's content type, not the file extension, is what tells
# a consumer whether a package carries macros. Visio reports a package whose
# extension and content type disagree as corrupt, so the two must be kept in
# step on save.
MACRO_ENABLED_CONTENT_TYPE = "application/vnd.ms-visio.drawing.macroEnabled.main+xml"
DRAWING_CONTENT_TYPE = "application/vnd.ms-visio.drawing.main+xml"
_SUFFIX_BY_CONTENT_TYPE = {MACRO_ENABLED_CONTENT_TYPE: ".vsdm", DRAWING_CONTENT_TYPE: ".vsdx"}


class Document:
    """A Visio drawing, ``.vsdx`` or ``.vsdm``, read whole into memory.

    Open one with :meth:`open`. The package is read before ``open`` returns and
    no file is held, so there is nothing to close; :meth:`save` is the only
    write.
    """

    def __init__(self, package: PackageStore, filename: str) -> None:
        """Wrap a package already read into memory. Use :meth:`open` to open a file."""
        self._filename = filename
        # the raw part XML (`_pages_xml`, `_app_xml` and the rest) is a set of
        # store-backed properties, defined below -- there is nothing to
        # initialise here, since the store itself is the state.
        self._package = package
        self._pages: list[Page] = []
        self._load_pages()
        self._masters = MasterCatalog(self._package, self._master_page)
        self._masters.load()
        if logger.isEnabledFor(logging.DEBUG):
            for master in self._masters.pages:
                logger.debug("Master(%s, id=%s)\n%s", master._filename, master._page_id, pretty_print_element(master.xml))

    @classmethod
    def open(
        cls,
        source: str | os.PathLike[str],
        *,
        limits: PackageLimits | None = None,
        limits_path: str | os.PathLike[str] | None = None,
    ) -> Document:
        """Open the drawing at ``source``, a ``.vsdx`` or ``.vsdm`` file.

        :param limits: package expansion caps; the defaults suit untrusted documents
        :param limits_path: a JSON file with the same keys as the
            :class:`~vsdxkit.package.PackageLimits` fields, read in place of ``limits``
        :raises TypeError: if ``source`` does not name a ``.vsdx`` or ``.vsdm`` file
        """
        filename = os.fspath(source)
        logger.debug("Document.open(%s)", filename)
        suffix = filename.rsplit(".", 1)[-1]
        if suffix.lower() not in ("vsdx", "vsdm"):
            raise TypeError(f"Invalid File Type:{suffix}")
        if limits_path is not None:
            limits = PackageLimits.from_json_file(os.fspath(limits_path))
        return cls(PackageStore.open(filename, limits=limits if limits is not None else PackageLimits()), filename)

    @property
    def filename(self) -> str:
        """The path this document was opened from, as it was given to :meth:`open`.

        Read-only: ``save()`` with no target writes back over this file. To
        write somewhere else, name the destination: ``document.save(target)``.
        """
        return self._filename

    @staticmethod
    def _part_root(tree: PartTree | None, description: str) -> ET.Element:
        """Root element of a required document part.

        A missing part means the package is malformed for the operation being
        attempted, so raise with the part name rather than failing on None.
        """
        return require_element(require_tree(tree, description).getroot(), f"{description} root")

    def _set_part_xml(self, name: str, tree: PartTree | None) -> None:
        """Make `tree` the part called `name`, or take the part out for None.

        Handing back the tree the store already holds is not a change, and
        writing it would throw away the baseline that lets an untouched part
        save as the bytes it arrived as.
        """
        held = self._package.part(name)
        if tree is None:
            if held is not None:
                self._package.remove(name)
            return
        if isinstance(held, XmlPart) and held.tree is tree:
            return
        # a replacement keeps the part's arrival baseline, so one that means
        # what the part already meant still saves as the bytes it arrived as
        self._package.replace_tree(name, tree)

    def _set_document_part_xml(self, attribute: str, name: str, tree: PartTree | None) -> None:
        """`_set_part_xml` for a part the document itself is wired to, which None may not remove.

        `app.xml`, `document.xml`, `pages.xml` and the rest are each named by a
        relationship and described by a content-type override. Taking one out
        of the store leaves both behind, and the saved package promises a part
        it does not hold. A page's rels part is different -- nothing points at
        it -- so `Page._rels_xml = None` still removes it, through
        `_set_part_xml` directly.
        """
        if tree is None:
            raise InvalidOperationError(
                f"Document.{attribute} cannot remove {name} through this property: this "
                f"property does not also remove the relationship and content-type override "
                f"that name a document part, so setting it to None would leave the package "
                f"inconsistent"
            )
        self._set_part_xml(name, tree)

    @property
    def _pages_xml(self) -> PartTree | None:
        return self._package.read_xml(PAGES_PART)

    @_pages_xml.setter
    def _pages_xml(self, tree: PartTree | None) -> None:
        self._set_document_part_xml("_pages_xml", PAGES_PART, tree)

    @property
    def _pages_xml_rels(self) -> PartTree | None:
        return self._package.read_xml(relationships_part_name(PAGES_PART))

    @_pages_xml_rels.setter
    def _pages_xml_rels(self, tree: PartTree | None) -> None:
        self._set_document_part_xml("_pages_xml_rels", relationships_part_name(PAGES_PART), tree)

    @property
    def _content_types_xml(self) -> PartTree | None:
        return self._package.read_xml(CONTENT_TYPES_PART)

    @_content_types_xml.setter
    def _content_types_xml(self, tree: PartTree | None) -> None:
        self._set_document_part_xml("_content_types_xml", CONTENT_TYPES_PART, tree)

    @property
    def _app_xml(self) -> PartTree | None:
        return self._package.read_xml(APP_PART)

    @_app_xml.setter
    def _app_xml(self, tree: PartTree | None) -> None:
        self._set_document_part_xml("_app_xml", APP_PART, tree)

    @property
    def _document_xml(self) -> PartTree | None:
        return self._package.read_xml(DOCUMENT_PART)

    @_document_xml.setter
    def _document_xml(self, tree: PartTree | None) -> None:
        self._set_document_part_xml("_document_xml", DOCUMENT_PART, tree)

    @property
    def _document_xml_rels(self) -> PartTree | None:
        return self._package.read_xml(relationships_part_name(DOCUMENT_PART))

    @_document_xml_rels.setter
    def _document_xml_rels(self, tree: PartTree | None) -> None:
        self._set_document_part_xml("_document_xml_rels", relationships_part_name(DOCUMENT_PART), tree)

    @property
    def _masters_xml(self) -> ET.Element | None:
        """The `<Masters>` root, read from the store so it can never be a stale copy."""
        tree = self._package.read_xml(MASTERS_PART)
        return None if tree is None else tree.getroot()

    @_masters_xml.setter
    def _masters_xml(self, root: ET.Element | None) -> None:
        if root is None:
            self._set_document_part_xml("_masters_xml", MASTERS_PART, None)  # raises: see there
            return
        # asked of the part as held rather than through `read_xml`: whether the
        # root is already the part's own needs no parse, and promoting the part
        # here would make assigning over bytes that are not XML raise
        held = self._package.part(MASTERS_PART)
        if isinstance(held, XmlPart) and held.tree.getroot() is root:
            return
        self._set_document_part_xml("_masters_xml", MASTERS_PART, ET.ElementTree(root))

    def _master_page(self, tree: PartTree, part_name: str, name: str, master_id: str, rel_id: str) -> Page:
        """The page a master is read as; the factory this document hands its catalog."""
        return Page(tree, part_name, name, master_id, rel_id, self)

    @property
    def master_pages(self) -> list[Page]:
        """Every master, as a page, in `masters.xml` order."""
        return self._masters.pages

    @property
    def master_index(self) -> dict[str, Page]:
        """Every master by name, e.g. 'Dynamic connector'. Where two masters share a name, the first wins."""
        index: dict[str, Page] = {}
        for page in self._masters.pages:
            index.setdefault(page.name, page)
        return index

    def load_master_pages(self) -> None:
        """Re-read the masters from the package. Idempotent."""
        self._masters.load()

    def _master_revision(self) -> int:
        """The catalog's :attr:`MasterCatalog.revision`: a master resolved at one count holds until the next."""
        return self._masters.revision

    def _master_is_one_d(self, master_id: str, master_shape_id: str | None) -> bool:
        """Whether the master shape an instance inherits from is 1-D; see :meth:`MasterCatalog.is_one_d`."""
        return self._masters.is_one_d(master_id, master_shape_id)

    def _master_page_by_id(self, id: str) -> Page | None:
        """The master page with this ID, as :attr:`Shape.master_page_ID` names it, or None."""
        return self._masters.by_id(id)

    def _masters_for(self, master_ids: list[str], source: _DocumentSeam) -> dict[str, Page]:
        """This document's master for each of `master_ids`, as `source` numbers its masters.

        From another document, a master this one lacks is imported, and listed
        in app.xml's TitlesOfParts. A document without app.xml, or whose app.xml
        lists no titles, has none to keep in step (#385): both are optional. The
        section is resolved before anything changes, so an app.xml it cannot
        be found in stops the import cleanly. An ID `source` cannot resolve is
        left out.

        :raises TypeError: if ``source`` is not a :class:`Document`; every page's document is one
        """
        if source is self:
            return {master_id: master for master_id in master_ids if (master := self._masters.by_id(master_id)) is not None}
        if not isinstance(source, Document):
            raise TypeError(f"expected a vsdxkit Document, got {type(source).__name__}")
        lists_titles = self._lists_titles()
        if lists_titles:
            self._titles_of_parts_section(self._MASTERS, self._page_titles())
        known = {page._page_id for page in self._masters.pages}
        masters = self._masters.import_masters(source._masters, master_ids)
        for master in masters.values():
            if lists_titles and master._page_id not in known:
                self._titles_of_parts_insert(master.name, self._MASTERS)
                known.add(master._page_id)
        return masters

    def _load_pages(self) -> None:
        rels_name = relationships_part_name(PAGES_PART)
        pages_xml_rels = self._package.require_xml(rels_name)
        rels = require_element(pages_xml_rels.getroot(), "pages.xml.rels")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Relationships(%s)\n%s", rels_name, pretty_print_element(rels))
        relid_page_dict = {}

        for rel in rels:
            rel_id = require_attribute(rel, "Id", "pages.xml.rels Relationship")
            page_file = require_attribute(rel, "Target", f"pages.xml.rels Relationship {rel.attrib.get('Id', '')!r}")
            relid_page_dict[rel_id] = page_file

        # pages.xml contains Page name, width, height, mapped to Id
        pages_xml = self._package.require_xml(PAGES_PART)
        pages = require_element(pages_xml.getroot(), "pages.xml")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Pages(%s)\n%s", PAGES_PART, pretty_print_element(pages))

        for page in pages:  # type: Element
            rel_id = require_attribute(
                require_element(page.find(f"{namespace}Rel"), "Page/Rel"), f"{r_namespace}id", "pages.xml Page/Rel"
            )
            page_name = require_attribute(page, "Name", "pages.xml Page")

            page_file = relid_page_dict.get(rel_id)
            if page_file is None:
                raise MissingPartError(f"no page part found for relationship {rel_id}")
            page_path = target_part_name(PAGES_PART, page_file)
            check_relationship_target(page_path, f"pages.xml.rels Relationship {rel_id!r}", page_file)
            page_id = page.attrib.get("ID", "")

            new_page = Page(self._package.require_xml(page_path), page_path, page_name, page_id, rel_id, self)
            # look for /visio/pages/_rels/page3.xml.rels
            page_rels_path = relationships_part_name(page_path)

            if self._package.part(page_rels_path) is not None:
                new_page._rels_xml_filename = page_rels_path
                # past the setter: the document is not open yet, which the
                # setter refuses, and the tree is the store's own, so there is
                # nothing for it to write through
                new_page._rels_tree = self._package.read_xml(page_rels_path)
            self._pages.append(new_page)

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Page(%s)\n%s", new_page._filename, pretty_print_element(new_page.xml))

        # `_content_types_xml`, `_app_xml`, `_document_xml` and
        # `_document_xml_rels` are store-backed properties, but promoted here
        # rather than left to the first later access: a part promoted at load
        # is an `XmlPart` from the moment the document opens, which is what
        # lets a caller compare the store's own identity for a part it has not
        # yet touched (app.xml, in particular, may simply be missing, and
        # promoting a missing part is just None), and a part that is not
        # well-formed XML fails the open itself, with a `PartParseError`,
        # rather than the first access to it.
        self._package.read_xml(CONTENT_TYPES_PART)
        self._package.read_xml(APP_PART)
        self._package.read_xml(DOCUMENT_PART)
        self._package.read_xml(relationships_part_name(DOCUMENT_PART))
        # TODO: add correctness cross-check. Or maybe the other way round, start from [Content_Types].xml
        #       to get page_dir and other paths...

    @property
    def pages(self) -> PageCollection:
        """The document's pages, in order: see :class:`PageCollection`."""
        return PageCollection(self._pages, self)

    def _remove_page_by_index(self, index: int) -> None:
        """Remove zero-based nth page from Document object

        :param index: Zero-based index of the page
        :type index: int

        :return: None
        """

        # remove Page element from pages.xml file - zero based index
        if isinstance(index, int):
            pages_root = self._part_root(self._pages_xml, "pages.xml")
            page = pages_root.find(f"{namespace}Page[{index + 1}]")
            if isinstance(page, Element):
                pages_root.remove(page)
                page = self.pages[index]  # type: Page

                # remove internal references to page
                self._remove_page_from_app_xml(page.name)

                # issue #7: a dangling rId pointing at a deleted part corrupts
                # the OPC graph, and so does an Override naming one
                remove(self._part_root(self._pages_xml_rels, "pages.xml.rels"), page._rel_id or "")
                remove_override(
                    self._part_root(self._content_types_xml, "[Content_Types].xml"),
                    page._filename,
                )

                # remove the page's own rels part if one exists
                if page._rels_xml_filename and self._package.part(page._rels_xml_filename) is not None:
                    self._package.remove(page._rels_xml_filename)

                # remove page<index>.xml file
                self._package.remove(self.pages[index]._filename)
                del self._pages[index]

    def _update_pages_xml_rels(self, new_page_filename: str) -> str:
        """Updates the pages.xml.rels file with a reference to the new page and returns the new relid"""

        rels_root = self._part_root(self._pages_xml_rels, "pages.xml.rels")
        relationship = append_if_absent(
            rels_root,
            rel_type="http://schemas.microsoft.com/visio/2010/relationships/page",
            target=new_page_filename,
        )
        return relationship.attrib["Id"]

    def _get_new_page_name(self, new_page_name: str) -> str:
        i = 1
        while new_page_name in [page.name for page in self.pages]:
            new_page_name = f"{new_page_name}-{i}"  # Page-X-i
            i += 1

        return new_page_name

    def _unused_page_part_name(self) -> str:
        """Return an unused ``pageN.xml`` part name (issue #7).

        Deriving the name from page count collides after a removal: two pages
        could target the same part. Members currently in the package and
        relationships still declared in pages.xml.rels are both treated as
        taken, so the chosen name is unused by either.

        A name is taken when either ``pageN.xml`` or its rels part
        ``_rels/pageN.xml.rels`` exists. An orphan rels part with no page part
        of its own is otherwise invisible to this check -- it sits at a
        different member name than the one being tested -- so a new page
        reusing ``pageN.xml`` would find the store already holding a part at
        its rels name. `Page._rels_attached()` treats that as not the page's
        own tree and refuses to write over it, so the new page's `_rels_xml`
        assignment becomes a silent no-op.
        """
        taken = set(self._package.names())
        rels_root = self._part_root(self._pages_xml_rels, "pages.xml.rels")
        taken.update(target_part_name(PAGES_PART, rel.attrib["Target"]) for rel in rels_root)
        counter = 1
        while _page_part_taken(taken, f"page{counter}.xml"):
            counter += 1
        return f"page{counter}.xml"

    def _get_max_page_id(self) -> int:
        pages_root = self._part_root(self._pages_xml, "pages.xml")
        page_with_max_id = max(pages_root, key=lambda page: int(page.attrib["ID"]))
        max_page_id = int(page_with_max_id.attrib["ID"])

        return max_page_id

    def _get_index(self, *, index: int | _PagePosition, page: Page | None) -> int:
        """Where a new page goes: `index` itself, or the place the position names.

        :raises ValueError: for `AFTER` with no page to go after
        """
        if not isinstance(index, _PagePosition):
            return index
        if index is _PagePosition.LAST:
            return len(self.pages)
        if page is None:
            raise ValueError(f"{index!r} requires a reference page; pass the source page to position relative to")
        return self.pages.index(page) + 1

    def _add_content_types_override(self, part_name_path: str, content_type: str) -> None:
        ensure_override(self._part_root(self._content_types_xml, "[Content_Types].xml"), part_name_path, content_type)

    def _style_sheets(self) -> Element:
        # return StyleSheets element from document.xml
        root = self._part_root(self._document_xml, "document.xml")
        return require_element(root.find(f"{namespace}StyleSheets"), "document.xml StyleSheets")

    def _get_style_by_id(self, ID: str) -> Element | None:
        return self._style_sheets().find(f"{namespace}StyleSheet[@ID = '{ID}']")

    def _kind_source(self, kind: ShapeKind) -> Shape:
        """The bundled shape `kind` is copied from; see :mod:`vsdxkit.media`."""
        return _kind_shape(kind, Document.open)

    def _copy_connector(self, page: Page) -> Connector:
        """A copy of the bundled dynamic connector on `page`, one of this document's pages.

        The copy imports the connector's master, whether or not this document
        has masters yet, and relates the page to it (#375). Its sentinel text
        is cleared, and the line style its master names is imported unless
        this document already has a style with that ID.
        """
        connector = _connector_shape(Document.open).copy(page)
        if not isinstance(connector, Connector):
            raise MalformedPackageError(f"the bundled connector in {MEDIA} is not a 1-D shape")
        connector.text = ""  # the sentinel text it was found by
        master_shape = connector.master_shape
        line_style_id = master_shape.line_style_id if master_shape is not None else None
        # a style with the same ID is taken to be the same style
        if line_style_id is not None and self._get_style_by_id(line_style_id) is None:
            style = _style_copy(line_style_id, Document.open)
            if style is not None:
                self._style_sheets().append(style)
        return connector

    def _heading_pairs(self) -> Element:
        # return HeadingPairs element from app.xml
        root = self._part_root(self._app_xml, "docProps/app.xml")
        return require_element(root.find(f"{ext_prop_namespace}HeadingPairs"), "app.xml HeadingPairs")

    def _lists_titles(self) -> bool:
        """Whether app.xml lists this document's parts by title, in sections a new title can be counted in.

        app.xml, its TitlesOfParts and its HeadingPairs are each optional.
        Without HeadingPairs no title belongs to a section, so there is no
        section for a new one to join.
        """
        if self._app_xml is None:
            return False
        root = self._part_root(self._app_xml, "docProps/app.xml")
        titles = root.find(f"{ext_prop_namespace}TitlesOfParts")
        has_titles = titles is not None and titles.find(f"{vt_namespace}vector") is not None
        return has_titles and root.find(f"{ext_prop_namespace}HeadingPairs") is not None

    def _titles_of_parts(self) -> Element:
        # return TitlesOfParts element from app.xml
        root = self._part_root(self._app_xml, "docProps/app.xml")
        return require_element(root.find(f"{ext_prop_namespace}TitlesOfParts"), "app.xml TitlesOfParts")

    class _Section(NamedTuple):
        """One section of TitlesOfParts.

        `label` is what Visio writes in English, and what we write when the
        section has to be created. It cannot be the only handle: HeadingPairs
        names are display strings chosen by the producer and Office localises
        them -- a German Excel writes `Arbeitsblätter` for `Worksheets` -- so a
        German file says `Seiten` and matching "Pages" finds nothing.

        `is_pages` says which section this is in terms the file cannot
        translate, which is what `_resolve_section` falls back on.
        """

        label: str
        is_pages: bool

    _PAGES = _Section("Pages", is_pages=True)
    _MASTERS = _Section("Masters", is_pages=False)

    def _heading_pairs_list(self) -> list[tuple[str, Element]]:
        """Each section HeadingPairs names, as (name, the element holding its count).

        HeadingPairs is a flat vector of variants holding a name and then a
        count, and that order is what cuts TitlesOfParts into sections: where
        one section's titles begin is the sum of every count written before it.

        The count is taken from the variant after the name rather than from an
        even/odd position in the vector, so one variant that is neither leaves
        every section after it where it was. This is the only reading of
        HeadingPairs in the package, and it yields the element rather than the
        number so that writing a count does not need a second one. Two readings
        is how a count came to be read from a section that was not there and
        written to one that was.
        """
        variants = self._heading_pairs().findall(f".//{vt_namespace}variant")
        pairs: list[tuple[str, Element]] = []
        for position, variant in enumerate(variants[:-1]):
            name = variant.find(f".//{vt_namespace}lpstr")
            count = variants[position + 1].find(f".//{vt_namespace}i4")
            if name is not None and count is not None:
                pairs.append((name.text or "", count))
        return pairs

    def _resolve_section(self, section: _Section, page_titles: set[str]) -> int | None:
        """Which HeadingPairs entry is `section`, or None if the file has no such entry.

        By name first, so a document that writes its sections in an unusual
        order is still read correctly.

        When the name misses, position is not a safe answer. A document naming
        only Masters has it at position 0, and a localised document names it
        something we would not recognise either -- so "the first section" would
        claim the masters and put page titles among them, which is worse than
        reporting the section missing, since that at least gets one created.

        What the producer cannot translate is the titles themselves. The pages
        section is the one naming this document's pages, so it is found by
        asking which section's titles those are. The masters section is then
        whatever the other one is, where there are two.
        """
        pairs = self._heading_pairs_list()
        for index, (name, _) in enumerate(pairs):
            if name == section.label:
                return index
        pages_index = self._section_naming_the_pages(pairs, page_titles)
        if section.is_pages:
            return pages_index
        if len(pairs) == 2 and pages_index is not None:
            return 1 - pages_index
        return None

    def _page_titles(self) -> set[str]:
        """The titles app.xml should be holding for this document's pages right now."""
        return {page.name for page in self.pages}

    def _section_naming_the_pages(self, pairs: list[tuple[str, Element]], page_titles: set[str]) -> int | None:
        """Which section's titles are this document's page names, or None if none are.

        Overlap rather than equality, because a caller is usually part-way
        through changing one of them: an added page is not in app.xml yet, and a
        renamed one is still there under its old title. A caller that knows
        which title is in flight passes the titles app.xml should be holding,
        rather than letting that difference count as a miss.

        A tie is not an answer. A master may be called what a page is called, so
        on a one-page document a masters section can score exactly what the
        pages section scores, and taking the first is how a page title ends up
        among the masters. Nothing here can tell those apart, so nothing here
        pretends to: the section reports missing and the caller creates one,
        which is recoverable in a way that writing into the wrong section is
        not.
        """
        vector = self._titles_of_parts().find(f"{vt_namespace}vector")
        if vector is None or not page_titles:
            return None
        scores: list[int] = []
        start = 0
        for _, count in pairs:
            titles_here = int(count.text or 0)
            stop = min(start + titles_here, len(vector))
            scores.append(sum(1 for at in range(min(start, len(vector)), stop) if vector[at].text in page_titles))
            start += titles_here
        best = max(scores, default=0)
        if best == 0 or scores.count(best) > 1:
            return None
        return scores.index(best)

    def _titles_of_parts_section(self, section: _Section, page_titles: set[str]) -> tuple[Element, int | None, int, int]:
        """The TitlesOfParts vector, which HeadingPairs entry `section` is, and the ``[start, stop)`` slice it owns.

        A section HeadingPairs does not mention owns the empty slice at the end
        of the vector: it has no titles yet, and the first one it gets belongs
        after every title already spoken for.

        The slice stops at the end of the vector however large the counts are.
        They come from whatever wrote the file, and a count read as a position
        is a count that can point past the last title there is. Only the slice
        is clipped: the count itself is the file's to keep.

        The entry comes back with the slice so that a caller changing the
        vector counts the change against the section it changed. Resolving it
        again afterwards reads a vector the counts no longer cut the way they
        did, and on a localised document that can find a different section or
        none.
        """
        vector = require_element(self._titles_of_parts().find(f"{vt_namespace}vector"), "TitlesOfParts vector")
        total = len(vector)
        wanted = self._resolve_section(section, page_titles)
        if wanted is None:
            return vector, None, total, total
        start = 0
        for index, (_, count) in enumerate(self._heading_pairs_list()):
            titles_here = int(count.text or 0)
            if index == wanted:
                return vector, wanted, min(start, total), min(start + titles_here, total)
            start += titles_here
        return vector, None, total, total

    def _section_count(self, section: _Section, index: int | None, change: int) -> None:
        """Add `change` to the count of HeadingPairs entry `index`, creating `section`'s pair if it is None.

        The stored count is what moves, not the length of the slice it turned
        out to name: a section reporting more titles than the vector holds
        still knows how many parts it has, and re-deriving the number from
        where the titles ended up would throw that away.

        `index` is taken rather than found: the caller resolved it before
        changing the vector, which is the only time the answer is reliable.
        """
        if index is None:
            self._set_app_xml_value(section.label, str(change))
            return
        count = self._heading_pairs_list()[index][1]
        count.text = str(int(count.text or 0) + change)

    def _titles_of_parts_insert(self, title: str, section: _Section, page_titles: set[str] | None = None) -> None:
        """Name a part in TitlesOfParts under `section`, and count it there.

        The title goes at the end of its own section rather than the end of the
        vector. Appending a page title to a document that has masters puts it
        past the Pages/Masters boundary, where it names the last master and
        every master name after the boundary slides onto the wrong master.

        A part the section already names is left alone. The one caller that
        needs that made the check itself, against every title in the document
        rather than this section's, so a page called the same thing as the
        master being added stopped the master being listed at all.
        """
        titles = self._page_titles() if page_titles is None else page_titles
        vector, index, start, stop = self._titles_of_parts_section(section, titles)
        if any(vector[position].text == title for position in range(start, stop)):
            return
        entry = Element(f"{vt_namespace}lpstr")
        entry.text = title
        vector.insert(stop, entry)
        vector.attrib["size"] = str(len(vector))
        self._section_count(section, index, 1)

    def _titles_of_parts_remove(self, title: str, section: _Section, page_titles: set[str] | None = None) -> None:
        """Drop `section`'s entry for `title`, and stop counting it.

        The count moves only when an entry does, and only this section's
        entries are candidates: a page and a master can be called the same
        thing, and the one being removed is the one in this section.
        """
        titles = self._page_titles() if page_titles is None else page_titles
        vector, index, start, stop = self._titles_of_parts_section(section, titles)
        for position in range(start, stop):
            if vector[position].text == title:
                del vector[position]
                vector.attrib["size"] = str(len(vector))
                self._section_count(section, index, -1)
                return

    def _titles_of_parts_rename(self, old_title: str, new_title: str, section: _Section, page_titles: set[str]) -> None:
        """Rewrite `section`'s entry for `old_title` in place.

        In place rather than a removal and an insertion: nothing joins or
        leaves the section, so neither its count nor the order of its titles
        has any business changing.
        """
        vector, _, start, stop = self._titles_of_parts_section(section, page_titles)
        for position in range(start, stop):
            if vector[position].text == old_title:
                vector[position].text = new_title
                return

    def _set_app_xml_value(self, name: str, value: str) -> None:
        for section, count in self._heading_pairs_list():
            if section == name:
                count.text = value
                return
        # no matching variant found - so create new item and populate it
        vector = require_element(
            self._heading_pairs().find(f".//{vt_namespace}vector"), "HeadingPairs vector"
        )  # new variant appended to vector Element
        name_variant = Element(f"{vt_namespace}variant", {})
        lpstr = Element(f"{vt_namespace}lpstr", {})
        lpstr.text = name
        name_variant.append(lpstr)
        vector.append(name_variant)
        i4_variant = Element(f"{vt_namespace}variant", {})
        i4 = Element(f"{vt_namespace}i4", {})
        i4.text = value
        i4_variant.append(i4)
        vector.append(i4_variant)
        # add two to vector size, as we have added two new variant elements
        vector.attrib["size"] = str(int(vector.attrib.get("size", 0)) + 2)

    def _add_page_to_app_xml(self, new_page_name: str) -> None:
        self._titles_of_parts_insert(new_page_name, Document._PAGES)

    def _remove_page_from_app_xml(self, page_name: str) -> None:
        if self._app_xml is not None:
            logger.debug("_remove_page_from_app_xml()")
            self._titles_of_parts_remove(page_name, Document._PAGES)

    def _rename_page_in_app_xml(self, old_page_name: str, new_page_name: str) -> None:
        """Keep app.xml's list of page names in step with a page that was renamed.

        Adding or removing a page writes a part into the package, and app.xml
        not being shaped like app.xml is then a broken document. A rename
        writes nothing, so a document whose metadata never listed the parts is
        left as it is rather than made to raise over a property assignment.
        """
        if self._app_xml is None:
            return
        root = self._part_root(self._app_xml, "docProps/app.xml")
        if root.find(f"{ext_prop_namespace}HeadingPairs") is None:
            return
        if root.find(f"{ext_prop_namespace}TitlesOfParts") is None:
            return
        # app.xml still lists the old title and the page already carries the new
        # one, so the titles to look for are today's with that swap undone. On a
        # one-page document nothing else identifies the section.
        expected = (self._page_titles() - {new_page_name}) | {old_page_name}
        self._titles_of_parts_rename(old_page_name, new_page_name, Document._PAGES, expected)

    def _create_page(
        self,
        *,
        new_page_xml_str: str,
        page_name: str,
        new_page_element: Element,
        index: int | _PagePosition,
        source_page: Page | None = None,
        new_page_filename: str,
        new_page_relid: str,
    ) -> Page:
        # Create visio\pages\pageX.xml file
        # Add to visio\pages\_rels\pages.xml.rels (done by the caller, which
        # also allocates the part name and relationship id)
        # Add to visio\pages\pages.xml
        # Add to [Content_Types].xml
        # Add to docProps\app.xml

        # create pageX.xml
        new_page_root = ET.fromstring(new_page_xml_str)
        if source_page is not None:
            # a copied page reaches here as a string, which drops the prefixes
            # its source declared; the copy is still the same page
            adopt_prefixes(new_page_root, require_element(source_page.xml.getroot(), "source page root"))
        new_page_xml: PartTree = ET.ElementTree(new_page_root)
        new_page_path = target_part_name(PAGES_PART, new_page_filename)

        # update pages.xml - insert the PageElement Element in it's correct location
        index = self._get_index(index=index, page=source_page)
        self._part_root(self._pages_xml, "pages.xml").insert(index, new_page_element)

        # update [Content_Types].xml - insert reference to the new page
        self._add_content_types_override(new_page_path, "application/vnd.ms-visio.page+xml")

        # update app.xml, if it exists
        if self._app_xml:
            self._add_page_to_app_xml(page_name)

        # Update Document object; the page carries its real ID and relationship
        # id immediately (issue #7: they were blank until a reload)
        page_id = new_page_element.attrib["ID"]
        # written into the store before the Page is constructed, so `Page.xml`'s
        # write-through guard (`_attached()`) already finds the page's own tree
        # at its part name for any later assignment, and because this call is
        # what gets the new page into the package at all: a save writes the
        # store and nothing else
        self._package.write_xml(new_page_path, new_page_xml)
        new_page = Page(new_page_xml, new_page_path, page_name, page_id, new_page_relid, self)
        if source_page is not None and source_page._rels_xml is not None:
            source_rels_root = require_element(source_page._rels_xml.getroot(), "source page relationships root")
            # the filename first: the `_rels_xml` setter only writes through
            # when `_rels_xml_filename` is already set (and the page's own
            # tree, above, is already its part)
            new_page._rels_xml_filename = relationships_part_name(new_page_path)
            new_page._rels_xml = ET.ElementTree(copy.deepcopy(source_rels_root))

        self._pages.insert(index, new_page)  # insert new page at defined index

        return new_page

    def _add_page_at(self, index: int, name: str | None = None) -> Page:
        """Add a new page at the specified index of the Document

        :param index: zero-based index where the new page will be placed
        :type index: int

        :param name: The name of the new page
        :type name: str, optional

        :return: :class:`Page` object representing the new page
        """

        # Determine the new page's name
        new_page_name = self._get_new_page_name(name or f"Page-{len(self.pages) + 1}")

        # Resolve the position before any package mutation so a rejected call
        # (BEFORE/AFTER without a reference page) leaves the document unchanged
        index = self._get_index(index=index, page=None)

        # Determine the new page's filename
        new_page_filename = self._unused_page_part_name()

        # Add reference to the new page in pages.xml.rels and get new relid
        new_page_relid = self._update_pages_xml_rels(new_page_filename)

        # Create default empty page xml
        # TODO: figure out the best way to define this default pagesheet XML
        # For example, python-docx has a 'template.docx' file which is copied.
        new_pagesheet_attribs = {"FillStyle": "0", "LineStyle": "0", "TextStyle": "0"}
        new_pagesheet_element = Element(f"{namespace}PageSheet", new_pagesheet_attribs)
        new_pagesheet_element.append(Element(f"{namespace}Cell", {"N": "PageWidth", "V": "8.26771653543307"}))
        new_pagesheet_element.append(Element(f"{namespace}Cell", {"N": "PageHeight", "V": "11.69291338582677"}))
        new_pagesheet_element.append(Element(f"{namespace}Cell", {"N": "ShdwOffsetX", "V": "0.1181102362204724"}))
        new_pagesheet_element.append(Element(f"{namespace}Cell", {"N": "ShdwOffsetY", "V": "-0.1181102362204724"}))
        new_pagesheet_element.append(Element(f"{namespace}Cell", {"N": "PageScale", "U": "MM", "V": "0.03937007874015748"}))
        new_pagesheet_element.append(Element(f"{namespace}Cell", {"N": "DrawingScale", "U": "MM", "V": "0.03937007874015748"}))
        new_pagesheet_element.append(Element(f"{namespace}Cell", {"N": "DrawingSizeType", "V": "0"}))
        new_pagesheet_element.append(Element(f"{namespace}Cell", {"N": "DrawingScaleType", "V": "0"}))
        new_pagesheet_element.append(Element(f"{namespace}Cell", {"N": "InhibitSnap", "V": "0"}))
        new_pagesheet_element.append(Element(f"{namespace}Cell", {"N": "PageLockReplace", "U": "BOOL", "V": "0"}))
        new_pagesheet_element.append(Element(f"{namespace}Cell", {"N": "PageLockDuplicate", "U": "BOOL", "V": "0"}))
        new_pagesheet_element.append(Element(f"{namespace}Cell", {"N": "UIVisibility", "V": "0"}))
        new_pagesheet_element.append(Element(f"{namespace}Cell", {"N": "ShdwType", "V": "0"}))
        new_pagesheet_element.append(Element(f"{namespace}Cell", {"N": "ShdwObliqueAngle", "V": "0"}))
        new_pagesheet_element.append(Element(f"{namespace}Cell", {"N": "ShdwScaleFactor", "V": "1"}))
        new_pagesheet_element.append(Element(f"{namespace}Cell", {"N": "DrawingResizeType", "V": "1"}))
        new_pagesheet_element.append(Element(f"{namespace}Cell", {"N": "PageShapeSplit", "V": "1"}))

        new_page_attribs = {
            "ID": str(self._get_max_page_id() + 1),
            "NameU": new_page_name,
            "Name": new_page_name,
        }
        new_page_element = Element(f"{namespace}Page", new_page_attribs)
        new_page_element.append(new_pagesheet_element)

        new_page_rel = {"{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id": new_page_relid}
        new_page_element.append(Element(f"{namespace}Rel", new_page_rel))

        # create the new page
        new_page = self._create_page(
            new_page_xml_str=f"<?xml version='1.0' encoding='utf-8' ?><PageContents xmlns='{namespace[1:-1]}' xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships' xml:space='preserve'/>",
            page_name=new_page_name,
            new_page_element=new_page_element,
            index=index,
            new_page_filename=new_page_filename,
            new_page_relid=new_page_relid,
        )

        return new_page

    def _copy_page(self, page: Page, *, index: int | _PagePosition = _PagePosition.AFTER, name: str | None = None) -> Page:
        """Copy an existing page and insert in Document

        :param page: the page to copy
        :type page: Page
        :param index: the specific int or relation _PagePosition location for new page
        :type index: int | _PagePosition
        :param name: name of new page (note this may be altered if name already exists)
        :type name: str

        :return: the newly created page
        """
        # Determine the new page's name
        new_page_name = self._get_new_page_name(name or page.name)

        # Determine the new page's filename
        new_page_filename = self._unused_page_part_name()

        # Add reference to the new page in pages.xml.rels and get new relid
        new_page_relid = self._update_pages_xml_rels(new_page_filename)

        # Copy the source page and update relevant attributes
        pages_root = self._part_root(self._pages_xml, "pages.xml")
        page_element = require_element(
            pages_root.find(f"{namespace}Page[@Name='{page.name}']"), f"pages.xml Page named {page.name}"
        )
        new_page_element = ET.fromstring(ET.tostring(page_element))

        new_page_element.attrib["ID"] = str(self._get_max_page_id() + 1)
        new_page_element.attrib["NameU"] = new_page_name
        new_page_element.attrib["Name"] = new_page_name
        require_element(new_page_element.find(f"{namespace}Rel"), "Page/Rel").attrib[
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        ] = new_page_relid

        # create the new page
        new_page = self._create_page(
            new_page_xml_str=ET.tostring(require_element(page.xml.getroot(), "page root"), encoding="unicode"),
            page_name=new_page_name,
            new_page_element=new_page_element,
            index=index,
            source_page=page,
            new_page_filename=new_page_filename,
            new_page_relid=new_page_relid,
        )

        return new_page

    def _main_part_content_type(self) -> str:
        """The declared content type of `/visio/document.xml`."""
        content_types = self._part_root(self._content_types_xml, "[Content_Types].xml")
        overrides = content_types.findall(f"{cont_types_namespace}Override")
        for override in overrides:
            if override.attrib.get("PartName") == DOCUMENT_PART:
                return override.attrib.get("ContentType", "")
        # an unusual package may name the main part differently; fall back to
        # whichever override declares a Visio main document content type
        for override in overrides:
            content_type = override.attrib.get("ContentType", "")
            if content_type in _SUFFIX_BY_CONTENT_TYPE:
                return content_type
        return ""

    @property
    def is_macro_enabled(self) -> bool:
        """Whether this package declares the macro-enabled main document part."""
        return self._main_part_content_type() == MACRO_ENABLED_CONTENT_TYPE

    def _check_destination_kind(self, filename: str) -> str | None:
        """Refuse a filename whose Visio extension contradicts the package kind.

        Renaming a .vsdm to .vsdx leaves `visio/vbaProject.bin` and the
        macro-enabled content type in place, and Visio reports the result as
        corrupt. Stripping the macros instead is a separate, larger job.

        Returns the Visio extension the name already carries, or None when it
        carries neither, so the caller can decide whether to append one.
        """
        macro_enabled = self.is_macro_enabled
        expected = ".vsdm" if macro_enabled else ".vsdx"
        lowered = filename.lower()
        # matched by ending, not splitext, so a name that is nothing but a
        # suffix keeps the historical behaviour of having one appended
        given = next((suffix for suffix in (".vsdm", ".vsdx") if lowered.endswith(suffix)), None)
        if given is None or given == expected:
            return given
        if macro_enabled:
            raise InvalidOperationError(
                f"cannot save a macro-enabled package as {filename!r}: it declares "
                f"{MACRO_ENABLED_CONTENT_TYPE} and still contains its vbaProject part, so it must be saved "
                "with a .vsdm extension"
            )
        raise InvalidOperationError(
            f"cannot save {filename!r}: the .vsdm extension is for macro-enabled packages, and this "
            f"package declares {self._main_part_content_type() or DRAWING_CONTENT_TYPE}"
        )

    def _destination_filename(self, new_filename: str) -> str:
        """Resolve a named save destination, appending the matching extension if absent."""
        if self._check_destination_kind(new_filename) is not None:
            return new_filename
        return new_filename + (".vsdm" if self.is_macro_enabled else ".vsdx")

    def save(self, target: str | os.PathLike[str] | None = None) -> Path:
        """Write the document, and return the absolute path it was written to.

        :param target: where to write. A ``.vsdx`` or ``.vsdm`` extension must
            match the package's own kind; any other name gets the matching
            extension appended. Omit it to save over the file the document
            was opened from; that name is checked the same way but never renamed.
        :raises InvalidOperationError: if the extension contradicts the package kind
        """
        if not self._package.names():
            raise InvalidOperationError("cannot save an empty package")

        if target is None:
            # the name it was opened under can only be refused, never rewritten:
            # silently renaming the caller's file would be a worse surprise than
            # the mismatch. `open` already refused anything but .vsdx or .vsdm.
            self._check_destination_kind(self._filename)
            # every change is already in the store -- the trees this document
            # edits are the store's own -- so saving is writing it, member by
            # member. In place, that is over the absolute path the store
            # captured at open: `filename` may be relative, and resolve against
            # another working directory by the time this runs.
            return self._package.save()
        # resolve the destination first, so a refused extension writes nothing
        return self._package.save(self._destination_filename(os.fspath(target)))

    def render(self, context: Mapping[str, object]) -> None:
        """Render the document as a Jinja template, in place.

        Shape text, and page names, are Jinja templates. vsdx-specific
        extensions are available, such as `{% for item in list %}` statements
        with no `{% endfor %}`. See :func:`vsdxkit.templating.render_document`.

        :param context: the values the templates can refer to
        """
        render_document(self, context)
