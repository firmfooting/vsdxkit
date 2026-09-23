from __future__ import annotations

import copy
import io
import os
import posixpath
import re
import sys
import xml.dom.minidom as minidom  # minidom used for prettyprint
import xml.etree.ElementTree as ET
from collections.abc import MutableMapping
from types import TracebackType
from typing import NamedTuple
from xml.etree.ElementTree import Element

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

import vsdxkit

from . import relationships
from .logging_support import attach_debug_stream_handler, get_logger
from .package import PackageLimitError as PackageLimitError
from .package import PackageLimits, PackageStore, XmlPart
from .zip_contents import ZipFileContentsView, part_name_for_path

# TODO(#362): `PackageLimitError` is imported here only to keep
# `vsdxkit.vsdxfile.PackageLimitError` working -- it moved to `vsdxkit.package`
# and `docs/classes.rst` had named the old path. It is spelled as an explicit
# re-export (`X as X`) rather than under a `noqa: F401`, because a `noqa` on the
# shared import line also hid imports that really were unused. It wants a
# deprecation shim, or removal once the old path is no longer published.
# Tested by tests/test_package_limit_error_import.py.
logger = get_logger(__name__)

from . import (  # noqa: E402
    cont_types_namespace,
    document_rels_namespace,
    ext_prop_namespace,
    namespace,
    r_namespace,
    vt_namespace,
)
from .masters import MastersImportMixin  # noqa: E402
from .pages import Page, PagePosition  # noqa: E402
from .shapes import Shape, find_or_create_shapes_tag  # noqa: E402
from .templating import JinjaTemplatingMixin  # noqa: E402

# `file_to_xml` is not called directly in this module any more -- every read
# here goes through `_read_part_xml`/`_require_part_xml`, which promote the
# store's own tree instead of parsing a private copy. It stays importable as
# `vsdxkit.vsdxfile.file_to_xml`: `Page.set_name` imports it from here to avoid
# a circular import, and tests/test_visiofile.py imports it the same way.
from .xmlio import (  # noqa: E402
    adopt_prefixes,
    file_to_xml,  # noqa: F401
    register_namespaces,
    require_element,
    require_tree,
)

register_namespaces()


def _page_relationship_path(rel_dir: str, page_path: str) -> str:
    """Return an in-memory OPC relationship key; OPC member names use `/`."""
    filename = posixpath.basename(page_path.replace("\\", "/"))
    return posixpath.join(rel_dir, f"{filename}.rels")


def _normalise_page_path(path: str) -> str:
    """Normalise mixed platform separators without changing OPC case."""
    return posixpath.normpath(path.replace("\\", "/"))


# The main document part's content type, not the file extension, is what tells
# a consumer whether a package carries macros. Visio reports a package whose
# extension and content type disagree as corrupt, so the two must be kept in
# step on save.
MACRO_ENABLED_CONTENT_TYPE = "application/vnd.ms-visio.drawing.macroEnabled.main+xml"
DRAWING_CONTENT_TYPE = "application/vnd.ms-visio.drawing.main+xml"
_SUFFIX_BY_CONTENT_TYPE = {MACRO_ENABLED_CONTENT_TYPE: ".vsdm", DRAWING_CONTENT_TYPE: ".vsdx"}

# OPC part names for the document-level parts `VisioFile` exposes as
# properties. Fixed, unlike a page's part name, because there is only ever one
# of each in a package.
_PAGES_PART = "/visio/pages/pages.xml"
_PAGES_RELS_PART = "/visio/pages/_rels/pages.xml.rels"
_CONTENT_TYPES_PART = "/[Content_Types].xml"
_APP_PART = "/docProps/app.xml"
_DOCUMENT_PART = "/visio/document.xml"
_DOCUMENT_RELS_PART = "/visio/_rels/document.xml.rels"
_MASTERS_PART = "/visio/masters/masters.xml"

# A ShapeSheet formula addresses another shape as `Sheet.5!Cell` or `Sheet5!Cell`.
# Visio writes the dotted form in inherited cells and the undotted form in the
# formulas it generates for connector glue -- `_XFTRIGGER(Sheet5!EventXFMod)`,
# `PAR(PNT(Sheet5!Connections.X1,...))` -- where the reference is also nested
# inside a function call rather than at the start of the formula.
#
# The lookbehind excludes the sheet of a cross-page reference: the `Sheet.5!` in
# `Pages[Page-2]!Sheet.5!Width` is an id on the page named in front of it, and
# ids are page-scoped, so remapping it through this page's map would repoint the
# reference at an unrelated shape. `tests/helpers/package_validator.py` draws
# the same line, and the two have to agree or one of them is wrong about which
# references a page owns.
_SHEET_REFERENCE_RE = re.compile(r"(?<!!)\bSheet(\.?)(\d+)!")


def _remap_sheet_references(formula: str, id_map: dict[str, int]) -> str:
    """Rewrite the shape ids in a formula, keeping each reference's own form.

    Ids absent from ``id_map`` address shapes outside the copied subtree (the
    Swimlane List, for instance) and are left exactly as they are.
    """

    def replace(match: re.Match[str]) -> str:
        separator, shape_id = match.group(1), match.group(2)
        if shape_id not in id_map:
            return match.group(0)
        return f"Sheet{separator}{id_map[shape_id]}!"

    return _SHEET_REFERENCE_RE.sub(replace, formula)


class VisioFileNotOpen(Exception):
    """Error class to report when a VisioFile is attempted to be saved when no longer open"""

    pass


