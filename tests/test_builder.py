"""The declarative builder: the graph contract, the validation, and what lands in the document."""

import dataclasses
import hashlib
import os
import random
import subprocess
import sys
import zipfile
from itertools import pairwise
from pathlib import Path
from xml.etree.ElementTree import Element

import pytest
from helpers.graphs import random_graph

from vsdxkit import namespace
from vsdxkit.builder import Diagram, Edge, Group, Lane, Node, Page
from vsdxkit.document import Document
from vsdxkit.errors import GraphError
from vsdxkit.shapes import Shape
from vsdxkit.swimlanes import ROW_HEADING_TEXT

HERE = Path(__file__).resolve().parent
NODE_KINDS = ["start", "end", "process", "decision", "data_store", "external", "document", "subprocess", "off_page"]


def _fields(cls: type) -> list[str]:
    return [f.name for f in dataclasses.fields(cls)]


def test_the_graph_contract_is_the_one_the_spec_states():
    """Fails if a field the docs generator builds against is renamed, reordered or dropped."""
    assert _fields(Diagram) == ["title", "pages"]
    assert _fields(Page) == ["name", "nodes", "edges", "groups", "lanes"]
    assert _fields(Node) == ["id", "kind", "label", "sublabel", "data"]
    assert _fields(Edge) == ["source", "target", "label", "kind"]
    assert _fields(Group) == ["id", "label", "node_ids", "groups"]
    assert _fields(Lane) == ["id", "label", "node_ids"]


def _rows(shape: Shape) -> dict[str, str]:
    return {name: prop.value or "" for name, prop in ((p.name or "", p) for p in shape.data_properties.values())}


def _by_source(document: Document, page: int = 0) -> dict[str, Shape]:
    return {
        _rows(s)["Source"]: s
        for s in document.pages[page].shapes
        if "Source" in _rows(s) and _rows(s).get("Kind") != "edge_label"
    }


def test_a_node_becomes_a_labelled_shape_with_its_data_rows(tmp_path):
    node = Node("a", "process", "Check", sublabel="twice", data={"Zeta": "z", "Alpha": "a"})
    document = Diagram("T", [Page("Main", [node])]).build()
    shape = _by_source(document)["a"]
    assert shape.text.rstrip("\n") == "Check\ntwice"
    rows = _rows(shape)
    assert list(rows) == ["Source", "Kind", "Alpha", "Zeta"]
    assert rows == {"Source": "a", "Kind": "process", "Alpha": "a", "Zeta": "z"}


def test_a_source_entry_in_data_replaces_the_default():
    document = Diagram("T", [Page("Main", [Node("a", "process", "x", data={"Source": "stage 2"})])]).build()
    assert list(_by_source(document)) == ["stage 2"]


@pytest.mark.parametrize("kind", NODE_KINDS)
def test_every_node_kind_builds_and_survives_a_save(kind, tmp_path):
    path = Diagram("T", [Page("Main", [Node("a", kind, "x")])]).save(tmp_path / "a.vsdx")
    assert _rows(next(iter(Document.open(path).pages[0].shapes)))["Kind"] == kind


def test_shape_ids_follow_input_order_within_each_kind_of_shape():
    nodes = [Node(f"n{i}", "process", f"S{i}") for i in range(5)]
    edges = [Edge("n0", "n1"), Edge("n1", "n2")]
    document = Diagram("T", [Page("Main", nodes, edges)]).build()
    ids = [int(s.ID) for s in document.pages[0].shapes]
    assert ids == sorted(ids)
    order = [_rows(s)["Source"] for s in document.pages[0].shapes]
    assert order == ["n0", "n1", "n2", "n3", "n4", "n0->n1", "n1->n2"]


def test_an_edge_is_an_open_polyline_with_an_arrowhead_and_a_label_shape():
    page = Page("Main", [Node("a", "process", "A"), Node("b", "process", "B")], [Edge("a", "b", "go", "no-path")])
    document = Diagram("T", [page]).build()
    shapes = _by_source(document)
    path = shapes["a->b"]
    assert path.end_arrow == "13"
    assert path.cell_value("LinePattern") == "2"
    assert _rows(path)["Kind"] == "no-path"
    rows = [r for r in path.xml.iter(f"{namespace}Row") if r.attrib.get("T") in ("MoveTo", "LineTo")]
    assert rows[0].attrib["T"] == "MoveTo" and len(rows) >= 2
    assert [s for s in document.pages[0].shapes if s.text == "go"], "the label has its own shape"


