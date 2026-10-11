"""The style IDs a master imported from another document names are settled in the destination."""

from pathlib import Path

from vsdxkit import namespace
from vsdxkit.document import Document


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
