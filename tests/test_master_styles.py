"""The style IDs a master imported from another document names are settled in the destination."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from vsdxkit import namespace
from vsdxkit.document import Document
from vsdxkit.pages import Page as Master


def _add_style(document: Document, style_id: str, name: str, based_on: str | None = None) -> None:
    """Add a style sheet with this ID and name to `document`, based on style `based_on` where given."""
    attributes = {"ID": style_id, "NameU": name, "Name": name}
    if based_on is not None:
        attributes["LineStyle"] = based_on
    document._style_sheets().append(Document.new()._style_sheets().makeelement(f"{namespace}StyleSheet", attributes))


def _master_naming(document: Document, style_id: str):
    """The destination's first master, its shapes made to name style `style_id` as `source` numbers it."""
    master = document._masters.pages[0]
    for shape in master.xml.getroot().iter(f"{namespace}Shape"):
        shape.attrib["LineStyle"] = style_id
    return master


def _names(document: Document) -> dict[str, str | None]:
    return {s.attrib["ID"]: s.attrib.get("NameU") for s in document._style_sheets()}


def _line_styles(master) -> set[str]:
    return {s.attrib["LineStyle"] for s in master.xml.getroot().iter(f"{namespace}Shape") if "LineStyle" in s.attrib}


def test_a_style_and_the_style_it_is_based_on_both_come_when_the_destination_has_neither():
    source, destination = Document.new(), Document.new()
    _add_style(source, "20", "Outer", based_on="21")
    _add_style(source, "21", "Inner")
    master = _master_naming(destination, "20")
    destination._settle_master_styles(source, master)
    assert _line_styles(master) == {"20"}
    assert _names(destination)["20"] == "Outer" and _names(destination)["21"] == "Inner"
    based = next(s for s in destination._style_sheets() if s.attrib["ID"] == "20")
    assert based.attrib["LineStyle"] == "21"


def test_the_style_a_style_is_based_on_follows_it_to_a_new_id_when_its_own_is_taken():
    source, destination = Document.new(), Document.new()
    _add_style(source, "20", "Outer", based_on="9")
    _add_style(source, "9", "Inner")
    _add_style(destination, "9", "Something else")
    master = _master_naming(destination, "20")
    destination._settle_master_styles(source, master)
    names = _names(destination)
    new_inner = next(i for i, n in names.items() if n == "Inner")
    assert new_inner != "9" and names["9"] == "Something else"
    outer = next(s for s in destination._style_sheets() if s.attrib["ID"] == "20")
    assert outer.attrib["LineStyle"] == new_inner


def test_styles_that_are_based_on_each_other_are_settled_once_and_the_call_ends():
    source, destination = Document.new(), Document.new()
    _add_style(source, "20", "Ping", based_on="21")
    _add_style(source, "21", "Pong", based_on="20")
    destination._settle_master_styles(source, _master_naming(destination, "20"))
    assert sorted(n for n in _names(destination).values() if n in ("Ping", "Pong")) == ["Ping", "Pong"]


def test_a_second_master_naming_the_same_style_reuses_what_the_first_settled():
    """The one master is made to name the source's 30 again, as a second imported master would."""
    source, destination = Document.new(), Document.new()
    _add_style(source, "30", "Flow Normal")
    _add_style(destination, "30", "Another style")
    master = _master_naming(destination, "30")
    destination._settle_master_styles(source, master)
    settled, count = _line_styles(master), len(destination._style_sheets())
    assert settled != {"30"}
    _master_naming(destination, "30")
    destination._settle_master_styles(source, master)
    assert len(destination._style_sheets()) == count
    assert _line_styles(master) == settled


SOURCE = str(Path(__file__).parent / "test_master_multiple_child_shapes.vsdx")
"""A document whose master takes style 7, "Default Svg Style", where a blank document's 7 is "Connector"."""


def _copied_master_styles(destination: Document) -> set[str | None]:
    """The names of the styles the copied master's shapes take, as `destination` resolves their IDs."""
    source = Document.open(SOURCE)
    shape = next(iter(source.pages[0].shapes))
    copy = shape.copy(destination.pages[0])
    master = destination._masters.by_id(copy.xml.attrib["Master"])
    names = _names(destination)
    return {
        names.get(s.attrib["LineStyle"]) for s in master.xml.getroot().iter(f"{namespace}Shape") if "LineStyle" in s.attrib
    }


def test_a_copied_masters_styles_follow_it_where_the_destination_means_another_style_by_the_id():
    assert _copied_master_styles(Document.new()) == {"Normal", "Default Svg Style"}


def test_a_copied_masters_styles_follow_it_where_the_destination_lacks_the_id():
    destination = Document.new()
    sheets = destination._style_sheets()
    for sheet in list(sheets):
        if sheet.attrib.get("ID") == "7":
            sheets.remove(sheet)
    assert _copied_master_styles(destination) == {"Normal", "Default Svg Style"}
    assert _names(destination)["7"] == "Default Svg Style"


def test_fill_and_text_style_references_are_settled_as_line_style_ones_are():
    source, destination = Document.new(), Document.new()
    _add_style(source, "20", "Filler")
    _add_style(source, "21", "Texter")
    _add_style(destination, "20", "Something else")
    master = destination._masters.pages[0]
    for shape in master.xml.getroot().iter(f"{namespace}Shape"):
        shape.attrib["FillStyle"], shape.attrib["TextStyle"] = "20", "21"
    destination._settle_master_styles(source, master)
    names = _names(destination)
    shape = next(master.xml.getroot().iter(f"{namespace}Shape"))
    assert names[shape.attrib["FillStyle"]] == "Filler" and shape.attrib["FillStyle"] != "20"
    assert names[shape.attrib["TextStyle"]] == "Texter"