def test_lanes_and_groups_are_drawn_behind_the_nodes():
    nodes = [Node("a", "process", "A"), Node("b", "process", "B")]
    page = Page("Main", nodes, [Edge("a", "b")], [Group("g", "Stage", ["a", "b"])], [Lane("l", "Role", ["a", "b"])])
    document = Diagram("T", [page]).build()
    kinds = [_rows(s).get("Kind") for s in document.pages[0].shapes if "Kind" in _rows(s)]
    assert kinds.index("group") < kinds.index("process")
    assert all(kinds.index(k) < kinds.index("group") for k in ("lane_container", "lane"))
    assert document.pages[0].swimlanes is not None


def test_the_title_and_the_page_names_are_written():
    document = Diagram("My title", [Page("One", [Node("a", "start", "S")]), Page("Two", [Node("b", "end", "E")])]).build()
    assert [p.name for p in document.pages] == ["One", "Two"]
    core = document._package.read_xml("/docProps/core.xml")
    assert core is not None and core.getroot().find("{http://purl.org/dc/elements/1.1/}title").text == "My title"


def test_a_page_link_writes_the_page_and_node_it_leads_to_on_both_ends():
    one = Page("One", [Node("out", "off_page", "To two")], [Edge("out", "in", kind="page-link")])
    two = Page("Two", [Node("in", "off_page", "From one")])
    document = Diagram("T", [one, two]).build()
    assert _rows(_by_source(document, 0)["out"])["Linked page"] == "Two"
    assert _rows(_by_source(document, 1)["in"])["Linked node"] == "out"
    assert not [s for s in document.pages[0].shapes if _rows(s).get("Kind") == "page-link"], "a page-link draws no connector"


def _node(id_: str, kind: str = "process") -> Node:
    return Node(id_, kind, id_)


@pytest.mark.parametrize(
    ("pages", "message"),
    [
        ([], "at least one page"),
        ([Page("P", [_node("a")]), Page("P", [_node("b")])], "page names must be unique"),
        ([Page("P", [_node("a"), _node("a")])], "used twice"),
        ([Page("P", [_node("")])], "something in it"),
        ([Page("P", [_node("  ")])], "something in it"),
        ([Page("P", [Node(7, "process", "x")])], "something in it"),  # type: ignore[arg-type]
        ([Page("", [_node("a")])], "needs a name"),
        ([Page("P", [_node("a")]), Page("Q", [_node("a")])], "used twice"),
        ([Page("P", [Node("a", "blob", "x")])], "has kind 'blob'"),  # type: ignore[arg-type]
        ([Page("P", [_node("a")], [Edge("a", "zz")])], "is not a node on page"),
        ([Page("P", [_node("a")], [Edge("a", "a", kind="loud")])], "has kind 'loud'"),  # type: ignore[arg-type]
        ([Page("P", [_node("a")], lanes=[Lane("l", "L", ["a"]), Lane("m", "M", ["a"])])], "is in lanes"),
        ([Page("P", [_node("a"), _node("b")], lanes=[Lane("l", "L", ["a"])])], "must be in one"),
        ([Page("P", [_node("a")], groups=[Group("g", "G", ["a"]), Group("h", "H", ["a"])])], "is in groups"),
        (
            [Page("P", [_node("a")], groups=[Group("g", "G", ["a"], [Group("h", "H", [], [Group("i", "I", [])])])])],
            "nest one level",
        ),
        (
            [
                Page(
                    "P",
                    [_node("a"), _node("b")],
                    groups=[Group("g", "G", ["a", "b"])],
                    lanes=[Lane("l", "L", ["a"]), Lane("m", "M", ["b"])],
                )
            ],
            "stays in one lane",
        ),
        (
            [Page("P", [_node("a")], groups=[Group("g", "G", ["lane"])], lanes=[Lane("lane", "L", ["a"])])],
            "not a node on page",
        ),
        ([Page("P", [Node("a", "process", 5)])], "must be a string"),  # type: ignore[arg-type]
        ([Page("P", [Node("a", "process", "x", sublabel=5)])], "must be a string"),  # type: ignore[arg-type]
        ([Page("P", [_node("a")], [Edge("a", ["a"])])], "ids are strings"),  # type: ignore[arg-type]
        ([Page("P", [_node("a")], [Edge("a", "a", label=3)])], "must be a string"),  # type: ignore[arg-type]
        ([Page("P", [_node("a")], lanes=[Lane("l", "L", [["a"]])])], "ids are strings"),  # type: ignore[list-item]
        (
            [
                Page("P", [_node("o", "off_page")], [Edge("o", "x", kind="page-link"), Edge("o", "y", kind="page-link")]),
                Page("Q", [_node("x", "off_page"), _node("y", "off_page")]),
            ],
            "more than one page-link",
        ),
        ([Page("P", [_node("a", "off_page")], [Edge("a", "a", kind="page-link")])], "must join an off_page node"),
        (
            [Page("P", [_node("a")], [Edge("a", "b", kind="page-link")]), Page("Q", [_node("b", "off_page")])],
            "must join an off_page node",
        ),
    ],
)
def test_a_description_that_cannot_be_drawn_is_refused_before_anything_is_built(pages, message):
    with pytest.raises(GraphError, match=message):
        Diagram("T", pages).build()