class VisioFile(MastersImportMixin, JinjaTemplatingMixin):
    """Represents a vsdx file

    :param filename: filename the :class:`VisioFile` was created from
    :type filename: str
    :param pages: a list of pages in the VisioFile
    :type pages: list of :class:`Page`
    :param master_pages: a list of master pages in the VisioFile
    :type master_pages: list of :class:`Page`
    """

    def __init__(
        self,
        filename: str,
        debug: bool = False,
        limits: PackageLimits | None = None,
        limits_path: str | None = None,
    ) -> None:
        """VisioFile constructor

        :param filename: the vsdx file to load and create the VisioFile object from
        :type filename: str
        :param debug: enable/disable debugging
        :type debug: bool, default to False
        :param limits: package expansion caps; the defaults suit untrusted documents
        :type limits: PackageLimits, optional
        :param limits_path: JSON file with the same keys as the PackageLimits fields
        :type limits_path: str, optional
        """
        self.debug = debug
        self.filename = filename
        if debug:
            attach_debug_stream_handler()
        logger.debug("VisioFile(filename=%s)", filename)
        file_type = self.filename.split(".")[-1]  # last text after dot
        if not file_type.lower() == "vsdx" and not file_type.lower() == "vsdm":
            raise TypeError(f"Invalid File Type:{file_type}")

        if limits_path is not None:
            limits = PackageLimits.from_json_file(limits_path)
        self.limits = limits if limits is not None else PackageLimits()

        self.directory = os.path.abspath(filename)[:-5]
        # pages_xml, pages_xml_rels, content_types_xml, app_xml, document_xml,
        # document_xml_rels and masters_xml are store-backed properties, defined
        # below -- there is nothing to initialise here, since the store itself
        # is the state.
        self.pages: list[Page] = []  # populated by open_vsdx_file()
        self.master_index: dict[str, Page] = {}  # master page info by item name e.g. 'Dynamic Connector'
        self.master_pages: list[Page] = []  # populated by open_vsdx_file()
        self.file_open = False
        # populated by _load_zip_file_contents_to_memory(), called from
        # open_vsdx_file() below; declared here so an attribute assigned
        # outside __init__ still has a home for pyrefly to check it against
        self._package: PackageStore
        # `filename` as the store was opened from it; see save_vsdx
        self._opened_filename: str
        self.zip_file_contents: MutableMapping[str, io.BytesIO]
        # the bundled donor packages are expensive to parse, so one Media is
        # shared by every create/connect call on this document (issue #65)
        self._media: vsdxkit.Media | None = None
        self.open_vsdx_file()

    def __enter__(self) -> VisioFile:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close_vsdx()

    @override
    def _require_open(self, operation: str) -> None:
        """Refuse a mutation on a closed document, whose result no save can reach.

        Ask this of the document the operation would change, which is not
        always the receiver: a cross-document copy runs `copy_shape` on the
        source but edits the destination page, so those methods ask `page.vis`
        (issue #242).
        """
        if not self.file_open:
            raise VisioFileNotOpen(f"{operation} is not available once the document is closed")

    @staticmethod
    def _part_tree(tree: ET.ElementTree[ET.Element] | None, description: str) -> ET.ElementTree[ET.Element]:
        """A required document part (pages.xml, app.xml, ...).

        A missing part means the package is malformed for the operation being
        attempted, so raise with the part name rather than failing on None.
        """
        return require_tree(tree, description)

    @staticmethod
    def _part_root(tree: ET.ElementTree[ET.Element] | None, description: str) -> ET.Element:
        """Root element of a required document part."""
        return require_element(VisioFile._part_tree(tree, description).getroot(), f"{description} root")

    @staticmethod
    def pretty_print_element(xml: Element | ET.ElementTree[ET.Element]) -> str:
        if isinstance(xml, ET.ElementTree):
            return minidom.parseString(ET.tostring(require_element(xml.getroot(), "element"))).toprettyxml()
        return minidom.parseString(ET.tostring(xml)).toprettyxml()

    def _load_zip_file_contents_to_memory(self) -> None:
        """Open the package as a `PackageStore`, the one copy of it held from now on.

        `zip_file_contents` survives as a view over the store, keyed the old
        way, until #91 retires it.
        """
        self._package = PackageStore.open(self.filename, limits=self.limits)
        self._opened_filename = self.filename
        self.zip_file_contents = ZipFileContentsView(self._package, self.directory)

    @override
    def _part_name(self, path: str) -> str:
        """The OPC part name for one of this document's `{directory}/...` paths."""
        name = part_name_for_path(self.directory, path)
        if name is None:
            raise ValueError(f"{path!r} is not a part of this document")
        return name

    @override
    def _read_part_xml(self, path: str) -> ET.ElementTree[ET.Element] | None:
        """The store's own tree for a part, promoting it -- never a private copy."""
        return self._package.read_xml(self._part_name(path))

    def _require_part_xml(self, path: str, description: str) -> ET.ElementTree[ET.Element]:
        """The store's own tree for a required part, or a ValueError naming it."""
        tree = self._read_part_xml(path)
        if tree is None:
            raise ValueError(f"expected XML part not found: {description} ({path})")
        return tree

    def _set_part_xml(self, name: str, tree: ET.ElementTree[ET.Element] | None) -> None:
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

    def _set_document_part_xml(self, attribute: str, name: str, tree: ET.ElementTree[ET.Element] | None) -> None:
        """`_set_part_xml` for a part the document itself is wired to, which None may not remove.

        `app.xml`, `document.xml`, `pages.xml` and the rest are each named by a
        relationship and described by a content-type override. Taking one out
        of the store leaves both behind, and the saved package promises a part
        it does not hold. A page's rels part is different -- nothing points at
        it -- so `Page.rels_xml = None` still removes it, through
        `_set_part_xml` directly.
        """
        if tree is None:
            raise ValueError(
                f"VisioFile.{attribute} cannot remove {name} through this property: this "
                f"property does not also remove the relationship and content-type override "
                f"that name a document part, so setting it to None would leave the package "
                f"inconsistent"
            )
        self._set_part_xml(name, tree)

    @property
    def pages_xml(self) -> ET.ElementTree[ET.Element] | None:
        return self._package.read_xml(_PAGES_PART)

    @pages_xml.setter
    def pages_xml(self, tree: ET.ElementTree[ET.Element] | None) -> None:
        self._set_document_part_xml("pages_xml", _PAGES_PART, tree)

    @property
    def pages_xml_rels(self) -> ET.ElementTree[ET.Element] | None:
        return self._package.read_xml(_PAGES_RELS_PART)

    @pages_xml_rels.setter
    def pages_xml_rels(self, tree: ET.ElementTree[ET.Element] | None) -> None:
        self._set_document_part_xml("pages_xml_rels", _PAGES_RELS_PART, tree)

    @property
    def content_types_xml(self) -> ET.ElementTree[ET.Element] | None:
        return self._package.read_xml(_CONTENT_TYPES_PART)

    @content_types_xml.setter
    def content_types_xml(self, tree: ET.ElementTree[ET.Element] | None) -> None:
        self._set_document_part_xml("content_types_xml", _CONTENT_TYPES_PART, tree)

    @property
    def app_xml(self) -> ET.ElementTree[ET.Element] | None:
        return self._package.read_xml(_APP_PART)

    @app_xml.setter
    def app_xml(self, tree: ET.ElementTree[ET.Element] | None) -> None:
        self._set_document_part_xml("app_xml", _APP_PART, tree)

    @property
    def document_xml(self) -> ET.ElementTree[ET.Element] | None:
        return self._package.read_xml(_DOCUMENT_PART)

    @document_xml.setter
    def document_xml(self, tree: ET.ElementTree[ET.Element] | None) -> None:
        self._set_document_part_xml("document_xml", _DOCUMENT_PART, tree)

    @property
    def document_xml_rels(self) -> ET.ElementTree[ET.Element] | None:
        return self._package.read_xml(_DOCUMENT_RELS_PART)

    @document_xml_rels.setter
    def document_xml_rels(self, tree: ET.ElementTree[ET.Element] | None) -> None:
        self._set_document_part_xml("document_xml_rels", _DOCUMENT_RELS_PART, tree)

    @property
    @override
    def masters_xml(self) -> ET.Element | None:
        """The `<Masters>` root, read from the store so it can never be a stale copy."""
        tree = self._package.read_xml(_MASTERS_PART)
        return None if tree is None else tree.getroot()

    @masters_xml.setter
    @override
    def masters_xml(self, root: ET.Element | None) -> None:
        if root is None:
            self._set_document_part_xml("masters_xml", _MASTERS_PART, None)  # raises: see there
            return
        # asked of the part as held rather than through `read_xml`: whether the
        # root is already the part's own needs no parse, and promoting the part
        # here would make assigning over bytes that are not XML raise
        held = self._package.part(_MASTERS_PART)
        if isinstance(held, XmlPart) and held.tree.getroot() is root:
            return
        self._set_document_part_xml("masters_xml", _MASTERS_PART, ET.ElementTree(root))

    def open_vsdx_file(self) -> None:
        self._load_zip_file_contents_to_memory()

        # load each page file into an ElementTree object
        self.load_pages()
        self.load_master_pages()
        self.file_open = True

    def _pages_filename(self):
        # pages.xml contains Page name, width, height, mapped to Id
        return f"{self.directory}{_PAGES_PART}"

    @property
    @override
    def _masters_folder(self) -> str:
        return f"{self.directory}/visio/masters"

    def load_pages(self) -> None:
        rel_dir = f"{self.directory}/visio/pages/_rels/"
        page_dir = f"{self.directory}/visio/pages/"

        rel_filename = rel_dir + "pages.xml.rels"
        pages_xml_rels = self._require_part_xml(rel_filename, "pages.xml.rels")
        rels = require_element(pages_xml_rels.getroot(), "pages.xml.rels")
        if self.debug:
            logger.debug("Relationships(%s)\n%s", rel_filename, VisioFile.pretty_print_element(rels))
        relid_page_dict = {}

        for rel in rels:
            rel_id = rel.attrib["Id"]
            page_file = rel.attrib["Target"]
            relid_page_dict[rel_id] = page_file

        pages_filename = self._pages_filename()  # pages contains Page name, width, height, mapped to Id
        pages_xml = self._require_part_xml(pages_filename, "pages.xml")
        pages = require_element(pages_xml.getroot(), "pages.xml")
        if self.debug:
            logger.debug("Pages(%s)\n%s", pages_filename, VisioFile.pretty_print_element(pages))

        for page in pages:  # type: Element
            rel_id = require_element(page.find(f"{namespace}Rel"), "Page/Rel").attrib[f"{r_namespace}id"]
            page_name = page.attrib["Name"]

            page_file = relid_page_dict.get(rel_id)
            if page_file is None:
                raise ValueError(f"no page part found for relationship {rel_id}")
            page_path = page_dir + page_file
            page_id = page.attrib.get("ID", "")

            new_page = Page(self._require_part_xml(page_path, "page part"), page_path, page_name, page_id, rel_id, self)
            # look for visio/pages/_rels/page3.xml.rels
            page_rels_path = _page_relationship_path(rel_dir, page_path)

            if page_rels_path in self.zip_file_contents:
                new_page.rels_xml_filename = page_rels_path
                # past the setter: the document is not open yet, which the
                # setter refuses, and the tree is the store's own, so there is
                # nothing for it to write through
                new_page._rels_xml = self._read_part_xml(page_rels_path)
            self.pages.append(new_page)

            if self.debug:
                logger.debug("Page(%s)\n%s", new_page.filename, VisioFile.pretty_print_element(new_page.xml))

        # content_types_xml, app_xml, document_xml and document_xml_rels are
        # store-backed properties, but promoted here rather than left to the
        # first later access: a part promoted at load is an `XmlPart` from the
        # moment the document opens, which is what lets a caller compare the
        # store's own identity for a part it has not yet touched (app.xml, in
        # particular, may simply be missing, and promoting a missing part is
        # just None), and a part that is not well-formed XML fails the open
        # itself, with a `PartParseError`, rather than the first access to it.
        self._read_part_xml(f"{self.directory}/[Content_Types].xml")
        self._read_part_xml(f"{self.directory}/docProps/app.xml")
        self._read_part_xml(f"{self.directory}/visio/document.xml")
        self._read_part_xml(f"{self.directory}/visio/_rels/document.xml.rels")
        # TODO: add correctness cross-check. Or maybe the other way round, start from [Content_Types].xml
        #       to get page_dir and other paths...

    @override
    def load_master_pages(self) -> None:
        # get data from /visio/masters folder
        master_rel_path = f"{self.directory}/visio/masters/_rels/masters.xml.rels"

        master_rels_data = self._read_part_xml(master_rel_path)
        # a document with no masters has no rels part: iterate an empty list
        master_rels: list[Element] = list(master_rels_data.getroot()) if master_rels_data is not None else []
        if self.debug:
            logger.debug("Master Relationships(%s)\n%s", master_rel_path, master_rels)

        # populate relid to master path
        relid_to_path: dict[str, str] = {}
        for rel in master_rels:
            master_id = rel.attrib.get("Id")
            if master_id is None:
                continue
            relid_to_path[master_id] = f"{self.directory}/visio/masters/{rel.attrib.get('Target')}"

        # masters_xml is a store-backed property (contains more info about
        # master page, i.e. Name, Icon); reading it here promotes the part.

        # for each master page, create the Page object
        for master in self.masters_xml if self.masters_xml is not None else []:
            master_name = master.attrib.get("NameU") or master.attrib.get("Name") or "Unknown"
            rel_id = require_element(master.find(f"{namespace}Rel"), "Master/Rel").attrib[f"{r_namespace}id"]
            master_id = master.attrib["ID"]
            master_unique_id = master.attrib.get("UniqueID")
            master_base_id = master.attrib.get("BaseID")

            master_path = relid_to_path[rel_id]

            master_page = Page(
                self._require_part_xml(master_path, "master part"),
                master_path,
                master_name,
                master_id,
                rel_id,
                self,
            )
            master_page.master_unique_id = master_unique_id
            master_page.master_base_id = master_base_id
            self.master_pages.append(master_page)
            self.master_index[master_name] = master_page  # index by master_name

            if self.debug:
                logger.debug("Master(%s, id=%s)\n%s", master_path, master_id, VisioFile.pretty_print_element(master_page.xml))

        return

    def get_page(self, n: int) -> Page | None:
        try:
            return self.pages[n]
        except IndexError:
            return None

    def get_page_names(self) -> list[str]:
        return [p.name for p in self.pages]

    def get_page_by_name(self, name: str) -> Page | None:
        """Get page from VisioFile with matching name

        :param name: The name of the required page
        :type name: str

        :return: :class:`Page` object representing the page (or None if not found)
        """
        for p in self.pages:
            if p.name == name:
                return p

    def get_master_page_by_id(self, id: str) -> Page | None:
        """Get master page from VisioFile with matching ID.

        Referred by :attr:`Shape.master_ID`.

                :param id: The ID of the required master
                :type id: str

                :return: :class:`Page` object representing the master page (or None if not found)
        """
        for m in self.master_pages:
            if m.page_id == id:
                return m

    @override
    def remove_page_by_index(self, index: int) -> None:
        """Remove zero-based nth page from VisioFile object

        :param index: Zero-based index of the page
        :type index: int

        :return: None
        """
        self._require_open("VisioFile.remove_page_by_index()")

        # remove Page element from pages.xml file - zero based index
        if isinstance(index, int):
            pages_root = self._part_root(self.pages_xml, "pages.xml")
            page = pages_root.find(f"{namespace}Page[{index + 1}]")
            if isinstance(page, Element):
                pages_root.remove(page)
                page = self.pages[index]  # type: Page

                # remove internal references to page
                self._remove_page_from_app_xml(page.name)

                # issue #7: a dangling rId pointing at a deleted part corrupts
                # the OPC graph, and so does an Override naming one
                relationships.remove(self._part_root(self.pages_xml_rels, "pages.xml.rels"), page.rel_id or "")
                relationships.remove_override(
                    self._part_root(self.content_types_xml, "[Content_Types].xml"),
                    f"/visio/pages/{os.path.basename(page.filename)}",
                )

                # remove the page's own rels part if one exists
                if page.rels_xml_filename and page.rels_xml_filename in self.zip_file_contents:
                    self._package.remove(self._part_name(page.rels_xml_filename))

                # remove page<index>.xml file
                self._package.remove(self._part_name(self.pages[index].filename))
                del self.pages[index]

    def remove_page_by_name(self, page_name: str) -> None:
        """Remove first page from VisioFile object that matches the page_name

        :param page_name: page of page to delete
        :type page_name: str

        :return: None
        """
        self._require_open("VisioFile.remove_page_by_name()")

        # get index and then pass to remove_page_by_index() to perform deletion
        for p in self.pages:
            if p.name == page_name:
                index = p.index_num
                if index is None:  # page is not attached to this document
                    continue
                self.remove_page_by_index(index)
                break  # exit after first match - delete only one page

    def _update_pages_xml_rels(self, new_page_filename: str) -> str:
        """Updates the pages.xml.rels file with a reference to the new page and returns the new relid"""

        rels_root = self._part_root(self.pages_xml_rels, "pages.xml.rels")
        relationship = relationships.append_if_absent(
            rels_root,
            rel_type="http://schemas.microsoft.com/visio/2010/relationships/page",
            target=new_page_filename,
        )
        return relationship.attrib["Id"]

    def _get_new_page_name(self, new_page_name: str) -> str:
        i = 1
        while new_page_name in self.get_page_names():
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
        own tree and refuses to write over it, so the new page's `rels_xml`
        assignment becomes a silent no-op.
        """
        page_dir = f"{self.directory}/visio/pages/"
        rel_dir = f"{self.directory}/visio/pages/_rels/"
        taken = set(self.zip_file_contents)
        rels_root = self._part_root(self.pages_xml_rels, "pages.xml.rels")
        taken.update(f"{page_dir}{rel.attrib['Target']}" for rel in rels_root)
        counter = 1
        while f"{page_dir}page{counter}.xml" in taken or f"{rel_dir}page{counter}.xml.rels" in taken:
            counter += 1
        return f"page{counter}.xml"

    def _get_max_page_id(self) -> int:
        pages_root = self._part_root(self.pages_xml, "pages.xml")
        page_with_max_id = max(pages_root, key=lambda page: int(page.attrib["ID"]))
        max_page_id = int(page_with_max_id.attrib["ID"])

        return max_page_id

    def _get_index(self, *, index: int | PagePosition, page: Page | None) -> int:
        if isinstance(index, PagePosition):  # only update index if it is relative to source page
            if index == PagePosition.LAST:
                index = len(self.pages)
            elif index == PagePosition.FIRST:
                index = 0
            elif page:  # need page for BEFORE or AFTER
                orig_page_idx = self.pages.index(page)
                if index == PagePosition.BEFORE:
                    # insert new page at the original page's index
                    index = orig_page_idx
                elif index == PagePosition.AFTER:
                    # insert new page after the original page
                    index = orig_page_idx + 1
            else:
                raise ValueError(f"{index!r} requires a reference page; pass the source page to position relative to")

        return index

    @override
    def _add_content_types_override(self, part_name_path: str, content_type: str) -> None:
        relationships.ensure_override(
            self._part_root(self.content_types_xml, "[Content_Types].xml"), part_name_path, content_type
        )

    def document_rels(self) -> list[Element]:
        rels_root = self._part_root(self.document_xml_rels, "visio/_rels/document.xml.rels")
        rels = rels_root.findall(f"{document_rels_namespace}Relationship")
        return rels

    @override
    def _add_document_rel(self, rel_type: str, target: str) -> None:
        relationships.append_if_absent(
            self._part_root(self.document_xml_rels, "visio/_rels/document.xml.rels"), rel_type=rel_type, target=target
        )

    def _style_sheets(self) -> Element:
        # return StyleSheets element from document.xml
        root = self._part_root(self.document_xml, "document.xml")
        return require_element(root.find(f"{namespace}StyleSheets"), "document.xml StyleSheets")

    def _get_styles_name_list(self) -> list[str]:
        return [s.attrib.get("Name", "") for s in self._style_sheets().findall(f"{namespace}StyleSheet")]

    def _get_style_by_name(self, name: str) -> Element | None:
        return self._style_sheets().find(f"{namespace}StyleSheet[@Name = '{name}']")

    def _get_style_by_id(self, ID: str) -> Element | None:
        return self._style_sheets().find(f"{namespace}StyleSheet[@ID = '{ID}']")

    def _heading_pairs(self) -> Element:
        # return HeadingPairs element from app.xml
        root = self._part_root(self.app_xml, "docProps/app.xml")
        return require_element(root.find(f"{ext_prop_namespace}HeadingPairs"), "app.xml HeadingPairs")

    def _titles_of_parts(self) -> Element:
        # return TitlesOfParts element from app.xml
        root = self._part_root(self.app_xml, "docProps/app.xml")
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

    PAGES = _Section("Pages", is_pages=True)
    MASTERS = _Section("Masters", is_pages=False)

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

    def _titles_of_parts_section(self, section: _Section, page_titles: set[str]) -> tuple[Element, int, int]:
        """The TitlesOfParts vector, and the ``[start, stop)`` slice of it `section` owns.

        A section HeadingPairs does not mention owns the empty slice at the end
        of the vector: it has no titles yet, and the first one it gets belongs
        after every title already spoken for.

        The slice stops at the end of the vector however large the counts are.
        They come from whatever wrote the file, and a count read as a position
        is a count that can point past the last title there is. Only the slice
        is clipped: the count itself is the file's to keep.
        """
        vector = require_element(self._titles_of_parts().find(f"{vt_namespace}vector"), "TitlesOfParts vector")
        total = len(vector)
        wanted = self._resolve_section(section, page_titles)
        if wanted is None:
            return vector, total, total
        start = 0
        for index, (_, count) in enumerate(self._heading_pairs_list()):
            titles_here = int(count.text or 0)
            if index == wanted:
                return vector, min(start, total), min(start + titles_here, total)
            start += titles_here
        return vector, total, total

    def _section_count(self, section: _Section, change: int, page_titles: set[str]) -> None:
        """Add `change` to `section`'s count in HeadingPairs, creating the pair if needed.

        The stored count is what moves, not the length of the slice it turned
        out to name: a section reporting more titles than the vector holds
        still knows how many parts it has, and re-deriving the number from
        where the titles ended up would throw that away.
        """
        index = self._resolve_section(section, page_titles)
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
        vector, start, stop = self._titles_of_parts_section(section, titles)
        if any(vector[position].text == title for position in range(start, stop)):
            return
        entry = Element(f"{vt_namespace}lpstr")
        entry.text = title
        vector.insert(stop, entry)
        vector.attrib["size"] = str(len(vector))
        self._section_count(section, 1, titles)

    def _titles_of_parts_remove(self, title: str, section: _Section, page_titles: set[str] | None = None) -> None:
        """Drop `section`'s entry for `title`, and stop counting it.

        The count moves only when an entry does, and only this section's
        entries are candidates: a page and a master can be called the same
        thing, and the one being removed is the one in this section.
        """
        titles = self._page_titles() if page_titles is None else page_titles
        vector, start, stop = self._titles_of_parts_section(section, titles)
        for position in range(start, stop):
            if vector[position].text == title:
                del vector[position]
                vector.attrib["size"] = str(len(vector))
                self._section_count(section, -1, titles)
                return

    def _titles_of_parts_rename(self, old_title: str, new_title: str, section: _Section, page_titles: set[str]) -> None:
        """Rewrite `section`'s entry for `old_title` in place.

        In place rather than a removal and an insertion: nothing joins or
        leaves the section, so neither its count nor the order of its titles
        has any business changing.
        """
        vector, start, stop = self._titles_of_parts_section(section, page_titles)
        for position in range(start, stop):
            if vector[position].text == old_title:
                vector[position].text = new_title
                return

    def _get_app_xml_value(self, name: str) -> str | None:
        """The count HeadingPairs gives `name`, or None if it names no such section."""
        for section, count in self._heading_pairs_list():
            if section == name:
                return count.text or ""
        return None

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
        self._titles_of_parts_insert(new_page_name, VisioFile.PAGES)

    def _remove_page_from_app_xml(self, page_name: str) -> None:
        if self.app_xml is not None:
            logger.debug("_remove_page_from_app_xml()")
            self._titles_of_parts_remove(page_name, VisioFile.PAGES)

    def _rename_page_in_app_xml(self, old_page_name: str, new_page_name: str) -> None:
        """Keep app.xml's list of page names in step with a page that was renamed.

        Adding or removing a page writes a part into the package, and app.xml
        not being shaped like app.xml is then a broken document. A rename
        writes nothing, so a document whose metadata never listed the parts is
        left as it is rather than made to raise over a property assignment.
        """
        if self.app_xml is None:
            return
        root = self._part_root(self.app_xml, "docProps/app.xml")
        if root.find(f"{ext_prop_namespace}HeadingPairs") is None:
            return
        if root.find(f"{ext_prop_namespace}TitlesOfParts") is None:
            return
        # app.xml still lists the old title and the page already carries the new
        # one, so the titles to look for are today's with that swap undone. On a
        # one-page document nothing else identifies the section.
        expected = (self._page_titles() - {new_page_name}) | {old_page_name}
        self._titles_of_parts_rename(old_page_name, new_page_name, VisioFile.PAGES, expected)

    def _create_page(
        self,
        *,
        new_page_xml_str: str,
        page_name: str,
        new_page_element: Element,
        index: int | PagePosition,
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

        page_dir = f"{self.directory}/visio/pages/"  # TODO: better concatenation

        # create pageX.xml
        new_page_root = ET.fromstring(new_page_xml_str)
        if source_page is not None:
            # a copied page reaches here as a string, which drops the prefixes
            # its source declared; the copy is still the same page
            adopt_prefixes(new_page_root, require_element(source_page.xml.getroot(), "source page root"))
        new_page_xml: ET.ElementTree[ET.Element] = ET.ElementTree(new_page_root)
        new_page_path = page_dir + new_page_filename  # TODO: better concatenation

        # update pages.xml - insert the PageElement Element in it's correct location
        index = self._get_index(index=index, page=source_page)
        self._part_root(self.pages_xml, "pages.xml").insert(index, new_page_element)

        # update [Content_Types].xml - insert reference to the new page
        self._add_content_types_override(f"/visio/pages/{new_page_filename}", "application/vnd.ms-visio.page+xml")

        # update app.xml, if it exists
        if self.app_xml:
            self._add_page_to_app_xml(page_name)

        # Update VisioFile object; the page carries its real ID and relationship
        # id immediately (issue #7: they were blank until a reload)
        page_id = new_page_element.attrib["ID"]
        # written into the store before the Page is constructed, so `Page.xml`'s
        # write-through guard (`_attached()`) already finds the page's own tree
        # at its part name for any later assignment, and because this call is
        # what gets the new page into the package at all: a save writes the
        # store and nothing else
        self._package.write_xml(self._part_name(new_page_path), new_page_xml)
        new_page = Page(new_page_xml, new_page_path, page_name, page_id, new_page_relid, self)
        if source_page is not None and source_page.rels_xml is not None:
            source_rels_root = require_element(source_page.rels_xml.getroot(), "source page relationships root")
            rel_dir = f"{self.directory}/visio/pages/_rels/"
            # the filename first: the `rels_xml` setter only writes through when
            # `rels_xml_filename` is already set (and the page's own tree, above,
            # is already its part)
            new_page.rels_xml_filename = _page_relationship_path(rel_dir, new_page_path)
            new_page.rels_xml = ET.ElementTree(copy.deepcopy(source_rels_root))

        self.pages.insert(index, new_page)  # insert new page at defined index

        return new_page

    def add_page_at(self, index: int, name: str | None = None) -> Page:
        """Add a new page at the specified index of the VisioFile

        :param index: zero-based index where the new page will be placed
        :type index: int

        :param name: The name of the new page
        :type name: str, optional

        :return: :class:`Page` object representing the new page
        """
        self._require_open("VisioFile.add_page_at()")

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

    def add_page(self, name: str | None = None) -> Page:
        """Add a new page at the end of the VisioFile

        :param name: The name of the new page
        :type name: str, optional

        :return: Page object representing the new page
        """

        return self.add_page_at(PagePosition.LAST, name)

    def copy_page(self, page: Page, *, index: int | PagePosition = PagePosition.AFTER, name: str | None = None) -> Page:
        """Copy an existing page and insert in VisioFile

        :param page: the page to copy
        :type page: Page
        :param index: the specific int or relation PagePosition location for new page
        :type index: int | PagePosition
        :param name: name of new page (note this may be altered if name already exists)
        :type name: str

        :return: the newly created page
        """
        self._require_open("VisioFile.copy_page()")
        # Determine the new page's name
        new_page_name = self._get_new_page_name(name or page.name)

        # Determine the new page's filename
        new_page_filename = self._unused_page_part_name()

        # Add reference to the new page in pages.xml.rels and get new relid
        new_page_relid = self._update_pages_xml_rels(new_page_filename)

        # Copy the source page and update relevant attributes
        pages_root = self._part_root(self.pages_xml, "pages.xml")
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

    # TODO: dead code - never used
    def get_sub_shapes(self, shape: Element, nth: int = 1) -> Element | None:
        for e in shape:
            if "Shapes" in e.tag:
                nth -= 1
                if not nth:
                    return e

    @staticmethod
    def get_shape_location(shape: Element) -> tuple[float, float]:
        cell_PinX = require_element(shape.find(f'{namespace}Cell[@N="PinX"]'), "PinX cell")
        cell_PinY = require_element(shape.find(f'{namespace}Cell[@N="PinY"]'), "PinY cell")
        x = float(cell_PinX.attrib["V"])
        y = float(cell_PinY.attrib["V"])

        return x, y

    @staticmethod
    def set_shape_location(shape: Element, x: float, y: float) -> None:
        cell_PinX = require_element(shape.find(f'{namespace}Cell[@N="PinX"]'), "PinX cell")
        cell_PinY = require_element(shape.find(f'{namespace}Cell[@N="PinY"]'), "PinY cell")
        cell_PinX.attrib["V"] = str(x)
        cell_PinY.attrib["V"] = str(y)

    @staticmethod
    def apply_text_context(shapes: Element, context: dict[str, object]) -> None:
        """Substitute `{{key}}` in the text of every shape under `shapes`.

        For example a shape reading "For {{customer_name}} (c){{year}}" becomes
        "For codypy.com (c)2020".

        `iter` rather than a hand-rolled descent: a group holds its children in
        its own `<Shapes>`, and the recursion this replaced never went in there.

        This reads a shape's own `<Text>` and does not resolve master
        inheritance, because it is handed elements rather than Shapes and has no
        master to consult. A shape showing its master's text is left alone;
        `Page.apply_text_context` is the route that resolves it.
        """
        for shape in shapes.iter(f"{namespace}Shape"):
            prefix, text, suffix, trailing = vsdxkit.shapes._text_runs_of(shape.find(f"{namespace}Text"))
            substituted = vsdxkit.shapes.substitute(text, context)
            # see Shape.apply_text_filter: visiting a shape that needs no
            # substitution is not free, so do not write one back unchanged
            if substituted != text:
                vsdxkit.shapes._write_text(shape, substituted, prefix=prefix, suffix=suffix, trailing=trailing)

    @staticmethod
    def get_shape_id(shape: Element) -> str:
        return shape.attrib["ID"]

    def _shared_media(self) -> vsdxkit.Media:
        """The bundled media/palette documents for this VisioFile.

        Created on first use and reused for every subsequent create/connect
        call, so a loop of N shapes parses the donor packages once rather than
        N times. Ownership stays here: `close_vsdx` closes and drops it, and a
        closed document is refused rather than handed a replacement, so the
        only pair that ever exists is one this document will close (issue #242).
        """
        self._require_open("building a shape or connector")
        if self._media is None:
            self._media = vsdxkit.Media()
        return self._media

    def create_shape(
        self,
        page: Page,
        palette_name: str,
        x: float,
        y: float,
        w: float | None = None,
        h: float | None = None,
        text: str | None = None,
    ) -> Shape:
        """Create a new shape on a page from the extended shape palette.

        Palette shapes are deliberately masterless, so creation needs no
        master-import and works on any document. Reuses copy_shape and the
        existing position/size setters (no second copy or id-rewrite path).

        :param page: destination page
        :param palette_name: sentinel name, e.g. 'PALETTE_PROCESS',
            'PALETTE_DECISION', 'PALETTE_START_END', 'PALETTE_PARALLELOGRAM',
            'PALETTE_DATABASE'
        :param x, y: centre position of the new shape
        :param w, h: optional width/height overrides
        :param text: label text; the palette sentinel name is cleared when None
        :return: the new Shape
        """
        page.vis._require_open("VisioFile.create_shape()")
        # the donor belongs to the document being changed, which is also the
        # one that will close it
        media = page.vis._shared_media()
        source = media.palette.pages[0].find_shape_by_text(palette_name)
        if source is None:
            raise ValueError(f"palette has no shape named {palette_name}")
        new_shape_xml = self.copy_shape(source.xml, page)
        new_shape = page.find_shape_by_id(new_shape_xml.attrib["ID"])
        if new_shape is None:
            raise ValueError("newly created shape not found on page")

        # palette shapes are drawn around their centre: position via PinX/PinY
        new_shape.get_or_create_cell("PinX", v=str(x))
        new_shape.get_or_create_cell("PinY", v=str(y))
        if w is not None:
            new_shape.width = w
        if h is not None:
            new_shape.height = h
        if text is not None:
            new_shape.text = text
        else:
            new_shape.text = ""
        return new_shape

    @override
    def increment_sub_shape_ids(self, shape: Shape, page: Page, id_map: dict[str, int] | None = None) -> dict[str, int]:
        """Renumber a shape and everything under it, then remap its formulas.

        The layer-by-layer re-walk this used to do is gone: it made up for an
        allocation walk that stopped short, and gave every child a second ID it
        then threw away. ``increment_shape_ids`` now reaches the whole subtree.
        """
        page.vis._require_open("VisioFile.increment_sub_shape_ids()")
        return self.renumber_shape_ids(shape.xml, page, id_map)

    def copy_shape(self, shape: Element, page: Page) -> Element:
        """Insert shape into first Shapes tag in destination page, and return the copy.

        If destination page does not have a Shapes tag yet, create it.

        Parameters:
            shape (Element): The source shape to be copied. Use Shape.xml
            page (ElementTree): The page where the new Shape will be placed. Use Page.xml
            page_path (str): The filename of the page where the new Shape will be placed. Use Page.filename

        Returns:
            ElementTree: The new shape ElementTree

        """
        page.vis._require_open("VisioFile.copy_shape()")

        new_shape = ET.fromstring(ET.tostring(shape))

        shapes_tag = find_or_create_shapes_tag(page.xml.getroot())

        self.renumber_shape_ids(new_shape, page)
        shapes_tag.append(new_shape)

        return new_shape

    def insert_shape(self, shape: Element, shapes: Element, page: Page, page_path: str) -> Element:
        page.vis._require_open("VisioFile.insert_shape()")
        # Keep page_path for the current API, but never let it select a different
        # page from the typed Page argument that owns ID allocation.
        if _normalise_page_path(page.filename) != _normalise_page_path(page_path):
            raise ValueError(f"page_path {page_path!r} does not match page filename {page.filename!r}")

        self.renumber_shape_ids(shape, page)
        shapes.append(shape)
        return shapes

    def renumber_shape_ids(self, shape: Element, page: Page, id_map: dict[str, int] | None = None) -> dict[str, int]:
        """Give a subtree IDs unused by ``page``, and follow them everywhere the page writes them.

        One primitive, because a shape ID is written in two places: the
        ``Sheet.N!`` references inside cell formulas, and the ``FromSheet`` and
        ``ToSheet`` attributes of the page's ``Connect`` records. Allocating and
        then sweeping only the formulas is what left a renumbered shape's glue
        naming an ID that was no longer on the page.

        Both stores are swept over the same ground: the whole page. Sweeping the
        records page-wide and the formulas only inside the renumbered subtree
        left behind every *other* shape that named the vacated ID in a cell
        formula, so a connector's record moved on while the formula placing its
        endpoint still addressed a sheet that had gone (#328).

        A vacated ID is one that was on the page before and is gone after.
        Renumbering does not always retire an ID - ``copy_shape`` leaves the
        original where it was, and the Jinja loop renumbers the duplicates while
        the shape they were copied from keeps its ID. Nor is every ID in the map
        one this page ever had: a subtree arriving from elsewhere brings its own,
        and a stale record that happens to name one of those numbers belongs to
        whatever wrote the file, not to the shape now carrying it. When nothing
        was vacated neither sweep runs, and nothing on the page is rewritten.

        The subtree is swept twice when it is already on the page, and the second
        sweep cannot chain onto what the first wrote. A subtree on the page has
        every allocated ID stamped onto one of its shapes, so every allocated ID
        is in ``after`` and none of them can be a vacated ID; a subtree that is
        not on the page leaves ``before`` and ``after`` equal and vacates
        nothing. The one way past that is a caller seeding ``id_map`` with a
        mapping onto an ID the page is still using, which is not what the
        parameter is for.

        :param shape: root of the subtree to renumber, normally a ``Shape`` element
        :param page: page that owns the ID high-water mark and the records
        :param id_map: mapping to extend, so several subtrees renumbered
            together share one map; a new one is started when omitted
        :return: the ID map, old ID -> new ID
        """
        # its own, rather than the one it inherits from increment_shape_ids:
        # this is the documented primitive and could not name itself in its own
        # error (issue #329)
        page.vis._require_open("VisioFile.renumber_shape_ids()")
        before = page._shape_ids()
        id_map = self.increment_shape_ids(shape, page, id_map)
        self.update_ids(shape, id_map)
        after = page._shape_ids()
        vacated = {old: new for old, new in id_map.items() if old in before and old not in after}
        if vacated:
            self.update_ids(require_element(page.xml.getroot(), "page root"), vacated)
            page._remap_connect_records(vacated)
        return id_map

    def increment_shape_ids(self, shape: Element, page: Page, id_map: dict[str, int] | None = None) -> dict[str, int]:
        """Give ``shape`` and the shapes inside it IDs unused by ``page``, and map old to new.

        Allocation owns the page's high-water mark rather than trusting callers
        to prime it: ``Page._max_id`` is 0 on a freshly loaded page, so a caller
        that forgot handed out 1 to a page whose first shape was already 1.
        Duplicate IDs make ``Connect`` records ambiguous and Visio offers to
        repair the file. Every entry into this method syncs, including one that
        passes an ``id_map`` to collect the mapping, because a caller who has to
        remember is the fault being fixed. The page is scanned once here, and
        the walk below allocates without scanning again.

        That walk covers the whole subtree, to any depth. It used to descend
        into a ``Shapes`` container but then only stamp the ``Shape`` elements
        directly inside it, so a group's grandchildren arrived in the copy
        still carrying their original IDs.

        Only ``Shape`` elements are numbered. A ``Shapes`` container is not a
        shape and takes no ``ID`` in the schema, and numbering one consumed an
        ID that ``Page._set_max_ids`` could not see, since that scan looks at
        shapes; a later allocation could then hand the same number to a real
        shape. A root element outside the Visio namespace is left alone for the
        same reason, so a caller that hand-builds one must namespace it to have
        it numbered.

        :param shape: root of the copied subtree, normally a ``Shape`` element
        :param page: destination page, which owns the ID high-water mark
        :param id_map: mapping to extend, so several subtrees copied together
            share one map; a new one is started when omitted
        :return: the ID map, old ID -> new ID, for ``update_ids`` to apply
        """
        page.vis._require_open("VisioFile.increment_shape_ids()")
        page._set_max_ids()
        if id_map is None:
            id_map = {}
        for element in shape.iter(f"{namespace}Shape"):
            self.set_new_id(element, page, id_map)
        return id_map

    def set_new_id(self, element: Element, page: Page, id_map: dict[str, int]) -> int:
        """Stamp the next free page ID onto one Shape element.

        Call this only for a ``Shape``; ``increment_shape_ids`` is what decides
        which elements qualify.
        """
        max_id = page._next_shape_id()
        if element.attrib.get("ID"):
            current_id = element.attrib["ID"]
            id_map[current_id] = max_id  # record mappings
        element.attrib["ID"] = str(max_id)
        return max_id  # return new id for info

    def update_ids(self, shape: Element, id_map: dict[str, int]) -> Element:
        """Remap every sheet reference in a copied subtree through ``id_map``.

        Covers the shape's own cells as well as its descendants', and cells
        nested inside Sections, since a formula anywhere in the subtree may
        address a shape whose id the copy has just changed.
        """
        for cell in shape.iter(f"{namespace}Cell"):
            formula = cell.attrib.get("F")
            if formula is None or "Sheet" not in formula:
                continue
            remapped = _remap_sheet_references(formula, id_map)
            if remapped != formula:
                cell.attrib["F"] = remapped
        return shape

    def close_vsdx(self) -> None:
        self.file_open = False
        media, self._media = self._media, None
        if media is not None:
            media.close()

    def _main_part_content_type(self) -> str:
        """The declared content type of `/visio/document.xml`."""
        content_types = self._part_root(self.content_types_xml, "[Content_Types].xml")
        overrides = content_types.findall(f"{cont_types_namespace}Override")
        for override in overrides:
            if override.attrib.get("PartName") == "/visio/document.xml":
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
            raise ValueError(
                f"cannot save a macro-enabled package as {filename!r}: it declares "
                f"{MACRO_ENABLED_CONTENT_TYPE} and still contains its vbaProject part, so it must be saved "
                "with a .vsdm extension"
            )
        raise ValueError(
            f"cannot save {filename!r}: the .vsdm extension is for macro-enabled packages, and this "
            f"package declares {self._main_part_content_type() or DRAWING_CONTENT_TYPE}"
        )

    def _destination_filename(self, new_filename: str) -> str:
        """Resolve a named save destination, appending the matching extension if absent."""
        if self._check_destination_kind(new_filename) is not None:
            return new_filename
        return new_filename + (".vsdm" if self.is_macro_enabled else ".vsdx")

    def _in_place_filename(self) -> str:
        """The source path, checked against the package kind but never renamed.

        A save with no destination keeps the name it was opened under, so the
        check can only refuse -- silently rewriting the caller's path would be
        a worse surprise than the mismatch itself. The constructor already
        rejects anything but a .vsdx or .vsdm name, so there is never a missing
        extension to append here.
        """
        self._check_destination_kind(self.filename)
        return self.filename

    def save_vsdx(self, new_filename: str | None = None) -> None:
        """save the VisioFile object as new vsdx file

        :param new_filename: path to save vsdx file. A `.vsdx` or `.vsdm`
            extension must match the package's own kind; any other name gets the
            matching extension appended. Omit it to save over the source file,
            or over `filename` if that has been reassigned since the document
            was opened; that name is checked the same way but never renamed.
        :type new_filename: str
        :raises ValueError: if the extension contradicts the package kind

        """
        self._require_open("VisioFile.save_vsdx()")
        if not self._package.names():
            raise ValueError("cannot save an empty package")

        # resolve the destination first, so a refused extension writes nothing
        target = self._in_place_filename() if new_filename is None else self._destination_filename(new_filename)

        # sync edits made through a `getbuffer()` memoryview on a buffer the
        # view handed out, which no write-through method could see; done after
        # the destination check, so a refused save still changes nothing
        if isinstance(self.zip_file_contents, ZipFileContentsView):
            self.zip_file_contents.sync()

        # every change is already in the store -- the trees this document edits
        # are the store's own -- so saving is writing it, once, member by member.
        # An in-place save writes back over the absolute source `PackageStore`
        # captured at open, not over `self.filename`, which may be relative and
        # resolve against a different working directory by the time this runs.
        # The exception is a `filename` the caller has reassigned since open:
        # a plain save went to `self.filename` before the store existed, so a
        # new one is where the caller means the save to go. It goes there as an
        # explicit target, which leaves the store's source where it was.
        redirected = new_filename is None and self.filename != self._opened_filename
        self._package.save(target if new_filename is not None or redirected else None)
