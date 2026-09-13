import codecs
import difflib
import hashlib
import zipfile

from .logging_support import get_logger
from .vsdxfile import PackageLimitError

logger = get_logger(__name__)


class VisioFileDiff:
    """Compares two vsdx files

    :param filepath_a: file path of the first :class:`VisioFile` was created from
    :type filepath_a: str
    :param filepath_b: file path of the second :class:`VisioFile` was created from
    :type filepath_b: str
    """

    def __init__(self, filepath_a: str, filepath_b: str):
        if filepath_a == filepath_b:
            raise ValueError("The two file paths should be different")
        if not filepath_a.lower().endswith(".vsdx") or not filepath_b.lower().endswith(".vsdx"):
            raise ValueError("Both files should be vsdx files")

        # load contents of each file
        self.filepath_a = filepath_a
        self.contents_a = self.extract_file_data(filepath_a)
        self.filepath_b = filepath_b
        self.contents_b = self.extract_file_data(filepath_b)

        # check if each file has same contents
        self.diffs = self.get_file_diffs()

    def __str__(self):
        return f"VisioFileDiff(a={self.filepath_a}, b={self.filepath_b})"

    def get_file_diffs(self) -> dict[str, list[str]]:
        common_members = self.common_members()
        diffs = {}
        d = difflib.Differ()
        for member_name in common_members:
            data_a = self.contents_a.get(member_name)
            data_a = VisioFileDiff.break_all_xml_into_lines(data_a or [])
            # print(data_a)
            data_b = self.contents_b.get(member_name)
            data_b = VisioFileDiff.break_all_xml_into_lines(data_b or [])
            if data_a and data_b and data_a != data_b:  # only add diff if contents are not the same
                diffs[member_name] = list(d.compare(data_a, data_b))
        return diffs

    @staticmethod
    def break_all_xml_into_lines(data: list[str]) -> list[str]:
        data_out: list[str] = []
        if data:
            for line in data:  # type: str
                lines = VisioFileDiff.break_xml_into_lines(line)
                for line_part in lines:
                    data_out.append(line_part)
        return data_out

    @staticmethod
    def break_xml_into_lines(x: str) -> list[str]:
        x = x.replace("<", "\n<")  # add CR before each element start
        return x.split("\n")

    def common_members(self) -> list[str]:
        """Return the sorted member names both files have.

        This returned the union until now, so a caller asking which members the
        two files share was handed every member either of them had. The ones
        that are not shared are what ``added_members`` and ``removed_members``
        report.

        ``get_file_diffs`` produces the same diffs either way, because it
        already skipped any member it could not read from both sides.
        """
        return sorted(set(self.contents_a.keys()) & set(self.contents_b.keys()))

    def compare_members(self) -> bool:
        # return True if same, False if different
        return self.contents_a.keys() == self.contents_b.keys()

    def added_members(self) -> set[str]:
        """Return the members file b has and file a has not."""
        return set(self.contents_b.keys()) - set(self.contents_a.keys())

    def removed_members(self) -> set[str]:
        """Return the members file a has and file b has not."""
        return set(self.contents_a.keys()) - set(self.contents_b.keys())

    # Diff-time safety caps (issue #8 review): a diff must not inflate a
    # compression bomb into memory. Text members are decoded incrementally
    # with a hard cap; binary members are hashed incrementally.
    MAX_MEMBER_BYTES = 256 * 1024 * 1024
    MAX_TOTAL_BYTES = 1024 * 1024 * 1024
    _CHUNK = 1024 * 1024

    @staticmethod
    def extract_file_data(file_path: str) -> dict[str, list[str]]:
        """Read archive members in-memory; nothing is written beside the source.

        A same-stem directory next to the .vsdx is user data, not scratch
        space, so no extraction or recursive delete happens (issue #8).
        Undecodable members become a ``binary sha256:<digest>`` line so two
        different binaries compare as changed instead of collapsing into the
        same placeholder. Members stream in chunks with per-member and total
        byte caps, so a compression bomb cannot exhaust memory through this
        path (issue #8 review).
        """
        file_contents: dict[str, list[str]] = {}
        total_read = 0
        with zipfile.ZipFile(file_path, "r") as zip_ref:
            for member in zip_ref.infolist():
                if member.filename.endswith("/"):
                    continue
                if member.file_size > VisioFileDiff.MAX_MEMBER_BYTES:
                    raise PackageLimitError(
                        "member_size",
                        f"package member '{member.filename}' declares {member.file_size} bytes;"
                        f" max_member_size={VisioFileDiff.MAX_MEMBER_BYTES}",
                    )
                total_read += member.file_size
                if total_read > VisioFileDiff.MAX_TOTAL_BYTES:
                    raise PackageLimitError(
                        "total_size",
                        f"package declares more than {VisioFileDiff.MAX_TOTAL_BYTES} uncompressed bytes across members",
                    )
                decoder = codecs.getincrementaldecoder("utf-8")()
                digest = hashlib.sha256()
                lines: list[str] = []
                pending = ""
                pending_cr = False  # a '\r' at chunk end may pair with '\n' next chunk
                is_text = True
                with zip_ref.open(member, "r") as stream:
                    while chunk := stream.read(VisioFileDiff._CHUNK):
                        digest.update(chunk)
                        if not is_text:
                            continue
                        try:
                            text = decoder.decode(chunk)
                        except UnicodeDecodeError:
                            is_text = False
                            continue
                        if pending_cr:
                            text = "\r" + text
                            pending_cr = False
                        if text.endswith("\r"):
                            text = text[:-1]
                            pending_cr = True  # decide CRLF-vs-CR only when the next chunk arrives
                        pending += text
                        *complete, pending = pending.replace("\r\n", "\n").replace("\r", "\n").split("\n")
                        lines.extend(line + "\n" for line in complete)
                if is_text:
                    try:
                        pending += decoder.decode(b"", final=True)
                    except UnicodeDecodeError:
                        is_text = False  # incomplete multibyte sequence at EOF: binary, not text
                if is_text:
                    if pending_cr:
                        pending += "\n"  # lone trailing CR normalises like the whole-payload path did
                    if pending:
                        lines.append(pending)
                    file_contents[member.filename] = lines
                else:
                    file_contents[member.filename] = [f"binary sha256:{digest.hexdigest()}"]
                    logger.debug("member %s is not decodable text; compared by digest", member.filename)
        return file_contents