AWKWARD_TEXT = [
    "R&D <review> \"quoted\" 'single'",
    "two\nlines",
    "caf\u00e9 \u65e5\u672c\u8a9e \U0001f600",
    "  padded  ",
    "x" * 400,
]


@pytest.mark.parametrize("text", AWKWARD_TEXT)
def test_awkward_label_text_is_written_escaped_and_reads_back_unchanged(text, tmp_path):
    """Markup characters, newlines, non-ASCII text and a very long label must not corrupt the XML."""
    path = Diagram("T", [Page("Main", [Node("a", "process", text, data={"Note": text})])]).save(tmp_path / "t.vsdx")
    shape = _by_source(Document.open(path))["a"]
    assert shape.text.rstrip("\n") == text
    assert _rows(shape)["Note"] == text


@pytest.mark.parametrize("text", AWKWARD_TEXT[:4])
def test_awkward_text_in_every_other_place_reads_back_unchanged(text, tmp_path):
    """A sublabel, an edge label, a group label, a lane label and a page name take the same text."""
    nodes = [Node("a", "process", "A", sublabel=text), Node("b", "process", "B")]
    page = Page("P" + text, nodes, [Edge("a", "b", text)], [Group("g", text, ["a"])], [Lane("l", text, ["a", "b"])])
    document = Document.open(Diagram(text, [page]).save(tmp_path / "t.vsdx"))
    assert document.pages[0].name == "P" + text
    shapes = list(document.pages[0].shapes)
    assert _by_source(document)["a"].text.rstrip("\n") == f"A\n{text}"
    assert next(s for s in shapes if _rows(s).get("Kind") == "edge_label").text.rstrip("\n") == text
    assert next(s for s in shapes if _rows(s).get("Kind") == "group").text.rstrip("\n") == text
    lane = document.pages[0].require_swimlanes().lanes[0]
    row = next(r for r in lane.xml.iter(f"{namespace}Row") if r.attrib.get("N") == ROW_HEADING_TEXT)
    assert next(c.attrib["V"] for c in row if c.attrib.get("N") == "Value") == text


@pytest.mark.parametrize(
    "edges",
    [
        [Edge("a", "a")],
        [Edge("a", "b"), Edge("b", "c"), Edge("c", "a")],
        [Edge("a", "b"), Edge("a", "b", "again"), Edge("a", "b", kind="data")],
    ],
    ids=["self-loop", "cycle", "parallel"],
)
def test_loops_cycles_and_parallel_edges_build_save_and_reopen(edges, tmp_path):
    nodes = [_node("a"), _node("b"), _node("c")]
    document = Document.open(Diagram("T", [Page("P", nodes, edges)]).save(tmp_path / "c.vsdx"))
    paths = [s for s in document.pages[0].shapes if _rows(s).get("Source", "").count("->")]
    assert len([s for s in paths if _rows(s)["Kind"] != "edge_label"]) == len(edges)


