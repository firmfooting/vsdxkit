"""Turn a blank drawing Visio saved into the template Document.new() copies, with nothing of the machine that saved it.

    python tools/make_blank_template.py RAW.vsdx src/vsdxkit/_bundled/blank.vsdx --forbid NAME [--forbid NAME ...] [--empty-page]

The shipped blank.vsdx was made from tests/fixtures/com_reference/s01_autoconnect_right.vsdx with
``--empty-page``, which deletes every shape on the first page (through vsdxkit, so the saved form is
vsdxkit's) before cleaning. Without the flag RAW is used as it is, for a blank drawing saved by Visio.
Drops the thumbnail and the custom properties, blanks the author, the company and every date, and
refuses to write a file in which any ``--forbid`` text still appears in any part. Visio saves the
machine's user name as the author, so pass it. The archive is written with the fixed member form
the deterministic save uses, so running this twice on one raw file gives one output.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
import zipfile
from pathlib import Path

DROPPED = ("docProps/thumbnail.emf", "docProps/custom.xml")
"""The parts that carry a rendering and build numbers, which a template does not need."""
FIXED_DATE = "2000-01-01T00:00:00Z"
"""The date written into every date property."""
EMPTIED = ("dc:creator", "cp:lastModifiedBy", "dc:title", "Manager", "Company", "Template", "HyperlinkBase")
"""The properties whose text is emptied."""
DATED = ("cp:lastPrinted", "dcterms:created", "dcterms:modified")
"""The properties whose text is replaced with the fixed date."""


def _empty(text: str, tag: str) -> str:
    """`text` with the element `tag` emptied, whether it is written empty, with text or self-closed."""
    return re.sub(rf"<{tag}(\s[^>]*)?(/>|>.*?</{tag}>)", lambda m: f"<{tag}{m.group(1) or ''}></{tag}>", text, flags=re.S)


def _date(text: str, tag: str) -> str:
    """`text` with the date element `tag` given the fixed date."""
    return re.sub(rf"(<{tag}(?:\s[^>]*)?>).*?(</{tag}>)", rf"\g<1>{FIXED_DATE}\g<2>", text, flags=re.S)


def clean(members: dict[str, bytes]) -> dict[str, bytes]:
    """The parts of the template: `members` less the dropped parts, with their references and the machine's details removed."""
    out = {name: data for name, data in members.items() if name not in DROPPED}
    rels = out["_rels/.rels"].decode("utf-8")
    for part in DROPPED:
        rels = re.sub(rf'<Relationship [^>]*Target="{re.escape(part)}"[^>]*/>', "", rels)
    out["_rels/.rels"] = rels.encode("utf-8")
    types = out["[Content_Types].xml"].decode("utf-8")
    types = re.sub(r'<Override PartName="/docProps/custom.xml"[^>]*/>', "", types)
    if not any(name.endswith(".emf") for name in out):
        types = re.sub(r'<Default Extension="emf"[^>]*/>', "", types)
    out["[Content_Types].xml"] = types.encode("utf-8")
    for name in ("docProps/core.xml", "docProps/app.xml"):
        text = out[name].decode("utf-8")
        for tag in EMPTIED:
            text = _empty(text, tag)
        for tag in DATED:
            text = _date(text, tag)
        out[name] = text.encode("utf-8")
    return out


def write(members: dict[str, bytes], target: Path) -> None:
    """Write `members` to `target` stored, with [Content_Types].xml first and then the rest by name, under a fixed date."""
    ordered = sorted(members.items(), key=lambda item: (item[0] != "[Content_Types].xml", item[0]))
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in ordered:
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o600 << 16
            archive.writestr(info, data)


def main(argv: list[str] | None = None) -> int:
    """Clean RAW into OUT; exit 1, writing nothing, if a forbidden text survives."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("raw", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument(
        "--forbid", action="append", default=[], help="text that must not appear in any part, such as the saving user's name"
    )
    parser.add_argument("--empty-page", action="store_true", help="delete every shape on RAW's first page before cleaning")
    args = parser.parse_args(argv)
    if args.empty_page:
        from vsdxkit.document import Document

        document = Document.open(args.raw)
        for shape in list(document.pages[0].shapes):
            if shape.is_attached:  # deleting a connector's end takes the connector with it
                shape.delete()
        args.raw = Path(tempfile.mkdtemp()) / "emptied.vsdx"
        document.save(args.raw)
    with zipfile.ZipFile(args.raw) as archive:
        members = {i.filename: archive.read(i) for i in archive.infolist() if not i.is_dir()}
    cleaned = clean(members)
    for name, data in cleaned.items():
        for text in args.forbid:
            if text.encode("utf-8") in data or text.encode("utf-16-le") in data:
                print(f"{name} still contains {text!r}; not writing {args.out}", file=sys.stderr)
                return 1
    write(cleaned, args.out)
    print(f"wrote {args.out}: {len(cleaned)} parts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