def _add_raw_style(document: Document, **attributes: str) -> None:
    document._style_sheets().append(Document.new()._style_sheets().makeelement(f"{namespace}StyleSheet", attributes))


def _settle_one(source_attributes: dict[str, str], destination_attributes: dict[str, str]) -> tuple[Document, Master]:
    source, destination = Document.new(), Document.new()
    _add_raw_style(source, ID="30", **source_attributes)
    _add_raw_style(destination, ID="30", **destination_attributes)
    master = _master_naming(destination, "30")
    destination._settle_master_styles(source, master)
    return destination, master


def test_styles_without_a_nameu_and_with_different_names_are_not_taken_to_be_the_same():
    destination, master = _settle_one({"Name": "Mine"}, {"Name": "Yours"})
    assert _line_styles(master) != {"30"}
    assert "Mine" in {s.attrib.get("Name") for s in destination._style_sheets()}


def test_styles_without_a_nameu_and_with_the_same_name_are_taken_to_be_the_same():
    destination, master = _settle_one({"Name": "Same"}, {"Name": "Same"})
    assert _line_styles(master) == {"30"}
    assert sum(s.attrib.get("Name") == "Same" for s in destination._style_sheets()) == 1


def test_styles_with_the_same_nameu_are_taken_to_be_the_same_whatever_their_names():
    _, master = _settle_one({"NameU": "Same", "Name": "A"}, {"NameU": "Same", "Name": "B"})
    assert _line_styles(master) == {"30"}


def test_styles_with_different_nameu_are_not_the_same_even_where_the_names_match():
    _, master = _settle_one({"NameU": "A", "Name": "Same"}, {"NameU": "B", "Name": "Same"})
    assert _line_styles(master) != {"30"}


def test_the_page_sheet_of_an_imported_master_is_settled_too():
    source, destination = Document.new(), Document.new()
    _add_style(source, "30", "Mine")
    _add_style(destination, "30", "Yours")
    master = destination._masters.pages[0]
    master._pagesheet_xml.attrib.update(LineStyle="30", FillStyle="30", TextStyle="30")
    destination._settle_master_styles(source, master)
    names = _names(destination)
    assert {names[master._pagesheet_xml.attrib[a]] for a in ("LineStyle", "FillStyle", "TextStyle")} == {"Mine"}


def test_a_drawing_page_sharing_the_masters_id_keeps_its_page_sheet_and_the_masters_is_settled():
    source, destination = Document.new(), Document.new()
    _add_style(source, "30", "Mine")
    _add_style(destination, "30", "Yours")
    master = destination._masters.pages[0]
    pages_root = destination._part_root(destination._pages_xml, "pages.xml")
    page = ET.SubElement(pages_root, f"{namespace}Page", {"ID": master._page_id})
    ET.SubElement(page, f"{namespace}PageSheet", {"LineStyle": "30"})
    destination._settle_master_styles(source, master)
    master_sheet = destination._masters.element_by_id(master._page_id).find(f"{namespace}PageSheet")
    master_sheet.attrib["LineStyle"] = "30"
    destination._settle_master_styles(source, master)
    assert page.find(f"{namespace}PageSheet").attrib["LineStyle"] == "30"
    assert _names(destination)[master_sheet.attrib["LineStyle"]] == "Mine"


def test_a_destination_without_style_sheets_gets_them_between_face_names_and_the_document_sheet():
    source, destination = Document.new(), Document.new()
    _add_style(source, "20", "Mine")
    root = destination._part_root(destination._document_xml, "document.xml")
    root.remove(root.find(f"{namespace}StyleSheets"))
    destination._settle_master_styles(source, _master_naming(destination, "20"))
    tags = [child.tag.removeprefix(namespace) for child in root]
    assert tags.index("FaceNames") < tags.index("StyleSheets") < tags.index("DocumentSheet")
    assert _names(destination)["20"] == "Mine"


def test_a_settle_that_fails_midway_leaves_the_document_and_the_memo_as_they_were(monkeypatch):
    source, destination = Document.new(), Document.new()
    _add_style(source, "20", "Outer", based_on="21")
    _add_style(source, "21", "Inner")
    master = _master_naming(destination, "20")
    before = ET.tostring(destination._part_root(destination._document_xml, "document.xml"))
    original = source._get_style_by_id

    def fail_on_the_second(style_id: str):
        if style_id == "21":
            raise RuntimeError("source went away")
        return original(style_id)

    monkeypatch.setattr(source, "_get_style_by_id", fail_on_the_second)
    with pytest.raises(RuntimeError):
        destination._settle_master_styles(source, master)
    assert ET.tostring(destination._part_root(destination._document_xml, "document.xml")) == before
    assert not destination._style_maps.get(source)


def test_a_copy_whose_styles_cannot_be_settled_leaves_every_part_of_the_package_as_it_was(monkeypatch):
    source, destination = Document.open(SOURCE), Document.new()
    before = {name: destination._package.read_bytes(name) for name in destination._package.names()}
    masters = [m._page_id for m in destination._masters.pages]

    def fail(style_id: str):
        raise RuntimeError("source went away")

    monkeypatch.setattr(source, "_get_style_by_id", fail)
    with pytest.raises(RuntimeError):
        next(iter(source.pages[0].shapes)).copy(destination.pages[0])
    assert {name: destination._package.read_bytes(name) for name in destination._package.names()} == before
    assert not destination._style_maps.get(source)
    assert [m._page_id for m in destination._masters.pages] == masters