def test_a_page_with_no_nodes_a_lane_with_no_nodes_and_a_group_with_no_nodes_all_build(tmp_path):
    empty = Page("Empty", [])
    spare = Page("Spare", [Node("a", "start", "A")], lanes=[Lane("l1", "Used", ["a"]), Lane("l2", "Spare", [])])
    path = Diagram("T", [empty, spare]).save(tmp_path / "e.vsdx")
    document = Document.open(path)
    assert [p.name for p in document.pages] == ["Empty", "Spare"]
    assert {_rows(s).get("Source") for s in document.pages[1].shapes} >= {"a", "l1", "l2"}


def test_every_node_sits_inside_the_lane_it_was_given(tmp_path):
    """A lane assignment that read as the wrong system would mislead (spec 12.2, item 2)."""
    members = (["n0", "n3"], ["n1", "n4"], ["n2", "n5"])
    nodes = [Node(f"n{i}", "process", f"N{i}") for i in range(6)]
    edges = [Edge(f"n{i}", f"n{i + 1}") for i in range(5)]
    lanes = [Lane(name, name.upper(), ids) for name, ids in zip("abc", members, strict=True)]
    document = Document.open(Diagram("T", [Page("P", nodes, edges, lanes=lanes)]).save(tmp_path / "l.vsdx"))
    diagram = document.pages[0].require_swimlanes()
    by_source = _by_source(document)
    for lane, ids in zip(diagram.lanes, members, strict=True):
        for node_id in ids:
            assert diagram.lane_for(by_source[node_id]).ID == lane.ID, node_id


def test_one_node_alone_on_a_page_builds(tmp_path):
    path = Diagram("T", [Page("One", [Node("only", "end", "Done")])]).save(tmp_path / "o.vsdx")
    assert len(Document.open(path).pages[0].shapes) == 1


def _bytes(diagram: Diagram, tmp_path: Path, name: str) -> bytes:
    return diagram.save(tmp_path / name).read_bytes()


def test_equal_diagrams_save_equal_bytes_whatever_the_order_the_data_was_inserted_in(tmp_path):
    items = [("k1", "1"), ("k2", "2"), ("k3", "3")]
    shuffled = random.Random(4).sample(items, 3)
    a = Diagram("T", [Page("P", [Node("a", "process", "A", data=dict(items))])])
    b = Diagram("T", [Page("P", [Node("a", "process", "A", data=dict(shuffled))])])
    assert _bytes(a, tmp_path, "a.vsdx") == _bytes(b, tmp_path, "b.vsdx")


def _big(n: int, m: int, lanes: int = 0) -> Diagram:
    rows, edges, lane_ids, _g, _p = random_graph(11, n, m, lanes, 0)
    built = [Node(row[0], NODE_KINDS[i % len(NODE_KINDS)], f"Step {i}") for i, row in enumerate(rows)]
    lane_objs = [Lane(name, name, [row[0] for row in rows if row[3] == name]) for name in lane_ids]
    return Diagram("Big", [Page("P", built, [Edge(s, t) for s, t in edges], lanes=lane_objs)])


def _laned() -> Diagram:
    """A page with lanes small enough to be drawn: a diagram with lanes is at most 22 inches wide."""
    rows, edges, lane_ids, _g, _p = random_graph(5, 8, 10, 3, 0)
    built = [Node(row[0], NODE_KINDS[i % len(NODE_KINDS)], f"Step {i}") for i, row in enumerate(rows)]
    lanes = [Lane(name, name, [row[0] for row in rows if row[3] == name]) for name in lane_ids]
    return Diagram("Laned", [Page("P", built, [Edge(s, t) for s, t in edges], lanes=lanes)])


def _fixed_bytes(tmp_path: Path, name: str) -> bytes:
    """The bytes of the digest's diagrams, one without lanes and one with."""
    return _bytes(_big(30, 45), tmp_path, name + "a.vsdx") + _bytes(_laned(), tmp_path, name + "b.vsdx")


def test_the_bytes_do_not_depend_on_the_hash_seed(tmp_path):
    code = (
        "import hashlib, sys\n"
        "from pathlib import Path\n"
        "from test_builder import _fixed_bytes\n"
        "print(hashlib.sha256(_fixed_bytes(Path(sys.argv[1]), 'x')).hexdigest())\n"
    )
    paths = os.pathsep.join([str(HERE), str(HERE.parent / "src")])
    digests = {
        subprocess.run(
            [sys.executable, "-c", code, str(tmp_path)],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": paths},
            check=True,
        ).stdout
        for seed in ("0", "1", "2", "random")
    }
    assert len(digests) == 1


