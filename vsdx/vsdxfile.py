from __future__ import annotations

import contextlib
import copy
import io
import json
import math
import os
import posixpath
import re
import shutil
import sys
import tempfile
import xml.dom.minidom as minidom  # minidom used for prettyprint
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol
from xml.etree.ElementTree import Element

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

import vsdx

from .logging_support import attach_debug_stream_handler, get_logger

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
from .xmlio import (  # noqa: E402
    adopt_prefixes,
    file_to_xml,
    register_namespaces,
    require_element,
    require_root,
    require_tree,
    require_xml_tree,
    xml_to_file,
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

# A ShapeSheet formula addresses another shape as `Sheet.5!Cell` or `Sheet5!Cell`.
# Visio writes the dotted form in inherited cells and the undotted form in the
# formulas it generates for connector glue -- `_XFTRIGGER(Sheet5!EventXFMod)`,
# `PAR(PNT(Sheet5!Connections.X1,...))` -- where the reference is also nested
# inside a function call rather than at the start of the formula.
_SHEET_REFERENCE_RE = re.compile(r"\bSheet(\.?)(\d+)!")


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


class PackageLimitError(OSError):
    """A package violated a load limit: size, member count, ratio, names or duplicates.

    ``reason`` is a stable slug (``member_size``, ``total_size``,
    ``member_count``, ``compression_ratio``, ``duplicate_member``,
    ``member_name``, ``limits_file``) so callers can branch by failure mode.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class PackageLimits:
    """Conservative caps applied while loading a package from disk.

    The defaults suit documents from unknown sources: a hostile or accidental
    archive is rejected well before it can exhaust process memory. Even at the
    caps the loader materialises at most ``max_total_uncompressed`` bytes
    (256 MiB by default); callers loading larger trusted documents should raise
    the caps explicitly via ``VisioFile(filename, limits=PackageLimits(...))``
    or a JSON file passed as ``limits_path`` with the same keys.
    """

    max_members: int = 512
    max_member_size: int = 64 * 1024 * 1024
    max_total_uncompressed: int = 256 * 1024 * 1024
    max_ratio: float = 100.0

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.max_ratio)):
            raise ValueError("max_ratio must be a finite number")
        for field_name in ("max_members", "max_member_size", "max_total_uncompressed"):
            value = getattr(self, field_name)
            if not math.isfinite(float(value)):
                raise ValueError(f"{field_name} must be a finite number")
            if value < 1:
                raise ValueError(f"{field_name} must be at least 1")
        if self.max_ratio < 1.0:
            raise ValueError("max_ratio must be at least 1.0")

    @classmethod
    def from_json_file(cls, path: str) -> PackageLimits:
        """Load limits from a JSON object; unusable files are PackageLimitError, not surprises."""
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError) as error:  # ValueError covers json.JSONDecodeError
            raise PackageLimitError("limits_file", f"unable to read limits file {path}: {error}") from error
        if not isinstance(payload, dict):
            raise PackageLimitError("limits_file", f"limits file {path} must contain a JSON object")
        known = {"max_members", "max_member_size", "max_total_uncompressed", "max_ratio"}
        unknown = sorted(set(payload) - known)
        if unknown:
            raise PackageLimitError("limits_file", f"unknown limit keys in {path}: {', '.join(unknown)}")
        try:
            return cls(**payload)
        except (TypeError, ValueError) as error:
            raise PackageLimitError("limits_file", f"invalid limits in {path}: {error}") from error


def _check_member_names(names: list[str]) -> None:
    """Reject duplicate and path-like unsafe member names before any state is materialised."""
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise PackageLimitError("duplicate_member", f"duplicate package member: {name}")
        seen.add(name)
        unsafe = (
            name.startswith("/")
            or name.startswith("\\")
            or ":" in name
            or "\\" in name
            or any(part == ".." for part in name.split("/"))
        )
        if unsafe:
            raise PackageLimitError("member_name", f"unsafe package member name: {name!r}")


class _MemberReader(Protocol):
    """Minimal structural type for a readable archive member stream."""

    def read(self, size: int = -1, /) -> bytes: ...


def _read_bounded(reader: _MemberReader, declared_size: int, name: str, limits: PackageLimits) -> bytes:
    """Stream a member through a byte counter so over-delivery cannot bypass the per-member cap."""
    chunks: list[bytes] = []
    received = 0
    while True:
        chunk = reader.read(1024 * 1024)
        if not chunk:
            break
        received += len(chunk)
        if received > limits.max_member_size:
            raise PackageLimitError(
                "member_size",
                f"package member '{name}' delivered {received} bytes (declared {declared_size});"
                f" max_member_size={limits.max_member_size}",
            )
        chunks.append(chunk)
    return b"".join(chunks)


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
        self.pages_xml: ET.ElementTree[ET.Element] | None = None
        self.pages_xml_rels: ET.ElementTree[ET.Element] | None = None
        self.content_types_xml: ET.ElementTree[ET.Element] | None = None
        self.app_xml: ET.ElementTree[ET.Element] | None = None
        self.document_xml: ET.ElementTree[ET.Element] | None = None
        self.document_xml_rels: ET.ElementTree[ET.Element] | None = None
        self.pages: list[Page] = []  # populated by open_vsdx_file()
        self.masters_xml: ET.Element | None = None  # <Masters> root element
        self.master_index: dict[str, Page] = {}  # master page info by item name e.g. 'Dynamic Connector'
        self.master_pages: list[Page] = []  # populated by open_vsdx_file()
        self.file_open = False
        self.zip_file_contents: dict[str, io.BytesIO] = {}  # file contents by file_path
        # the bundled donor packages are expensive to parse, so one Media is
        # shared by every create/connect call on this document (issue #65)
        self._media: vsdx.Media | None = None
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

    @staticmethod
    def _preflight_eocd(path: str, limits: PackageLimits) -> None:
        """Validate the central directory before ZipFile parses it.

        Issue #20 review: the ``ZipFile`` constructor reads the whole central
        directory and builds a ``ZipInfo`` per entry before any of our checks
        run, so a crafted archive with millions of tiny entries costs memory
        proportional to its entry count first.

        Every EOCD/Z64 field is attacker-controlled and ``ZipFile`` reserves
        the right to reinterpret them, so this preflight derives the
        central-directory start the same way ``ZipFile`` does — from the EOCD
        locator's own file position minus the declared directory size — and
        then walks the real records (headers only, no payload) until one
        fails to parse, the declared directory is exhausted, or the member
        cap is exceeded. A falsified count, offset, or ZIP64 sentinel cannot
        hide entries from the walk.
        """
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            window = min(size, 65536 + 22)  # EOCD comment is at most 64 KiB
            handle.seek(size - window)
            tail = handle.read()
        signature = b"PK\x05\x06"
        position = tail.rfind(signature)
        if position == -1:
            return  # not a zip / truncated: ZipFile will raise its own error
        eocd_file_position = size - window + position  # absolute offset of the EOCD record
        declared_entries = int.from_bytes(tail[position + 10 : position + 12], "little")
        cd_size = int.from_bytes(tail[position + 12 : position + 16], "little")
        # note: the classic cd_offset field is deliberately not read — the
        # walk derives its start from the EOCD's own file position, matching
        # zipfile's concat adjustment, so a falsified offset cannot misdirect
        # the scan away from the records ZipFile will parse.

        # Detect ZIP64 by its locator (PK\x06\x07), exactly as zipfile does:
        # the locator may exist regardless of the classic count, and when the
        # ZIP64 EOCD is found it replaces all classic values.
        locator = tail.rfind(b"PK\x06\x07")
        if locator != -1:
            z64_offset = int.from_bytes(tail[locator + 8 : locator + 16], "little")
            z64_tail_position = z64_offset - (size - window)
            if 0 <= z64_tail_position <= len(tail) - 56 and tail[z64_tail_position : z64_tail_position + 4] == b"PK\x06\x06":
                z64 = z64_tail_position
                z64_count_this_disk = int.from_bytes(tail[z64 + 24 : z64 + 32], "little")
                z64_total = int.from_bytes(tail[z64 + 32 : z64 + 40], "little")
                z64_cd_size = int.from_bytes(tail[z64 + 40 : z64 + 48], "little")
                z64_cd_offset = int.from_bytes(tail[z64 + 48 : z64 + 56], "little")
                if z64_count_this_disk != 0xFFFF and z64_total != 0xFFFF:
                    declared_entries = z64_total
                if z64_cd_size != 0xFFFFFFFF and z64_cd_offset != 0xFFFFFFFF:
                    cd_size = z64_cd_size  # the walk derives its start from cd_size + EOCD position

        if declared_entries > limits.max_members:
            raise PackageLimitError(
                "member_count",
                f"package declares {declared_entries} entries in its central directory; max_members={limits.max_members}",
            )
        if cd_size == 0 or cd_size > size:
            return
        # Derive the effective directory start the way zipfile's
        # _EndRecData does: concat-adjust from the EOCD's own location.
        effective_start = max(eocd_file_position - cd_size, 0)
        # Walk the real central-directory records: each header is at least 46
        # bytes and carries its own name/extra/comment lengths. The declared
        # count is never trusted — including a declared zero, which must not
        # skip the walk while ZipFile would still parse entries by size — so
        # records are visited until one fails to parse, the declared
        # directory is exhausted, or the member cap is exceeded.
        walked = 0
        with open(path, "rb") as handle:
            handle.seek(effective_start)
            while walked < declared_entries or declared_entries == 0:
                header = handle.read(46)
                if len(header) < 46 or header[:4] != b"PK\x01\x02":
                    break  # malformed/short directory: ZipFile will judge it
                name_len = int.from_bytes(header[28:30], "little")
                extra_len = int.from_bytes(header[30:32], "little")
                comment_len = int.from_bytes(header[32:34], "little")
                record_len = 46 + name_len + extra_len + comment_len
                if record_len > 46 + 3 * 65535:  # impossible per spec: corrupt
                    break
                if handle.seek(record_len - 46, 1) > size:
                    break
                walked += 1
                if walked > limits.max_members:
                    break  # cap already exceeded; no need to count further
        if walked > limits.max_members:
            raise PackageLimitError(
                "member_count",
                f"package central directory holds at least {walked} entries; max_members={limits.max_members}",
            )

    def _load_zip_file_contents_to_memory(self) -> None:
        """Open zip file and create a dictionary of file like objects by file_path.

        The end-of-central-directory entry count is checked before ``ZipFile``
        parses the central directory, ZipInfo metadata is checked against
        ``self.limits`` before any member body is read, and reads stream
        through a byte counter so the bound holds even if the archive's
        metadata disagrees with its contents.
        """
        limits = self.limits
        self._preflight_eocd(self.filename, limits)
        with zipfile.ZipFile(self.filename, "r") as zip_ref:
            infos = zip_ref.infolist()
            if len(infos) > limits.max_members:
                raise PackageLimitError(
                    "member_count",
                    f"package has {len(infos)} entries (including directories); max_members={limits.max_members}",
                )
            _check_member_names([info.filename for info in infos])
            file_infos = [info for info in infos if info.filename and not info.filename.endswith("/")]
            declared_total = 0
            for info in file_infos:
                declared_total += info.file_size
                if info.file_size > limits.max_member_size:
                    raise PackageLimitError(
                        "member_size",
                        f"package member '{info.filename}' declares {info.file_size} bytes;"
                        f" max_member_size={limits.max_member_size}",
                    )
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > limits.max_ratio:
                    raise PackageLimitError(
                        "compression_ratio",
                        f"package member '{info.filename}' has compression ratio {ratio:.1f}; max_ratio={limits.max_ratio}",
                    )
            if declared_total > limits.max_total_uncompressed:
                raise PackageLimitError(
                    "total_size",
                    f"package declares {declared_total} uncompressed bytes;"
                    f" max_total_uncompressed={limits.max_total_uncompressed}",
                )
            for info in file_infos:
                path = f"{self.directory}/{info.filename}"
                with zip_ref.open(info, "r") as member_reader:
                    content = _read_bounded(member_reader, info.file_size, info.filename, limits)
                self.zip_file_contents[path] = io.BytesIO(content)

    def _save_zip_file_contents_to_disk(self, save_filename: str) -> None:
        """Atomically save the in-memory package to a .vsdx file."""
        target = os.path.abspath(save_filename)
        target_dir = os.path.dirname(target)
        os.makedirs(target_dir, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{os.path.basename(target)}.", suffix=".tmp", dir=target_dir)
        os.close(fd)
        try:
            with zipfile.ZipFile(temporary, "w") as zipf:
                for file_path, file_content in self.zip_file_contents.items():
                    file_path_in_zip = file_path.replace(self.directory + "/", "")
                    content = file_content.getvalue()
                    if file_path_in_zip.endswith(".xml") or file_path_in_zip.endswith(".rels"):
                        zipf.writestr(file_path_in_zip, content.decode("utf-8"))
                    else:
                        zipf.writestr(file_path_in_zip, content)
            mode_source = target if os.path.exists(target) else os.path.abspath(self.filename)
            if os.path.exists(mode_source):
                shutil.copymode(mode_source, temporary)
            os.replace(temporary, target)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary)

    def open_vsdx_file(self) -> None:
        self._load_zip_file_contents_to_memory()

        # load each page file into an ElementTree object
        self.load_pages()
        self.load_master_pages()
        self.file_open = True

    def _pages_filename(self):
        page_dir = f"{self.directory}/visio/pages/"
        pages_filename = page_dir + "pages.xml"  # pages.xml contains Page name, width, height, mapped to Id
        return pages_filename

    @property
    @override
    def _masters_folder(self) -> str:
        return f"{self.directory}/visio/masters"

    def load_pages(self) -> None:
        rel_dir = f"{self.directory}/visio/pages/_rels/"
        page_dir = f"{self.directory}/visio/pages/"

        rel_filename = rel_dir + "pages.xml.rels"
        rels = require_root(rel_filename, self.zip_file_contents, "pages.xml.rels")
        self.pages_xml_rels = file_to_xml(
            rel_filename, self.zip_file_contents
        )  # store pages.xml.rels so pages can be added or removed
        if self.debug:
            logger.debug("Relationships(%s)\n%s", rel_filename, VisioFile.pretty_print_element(rels))
        relid_page_dict = {}

        for rel in rels:
            rel_id = rel.attrib["Id"]
            page_file = rel.attrib["Target"]
            relid_page_dict[rel_id] = page_file

        pages_filename = self._pages_filename()  # pages contains Page name, width, height, mapped to Id
        pages = require_root(pages_filename, self.zip_file_contents, "pages.xml")
        self.pages_xml = file_to_xml(pages_filename, self.zip_file_contents)  # store xml so pages can be removed
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

            new_page = Page(
                require_xml_tree(page_path, self.zip_file_contents, "page part"), page_path, page_name, page_id, rel_id, self
            )
            # look for visio/pages/_rels/page3.xml.rels
            page_rels_path = _page_relationship_path(rel_dir, page_path)

            if page_rels_path in self.zip_file_contents:
                new_page.rels_xml_filename = page_rels_path
                new_page.rels_xml = file_to_xml(page_rels_path, self.zip_file_contents)
            self.pages.append(new_page)

            if self.debug:
                logger.debug("Page(%s)\n%s", new_page.filename, VisioFile.pretty_print_element(new_page.xml))

        self.content_types_xml = file_to_xml(f"{self.directory}/[Content_Types].xml", self.zip_file_contents)
        # TODO: add correctness cross-check. Or maybe the other way round, start from [Content_Types].xml
        #       to get page_dir and other paths...

        self.app_xml = file_to_xml(
            f"{self.directory}/docProps/app.xml", self.zip_file_contents
        )  # note: files in docProps may be missing
        self.document_xml = file_to_xml(f"{self.directory}/visio/document.xml", self.zip_file_contents)
        self.document_xml_rels = file_to_xml(f"{self.directory}/visio/_rels/document.xml.rels", self.zip_file_contents)

    @override
    def load_master_pages(self) -> None:
        # get data from /visio/masters folder
        master_rel_path = f"{self.directory}/visio/masters/_rels/masters.xml.rels"

        master_rels_data = file_to_xml(master_rel_path, self.zip_file_contents)
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

        # load masters.xml file
        masters_path = f"{self.directory}/visio/masters/masters.xml"
        masters_xml = file_to_xml(
            masters_path, self.zip_file_contents
        )  # contains more info about master page (i.e. Name, Icon)
        self.masters_xml = masters_xml.getroot() if masters_xml is not None else None

        # for each master page, create the Page object
        for master in self.masters_xml if self.masters_xml is not None else []:
            master_name = master.attrib.get("NameU") or master.attrib.get("Name") or "Unknown"
            rel_id = require_element(master.find(f"{namespace}Rel"), "Master/Rel").attrib[f"{r_namespace}id"]
            master_id = master.attrib["ID"]
            master_unique_id = master.attrib.get("UniqueID")
            master_base_id = master.attrib.get("BaseID")

            master_path = relid_to_path[rel_id]

            master_page = Page(
                require_xml_tree(master_path, self.zip_file_contents, "master part"),
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

                # remove the page's relationship from pages.xml.rels (issue #7:
                # a dangling rId pointing at a deleted part corrupts the OPC graph)
                rels_root = self._part_root(self.pages_xml_rels, "pages.xml.rels")
                page_rel = rels_root.find(f'{document_rels_namespace}Relationship[@Id="{page.rel_id}"]')
                if page_rel is not None:
                    rels_root.remove(page_rel)

                # remove the page's content-type override
                content_types = self._part_root(self.content_types_xml, "[Content_Types].xml")
                part_name = f"/visio/pages/{os.path.basename(page.filename)}"
                override = content_types.find(f'{cont_types_namespace}Override[@PartName="{part_name}"]')
                if override is not None:
                    content_types.remove(override)

                # remove the page's own rels part if one exists
                if page.rels_xml_filename and page.rels_xml_filename in self.zip_file_contents:
                    self.zip_file_contents.pop(page.rels_xml_filename)

                # remove page<index>.xml file
                self.zip_file_contents.pop(self.pages[index].filename)
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
        # allocate an unused rel-id rather than assuming count+1 (issue #7)
        used_rel_ids = {rel.attrib["Id"] for rel in rels_root}
        counter = 1
        while f"rId{counter}" in used_rel_ids:
            counter += 1
        new_page_relid = f"rId{counter}"

        new_page_rel = {
            "Target": new_page_filename,
            "Type": "http://schemas.microsoft.com/visio/2010/relationships/page",
            "Id": new_page_relid,
        }
        rels_root.append(Element("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship", new_page_rel))

        return new_page_relid

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
        """
        page_dir = f"{self.directory}/visio/pages/"
        taken = set(self.zip_file_contents)
        rels_root = self._part_root(self.pages_xml_rels, "pages.xml.rels")
        taken.update(f"{page_dir}{rel.attrib['Target']}" for rel in rels_root)
        counter = 1
        while f"{page_dir}page{counter}.xml" in taken:
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
        content_types = self._part_root(self.content_types_xml, "[Content_Types].xml")

        # idempotent: skip if this exact PartName is already registered
        for existing in content_types.findall(f"{cont_types_namespace}Override"):
            if existing.attrib.get("PartName") == part_name_path:
                return

        content_types_attribs = {
            "PartName": part_name_path,
            "ContentType": content_type,
        }
        override_element = Element(f"{cont_types_namespace}Override", content_types_attribs)
        # find existing elements with same content_type
        matching_overrides = content_types.findall(f'{cont_types_namespace}Override[@ContentType="{content_type}"]')
        if len(matching_overrides):  # insert after similar elements
            idx = list(content_types).index(matching_overrides[-1])
            content_types.insert(idx + 1, override_element)
        else:  # add at end of list
            content_types.append(override_element)

    def _update_content_types_xml(self, new_page_filename: str) -> None:
        # todo: use generic function above
        content_types = self._part_root(self.content_types_xml, "[Content_Types].xml")

        content_types_attribs = {
            "PartName": f"/visio/pages/{new_page_filename}",
            "ContentType": "application/vnd.ms-visio.page+xml",
        }
        content_types_element = Element(f"{cont_types_namespace}Override", content_types_attribs)

        # add the new element after the last such element
        # first find the index:
        all_page_overrides = content_types.findall(
            f'{cont_types_namespace}Override[@ContentType="application/vnd.ms-visio.page+xml"]'
        )
        idx = list(content_types).index(all_page_overrides[-1])

        # then add it:
        content_types.insert(idx + 1, content_types_element)

    def document_rels(self) -> list[Element]:
        rels_root = self._part_root(self.document_xml_rels, "_rels/.rels")
        rels = rels_root.findall(f"{document_rels_namespace}Relationship")
        return rels

    @override
    def _add_document_rel(self, rel_type: str, target: str) -> None:
        # idempotent: skip if an identical relationship already exists
        for r in self.document_rels():
            if r.attrib.get("Type") == rel_type and r.attrib.get("Target") == target:
                return
        rel_ids = [int(str(r.attrib.get("Id")).replace("rId", "")) for r in self.document_rels()]
        new_rel = Element(
            f"{document_rels_namespace}Relationship",
            {
                "Id": f"rId{max(rel_ids) + 1}",
                "Type": rel_type,
                "Target": target,
            },
        )
        self._part_root(self.document_xml_rels, "_rels/.rels").append(new_rel)

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

    def _titles_of_parts_list(self) -> list[str]:
        # return list of strings
        vector = require_element(self._titles_of_parts().find(f".//{vt_namespace}vector"), "TitlesOfParts vector")
        return [t.text or "" for t in vector]

    def _add_titles_of_parts_item(self, title: str) -> None:
        titles = self._titles_of_parts()
        # new variant appended to vector Element
        vector = require_element(titles.find(f".//{vt_namespace}vector"), "TitlesOfParts vector")
        new_title = Element(f"{vt_namespace}lpstr", {})
        new_title.text = title
        vector.append(new_title)
        # add one to vector size, as we have added two new variant elements
        vector.attrib["size"] = str(int(vector.attrib.get("size", 0)) + 1)

    def _get_app_xml_value(self, name: str) -> str | None:
        variants = self._heading_pairs().findall(f".//{vt_namespace}variant")
        # find Pages in headings
        for index in range(len(variants)):
            v = variants[index]
            lpstr = v.find(f".//{vt_namespace}lpstr")
            if type(lpstr) is Element and lpstr.text == name:
                next_v = variants[index + 1] if index < (len(variants) - 1) else None  # next variant if there is one
                i4 = next_v.find(f".//{vt_namespace}i4") if type(next_v) is Element else None
                if type(i4) is Element:
                    return i4.text or ""

    def _set_app_xml_value(self, name: str, value: str) -> None:
        variants = self._heading_pairs().findall(f".//{vt_namespace}variant")
        # find Pages in headings
        for index in range(len(variants)):
            v = variants[index]
            lpstr = v.find(f".//{vt_namespace}lpstr")
            if type(lpstr) is Element and lpstr.text == name:
                next_v = variants[index + 1] if index < (len(variants) - 1) else None  # next variant if there is one
                i4 = next_v.find(f".//{vt_namespace}i4") if type(next_v) is Element else None
                if type(i4) is Element:
                    i4.text = value
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
        # todo: use _add_titles_of_parts_item()
        heading_pairs = self._heading_pairs()
        i4 = require_element(heading_pairs.find(f".//{vt_namespace}i4"), "HeadingPairs i4")
        num_pages = int(i4.text or 0)
        i4.text = str(num_pages + 1)  # increment as page added

        vector = require_element(self._titles_of_parts().find(f"{vt_namespace}vector"), "TitlesOfParts vector")

        lpstr = Element(f"{vt_namespace}lpstr")
        lpstr.text = new_page_name
        vector.append(lpstr)  # add new lpstr element with new page name
        vector_size = int(vector.attrib["size"])
        vector.set("size", str(vector_size + 1))  # increment as page added

    def _remove_page_from_app_xml(self, page_name: str):
        if self.app_xml is not None:
            logger.debug("_remove_page_from_app_xml()")
            heading_pairs = self._heading_pairs()
            i4 = require_element(heading_pairs.find(f".//{vt_namespace}i4"), "HeadingPairs i4")
            num_pages = int(i4.text or 0)
            i4.text = str(num_pages - 1)  # decrement as page removed

            vector = require_element(self._titles_of_parts().find(f"{vt_namespace}vector"), "TitlesOfParts vector")

            for lpstr in vector.findall(f"{vt_namespace}lpstr"):
                if lpstr.text == page_name:
                    vector.remove(lpstr)  # remove page from list of names
                    break

            vector_size = int(vector.attrib["size"])
            vector.set("size", str(vector_size - 1))  # decrement as page removed

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
        self._update_content_types_xml(new_page_filename)

        # update app.xml, if it exists
        if self.app_xml:
            self._add_page_to_app_xml(page_name)

        # Update VisioFile object; the page carries its real ID and relationship
        # id immediately (issue #7: they were blank until a reload)
        page_id = new_page_element.attrib["ID"]
        new_page = Page(new_page_xml, new_page_path, page_name, page_id, new_page_relid, self)
        if source_page is not None and source_page.rels_xml is not None:
            source_rels_root = require_element(source_page.rels_xml.getroot(), "source page relationships root")
            new_page.rels_xml = ET.ElementTree(copy.deepcopy(source_rels_root))
            rel_dir = f"{self.directory}/visio/pages/_rels/"
            new_page.rels_xml_filename = _page_relationship_path(rel_dir, new_page_path)

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
    # TODO: is this never used?
    def get_shape_text(shape: Element) -> str:
        # technically the below is not an exact replacement of the above...
        text = ""
        text_elem = shape.find(f"{namespace}Text")
        if text_elem is not None:
            text = "".join(text_elem.itertext())
        return text

    @staticmethod
    # TODO: is this never used?
    def set_shape_text(shape: Element, text: str) -> None:
        t = shape.find(f"{namespace}Text")  # type: Element
        if t is not None:
            if t.text:
                t.text = text
            else:
                t[0].tail = text

    # context = {'customer_name':'codypy.com', 'year':2020 }
    # example shape text "For {{customer_name}}  (c){{year}}" -> "For codypy.com (c)2020"
    @staticmethod
    def apply_text_context(shapes: Element, context: dict[str, object]) -> None:

        def _replace_shape_text(shape: Element, context: dict[str, object]) -> None:
            text = VisioFile.get_shape_text(shape)

            for key in context:
                r_key = "{{" + key + "}}"
                text = text.replace(r_key, str(context[key]))
            VisioFile.set_shape_text(shape, text)

        for shape in shapes.findall(f"{namespace}Shapes"):
            VisioFile.apply_text_context(shape, context)  # recursive call
            _replace_shape_text(shape, context)

        for shape in shapes.findall(f"{namespace}Shape"):
            _replace_shape_text(shape, context)

    @staticmethod
    def get_shape_id(shape: Element) -> str:
        return shape.attrib["ID"]

    def _shared_media(self) -> vsdx.Media:
        """The bundled media/palette documents for this VisioFile.

        Created on first use and reused for every subsequent create/connect
        call, so a loop of N shapes parses the donor packages once rather than
        N times. Ownership stays here: `close_vsdx` closes and drops it, and a
        closed document is refused rather than handed a replacement, so the
        only pair that ever exists is one this document will close (issue #242).
        """
        self._require_open("building a shape or connector")
        if self._media is None:
            self._media = vsdx.Media()
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

        A record follows only the IDs this call vacated: on the page before,
        gone after. Renumbering does not always retire an ID - ``copy_shape``
        leaves the original where it was, and the Jinja loop renumbers the
        duplicates while the shape they were copied from keeps its ID. Nor is
        every ID in the map one this page ever had: a subtree arriving from
        elsewhere brings its own, and a stale record that happens to name one
        of those numbers belongs to whatever wrote the file, not to the shape
        now carrying it.

        :param shape: root of the subtree to renumber, normally a ``Shape`` element
        :param page: page that owns the ID high-water mark and the records
        :param id_map: mapping to extend, so several subtrees renumbered
            together share one map; a new one is started when omitted
        :return: the ID map, old ID -> new ID
        """
        before = page._shape_ids()
        id_map = self.increment_shape_ids(shape, page, id_map)
        self.update_ids(shape, id_map)
        after = page._shape_ids()
        page._remap_connect_records({old: new for old, new in id_map.items() if old in before and old not in after})
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
            which is checked the same way but never renamed.
        :type new_filename: str
        :raises ValueError: if the extension contradicts the package kind

        """
        self._require_open("VisioFile.save_vsdx()")
        if not self.zip_file_contents:
            raise ValueError("cannot save an empty package")

        # resolve the destination before re-serialising anything, so a refused
        # extension leaves the in-memory package untouched
        target = self._in_place_filename() if new_filename is None else self._destination_filename(new_filename)

        # write pages.xml.rels
        xml_to_file(
            self._part_tree(self.pages_xml_rels, "pages.xml.rels"),
            f"{self.directory}/visio/pages/_rels/pages.xml.rels",
            self.zip_file_contents,
        )

        # write pages.xml file - in case pages added removed
        xml_to_file(self._part_tree(self.pages_xml, "pages.xml"), self._pages_filename(), self.zip_file_contents)

        # write the master pages to file
        for page in self.master_pages:  # type: Page
            xml_to_file(page.xml, page.filename, self.zip_file_contents)

        # write the pages to file
        for page in self.pages:  # type: Page
            xml_to_file(page.xml, page.filename, self.zip_file_contents)
            if page.rels_xml_filename is not None:
                xml_to_file(require_tree(page.rels_xml, "page rels"), page.rels_xml_filename, self.zip_file_contents)

        # write [content_Types].xml
        xml_to_file(
            self._part_tree(self.content_types_xml, "[Content_Types].xml"),
            f"{self.directory}/[Content_Types].xml",
            self.zip_file_contents,
        )

        # write app.xml
        if self.app_xml is not None:
            xml_to_file(self.app_xml, f"{self.directory}/docProps/app.xml", self.zip_file_contents)

        # write document.xml
        xml_to_file(
            self._part_tree(self.document_xml, "document.xml"), f"{self.directory}/visio/document.xml", self.zip_file_contents
        )

        # write document.xml.rels
        xml_to_file(
            self._part_tree(self.document_xml_rels, "document.xml.rels"),
            f"{self.directory}/visio/_rels/document.xml.rels",
            self.zip_file_contents,
        )

        self._save_zip_file_contents_to_disk(target)