def test_a_50_node_process_builds_in_one_call_with_no_coordinates(tmp_path):
    """The #52 exit criterion. Lanes are limited to 22 inches wide, so the 50 nodes are drawn without them."""
    document = Document.open(_big(50, 70).save(tmp_path / "fifty.vsdx"))
    nodes = [s for s in document.pages[0].shapes if _rows(s).get("Kind") in NODE_KINDS]
    assert len(nodes) == 50


def test_a_laned_page_builds_within_the_swimlane_limits(tmp_path):
    document = Document.open(_laned().save(tmp_path / "laned.vsdx"))
    assert len(document.pages[0].require_swimlanes().lanes) == 3


def test_a_page_the_swimlane_drawing_cannot_hold_is_refused_before_a_file_exists(tmp_path):
    too_many = Page("P", [_node(f"n{i}") for i in range(6)], lanes=[Lane(f"l{i}", f"L{i}", [f"n{i}"]) for i in range(6)])
    wide = _big(30, 45, lanes=3)
    long_label = Page("P", [_node("a")], lanes=[Lane("l", "x" * 40, ["a"])])
    empty_label = Page("P", [_node("a")], lanes=[Lane("l", " ", ["a"])])
    for page, message in (
        (too_many, "at most 5"),
        (wide.pages[0], "inches wide"),
        (long_label, "label"),
        (empty_label, "label"),
    ):
        target = tmp_path / "never.vsdx"
        with pytest.raises(GraphError, match=message):
            Diagram("T", [page]).save(target)
        assert not target.exists()


def _absolute_points(shape: Shape) -> list[tuple[float, float]]:
    left = (shape.x or 0.0) - (shape.width or 0.0) / 2
    bottom = (shape.y or 0.0) - (shape.height or 0.0) / 2
    points = []
    for row in shape.xml.iter(f"{namespace}Row"):
        if row.attrib.get("T") in ("MoveTo", "LineTo"):
            cells: dict[str, Element] = {c.attrib["N"]: c for c in row.findall(f"{namespace}Cell")}
            points.append((left + float(cells["X"].attrib["V"]), bottom + float(cells["Y"].attrib["V"])))
    return points


def test_in_a_200_node_page_no_connector_runs_through_a_node(tmp_path):
    """The #53 exit criterion, read back from the written file rather than from the layout."""
    document = Document.open(_big(200, 300).save(tmp_path / "two_hundred.vsdx"))
    shapes = list(document.pages[0].shapes)
    nodes = {_rows(s)["Source"]: s for s in shapes if _rows(s).get("Kind") in NODE_KINDS}
    shrink = 1e-6
    for path in (s for s in shapes if _rows(s).get("Kind") == "flow"):
        source, target = _rows(path)["Source"].split("->")
        for p, q in pairwise(_absolute_points(path)):
            for node_id, node in nodes.items():
                if node_id in (source, target):
                    continue
                left, right = node.x - node.width / 2 + shrink, node.x + node.width / 2 - shrink
                bottom, top = node.y - node.height / 2 + shrink, node.y + node.height / 2 - shrink
                inside = max(min(p[0], q[0]), left) <= min(max(p[0], q[0]), right) and max(min(p[1], q[1]), bottom) <= min(
                    max(p[1], q[1]), top
                )
                assert not inside, f"{source}->{target} runs through {node_id}"


def test_a_saved_diagram_is_a_valid_zip_with_the_fixed_member_form(tmp_path):
    path = _big(10, 12).save(tmp_path / "d.vsdx")
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert {i.date_time for i in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}


GOLDEN = HERE / "fixtures" / "builder_bytes.sha256"
"""The digest of a fixed diagram, read by every platform in the CI matrix (spec section 4.11)."""


def test_the_bytes_equal_the_digest_every_platform_is_held_to(tmp_path):
    """Linux, Windows and macOS each build the same diagram and compare with the one committed digest."""
    digest = hashlib.sha256(_fixed_bytes(tmp_path, "d")).hexdigest()
    assert digest == GOLDEN.read_text(encoding="utf-8").strip()
