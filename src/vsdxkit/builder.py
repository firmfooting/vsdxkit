"""Describe a diagram as data, and compile it to a Visio document with no coordinates supplied.

A :class:`Diagram` is pages of :class:`Node`, :class:`Edge`, :class:`Group` and :class:`Lane`
values, each named by an id the caller chooses. :meth:`Diagram.build` lays the pages out
(see :mod:`vsdxkit.layout`) and draws them. The same description gives the same document, and
:meth:`Diagram.save` writes it as the same bytes on every platform.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import pairwise
from pathlib import Path
from typing import Literal, get_args

from vsdxkit._drawing import DEFAULT_SIZE, add_data_rows, draw_backdrop, draw_label, draw_node, draw_path
from vsdxkit.document import Document
from vsdxkit.errors import GraphError
from vsdxkit.layout import Layout, LayoutNode, LayoutOptions, layered_layout, snap
from vsdxkit.pages import Page as VisioPage
from vsdxkit.swimlanes import DIAGRAM_WIDTHS, LABEL_CHARS_PER_INCH, LANE_HEIGHTS, MAX_LANES

NodeKind = Literal["start", "end", "process", "decision", "data_store", "external", "document", "subprocess", "off_page"]
"""What a node looks like."""
EdgeKind = Literal["flow", "yes-path", "no-path", "data", "call", "page-link"]
"""What an edge means. ``page-link`` joins two ``off_page`` nodes on different pages and draws no connector."""

_DASHED_EDGES = frozenset({"no-path", "data", "call"})
"""The edge kinds drawn dashed; the others are solid."""
_LANE_LEFT = 0.25
"""Inches between the page's left edge and a lane diagram, which also leaves the same on the right."""
_LANE_MARGIN = 0.7
"""The least margin on a page with lanes: the diagram's title bar sits above its first lane and must stay on the page."""
_CORE_PART = "/docProps/core.xml"
"""The part holding the document's title."""
_DC_TITLE = "{http://purl.org/dc/elements/1.1/}title"
"""The title element of the core properties."""


@dataclass(frozen=True)
class Node:
    """One box."""

    id: str
    """The caller's id, unique across the whole diagram."""
    kind: NodeKind
    """What the box looks like."""
    label: str
    """The text in the box."""
    sublabel: str | None = None
    """A second line of text, or None."""
    data: Mapping[str, str] = field(default_factory=dict)
    """Shape Data rows, written after the ``Source`` and ``Kind`` rows, sorted by name. A ``Source`` entry replaces the default, the id."""


@dataclass(frozen=True)
class Edge:
    """An arrow from one node to another on the same page."""

    source: str
    """The id of the node it leaves."""
    target: str
    """The id of the node it enters."""
    label: str | None = None
    """Text beside the arrow, or None."""
    kind: EdgeKind = "flow"
    """What the arrow means."""


@dataclass(frozen=True)
class Group:
    """A labelled box round some nodes."""

    id: str
    """The caller's id, unique across the whole diagram."""
    label: str
    """The text at the top of the box."""
    node_ids: Sequence[str]
    """The nodes directly in the group."""
    groups: Sequence[Group] = ()
    """Groups inside this one. They nest one level, and their nodes are not repeated in ``node_ids``."""

    def __post_init__(self) -> None:
        """Hold the members as tuples, so a group compares by value."""
        object.__setattr__(self, "node_ids", tuple(self.node_ids))
        object.__setattr__(self, "groups", tuple(self.groups))


@dataclass(frozen=True)
class Lane:
    """A horizontal band, labelled at its left, that holds nodes."""

    id: str
    """The caller's id, unique across the whole diagram."""
    label: str
    """The lane's heading."""
    node_ids: Sequence[str]
    """The nodes in the lane. When a page has lanes, every node is in one."""

    def __post_init__(self) -> None:
        """Hold the members as a tuple, so a lane compares by value."""
        object.__setattr__(self, "node_ids", tuple(self.node_ids))


@dataclass(frozen=True)
class Page:
    """One Visio page."""

    name: str
    """The page's name, unique in the diagram."""
    nodes: Sequence[Node]
    """The boxes, in the order they are created."""
    edges: Sequence[Edge] = ()
    """The arrows, in the order they are created."""
    groups: Sequence[Group] = ()
    """The group boxes."""
    lanes: Sequence[Lane] = ()
    """The lanes, top to bottom."""

    def __post_init__(self) -> None:
        """Hold the members as tuples, so a page compares by value."""
        for name in ("nodes", "edges", "groups", "lanes"):
            object.__setattr__(self, name, tuple(getattr(self, name)))


@dataclass(frozen=True)
class Diagram:
    """A titled document of pages. Every id is unique across all of them."""

    title: str
    """The document's title property."""
    pages: Sequence[Page]
    """The pages, in order."""

    def __post_init__(self) -> None:
        """Hold the pages as a tuple, so a diagram compares by value."""
        object.__setattr__(self, "pages", tuple(self.pages))

    def validate(self) -> None:
        """Refuse a description that cannot be drawn, naming the first thing wrong.

        :raises GraphError: on a repeated, empty or non-string id or page name, an edge or member naming a node
            not on its page, a node in two lanes or two groups, a node outside every lane on a page with lanes,
            a group split across lanes or nested two deep, more lanes than a page draws, a blank lane label, an
            unknown kind, a label or sublabel that is not a string, an edge end that is not a string, an ``off_page``
            node that ends two ``page-link`` edges, or a ``page-link`` that does not join an ``off_page`` node on its
            own page to one on another. Whether a laned page fits is known only after layout, so :meth:`build` checks it.
        """
        if not self.pages:
            raise GraphError("a diagram needs at least one page")
        names = [p.name for p in self.pages]
        if not all(isinstance(n, str) and n.strip() for n in names):
            raise GraphError("every page needs a name with something in it")
        if len(set(names)) != len(names):
            raise GraphError(f"page names must be unique, and {sorted({n for n in names if names.count(n) > 1})} are not")
        where: dict[str, tuple[str, str]] = {}
        for page in self.pages:
            _register(page, where)
        for page in self.pages:
            _check_lanes(page)
            _check_membership(page, where)
            _check_edges(page, where)
        _links(self)

    def build(self, *, layout: LayoutOptions | None = None) -> Document:
        """Compile to a new document with one page per :class:`Page`, creating shapes in input order.

        :param layout: spacing and flow direction; the defaults flow left to right
        :raises GraphError: as :meth:`validate`, and when a laid-out page with lanes is wider than 60 inches of diagram,
            a lane is more than 6 inches tall, a lane label is longer than 11 characters for each inch of its lane, or
            the layout refuses the graph
        """
        self.validate()
        options = layout if layout is not None else LayoutOptions()
        document = Document.new(page_name=self.pages[0].name)
        _set_title(document, self.title)
        links = _links(self)
        for n, page in enumerate(self.pages):
            _draw_page(page, document.pages[0] if n == 0 else document.pages.create(page.name), options, links)
        return document

    def save(self, target: str | os.PathLike[str], *, layout: LayoutOptions | None = None) -> Path:
        """Build and write the document with a deterministic save: equal diagrams give equal bytes.

        :raises GraphError: as :meth:`validate`
        """
        return self.build(layout=layout).save(target, deterministic=True)


def _register(page: Page, where: dict[str, tuple[str, str]]) -> None:
    """Record every id on `page` as (page name, kind), refusing a repeat or an unknown kind."""
    for node in page.nodes:
        if node.kind not in get_args(NodeKind):
            raise GraphError(f"node {node.id!r} has kind {node.kind!r}; the kinds are {sorted(get_args(NodeKind))}")
        _claim(where, node.id, page.name, node.kind)
        for field_name in ("label", "sublabel"):
            value = getattr(node, field_name)
            if not isinstance(value, str) and not (field_name == "sublabel" and value is None):
                raise GraphError(f"node {node.id!r} has a {field_name} that is {value!r}; it must be a string")
    for lane in page.lanes:
        _claim(where, lane.id, page.name, "lane")
    for group in _all_groups(page):
        _claim(where, group.id, page.name, "group")


def _claim(where: dict[str, tuple[str, str]], id_: str, page: str, kind: str) -> None:
    """Record `id_` as belonging to `page`, or refuse it as used twice."""
    if not isinstance(id_, str) or not id_.strip():
        raise GraphError(f"id {id_!r} must be a string with something in it")
    if id_ in where:
        raise GraphError(f"id {id_!r} is used twice")
    where[id_] = (page, kind)


def _check_membership(page: Page, where: Mapping[str, tuple[str, str]]) -> None:
    """Refuse lane and group membership that names a stranger, repeats a node, or splits a group across lanes."""
    lane_of: dict[str, str] = {}
    for lane in page.lanes:
        for node_id in lane.node_ids:
            _on_page(page, node_id, where, f"lane {lane.id!r}")
            if node_id in lane_of:
                raise GraphError(f"node {node_id!r} is in lanes {lane_of[node_id]!r} and {lane.id!r}")
            lane_of[node_id] = lane.id
    if page.lanes:
        for node in page.nodes:
            if node.id not in lane_of:
                raise GraphError(f"page {page.name!r} has lanes, so node {node.id!r} must be in one")
    group_of: dict[str, str] = {}
    for group in page.groups:
        direct = {i: group.id for i in group.node_ids}
        for child in group.groups:
            if child.groups:
                raise GraphError(f"group {child.id!r} nests inside {group.id!r}; groups nest one level")
            direct.update({i: child.id for i in child.node_ids})
        for node_id, owner in direct.items():
            _on_page(page, node_id, where, f"group {owner!r}")
            if node_id in group_of:
                raise GraphError(f"node {node_id!r} is in groups {group_of[node_id]!r} and {owner!r}")
            group_of[node_id] = owner
        used = {lane_of[i] for i in direct if i in lane_of}
        if len(used) > 1:
            raise GraphError(f"group {group.id!r} holds nodes from lanes {sorted(used)}; a group stays in one lane")


def _check_lanes(page: Page) -> None:
    """Refuse more lanes than the swimlane drawing is verified for."""
    if len(page.lanes) > MAX_LANES:
        raise GraphError(f"page {page.name!r} has {len(page.lanes)} lanes; a page draws at most {MAX_LANES}")
    for lane in page.lanes:
        if not isinstance(lane.label, str) or not lane.label.strip():
            raise GraphError(f"lane {lane.id!r} needs a label with something in it")


def _on_page(page: Page, node_id: str, where: Mapping[str, tuple[str, str]], what: str) -> None:
    """Refuse `node_id` unless it is a node on `page`."""
    if not isinstance(node_id, str):
        raise GraphError(f"{what} lists {node_id!r}; ids are strings")
    if where.get(node_id, ("", ""))[0] != page.name or where[node_id][1] in ("lane", "group"):
        raise GraphError(f"{what} lists {node_id!r}, which is not a node on page {page.name!r}")


def _check_edges(page: Page, where: Mapping[str, tuple[str, str]]) -> None:
    """Refuse an edge of an unknown kind, or whose ends are not where its kind needs them."""
    for edge in page.edges:
        if edge.kind not in get_args(EdgeKind):
            raise GraphError(
                f"edge {edge.source!r} -> {edge.target!r} has kind {edge.kind!r}; the kinds are {sorted(get_args(EdgeKind))}"
            )
        for end in (edge.source, edge.target):
            if not isinstance(end, str):
                raise GraphError(f"an edge on page {page.name!r} has an end {end!r}; ids are strings")
        if edge.label is not None and not isinstance(edge.label, str):
            raise GraphError(
                f"edge {edge.source!r} -> {edge.target!r} has a label that is {edge.label!r}; it must be a string"
            )
        source, target = where.get(edge.source), where.get(edge.target)
        if edge.kind == "page-link":
            if not (
                source == (page.name, "off_page") and target is not None and target[1] == "off_page" and target[0] != page.name
            ):
                raise GraphError(
                    f"page-link {edge.source!r} -> {edge.target!r} must join an off_page node on page {page.name!r} "
                    "to an off_page node on another page"
                )
        else:
            for end, found in ((edge.source, source), (edge.target, target)):
                if found is None or found[0] != page.name or found[1] in ("lane", "group"):
                    raise GraphError(f"edge {edge.source!r} -> {edge.target!r}: {end!r} is not a node on page {page.name!r}")


def _all_groups(page: Page) -> list[Group]:
    """Every group on the page, each parent before its children, in input order."""
    return [g for group in page.groups for g in (group, *group.groups)]


def _links(diagram: Diagram) -> dict[str, dict[str, str]]:
    """The Shape Data rows each ``page-link`` end gets, by node id: the page and the node it leads to."""
    pages = {n.id: p.name for p in diagram.pages for n in p.nodes}
    rows: dict[str, dict[str, str]] = {}
    for page in diagram.pages:
        for edge in page.edges:
            if edge.kind == "page-link":
                for end in (edge.source, edge.target):
                    if end in rows:
                        raise GraphError(f"off_page node {end!r} ends more than one page-link")
                rows[edge.source] = {"Linked page": pages[edge.target], "Linked node": edge.target}
                rows[edge.target] = {"Linked page": page.name, "Linked node": edge.source}
    return rows


def _set_title(document: Document, title: str) -> None:
    """Write the title into the core properties; Document.new always has them, so a missing one is refused."""
    tree = document._package.read_xml(_CORE_PART)
    element = None if tree is None else tree.getroot().find(_DC_TITLE)
    if element is None:
        raise GraphError("the new document has no title property to write")
    element.text = title


def _size(node: Node) -> tuple[float, float]:
    """The node's width and height: its kind's, grown for a long label or extra lines."""
    width, height = DEFAULT_SIZE[node.kind]
    lines = [node.label, *(node.sublabel.split("\n") if node.sublabel else [])]
    return snap(max(width, 0.09 * max(len(line) for line in lines) + 0.5)), snap(max(height, 0.25 * len(lines) + 0.4))


def _rows(node: Node, links: Mapping[str, Mapping[str, str]]) -> dict[str, str]:
    """The Shape Data rows a node is written with: Source and Kind first, then the rest sorted by name."""
    rows = {"Source": node.data.get("Source", node.id), "Kind": node.kind}
    rows.update({k: node.data[k] for k in sorted(node.data) if k not in rows})
    rows.update(links.get(node.id, {}))
    return rows


def _draw_page(page: Page, target: VisioPage, options: LayoutOptions, links: Mapping[str, Mapping[str, str]]) -> None:
    """Lay `page` out and draw it onto `target`: backdrops first, then nodes, then edges, so ids follow input order within each."""
    lane_of = {i: lane.id for lane in page.lanes for i in lane.node_ids}
    group_of: dict[str, str] = {}
    parents: list[tuple[str, str]] = []
    for group in page.groups:
        group_of.update({i: group.id for i in group.node_ids})
        for child in group.groups:
            parents.append((child.id, group.id))
            group_of.update({i: child.id for i in child.node_ids})
    sizes = {n.id: _size(n) for n in page.nodes}
    if page.lanes:
        options = replace(options, margin=max(options.margin, _LANE_MARGIN))
    layout = layered_layout(
        tuple(LayoutNode(n.id, *sizes[n.id], lane_of.get(n.id), group_of.get(n.id)) for n in page.nodes),
        tuple((e.source, e.target) for e in page.edges if e.kind != "page-link"),
        tuple(lane.id for lane in page.lanes),
        tuple(g.id for g in _all_groups(page)),
        replace(options, parents=tuple(parents)),
    )
    if page.lanes:
        low, high = DIAGRAM_WIDTHS
        if layout.width - 2 * _LANE_LEFT > high:
            raise GraphError(
                f"page {page.name!r} lays out {layout.width:.1f} inches wide, and a page with lanes is drawn at most "
                f"{high + 2 * _LANE_LEFT:g}; use fewer layers or nodes"
            )
        layout = replace(layout, width=max(layout.width, low + 2 * _LANE_LEFT))
    target.width = layout.width
    target.height = layout.height
    _draw_layout(page, target, layout, sizes, links)


def _draw_layout(
    page: Page,
    target: VisioPage,
    layout: Layout,
    sizes: Mapping[str, tuple[float, float]],
    links: Mapping[str, Mapping[str, str]],
) -> None:
    """Draw lane bands, group boxes, nodes and edges where `layout` put them."""
    if page.lanes:
        boxes = [layout.lanes[lane.id] for lane in page.lanes]
        for lane, box in zip(page.lanes, boxes, strict=True):
            if not LANE_HEIGHTS[0] <= box.height <= LANE_HEIGHTS[1]:
                raise GraphError(
                    f"lane {lane.id!r} is laid out {box.height:g} inches tall; a lane is drawn {LANE_HEIGHTS[0]} to {LANE_HEIGHTS[1]}"
                )
            if len(lane.label) > LABEL_CHARS_PER_INCH * box.height:
                raise GraphError(
                    f"lane {lane.id!r} has a label of {len(lane.label)} characters, more than its {box.height:g} inch height holds"
                )
        diagram = target.create_swimlanes(
            [(lane.label, box.height) for lane, box in zip(page.lanes, boxes, strict=True)],
            left=_LANE_LEFT,
            top=boxes[0].y + boxes[0].height / 2,
            width=layout.width - 2 * _LANE_LEFT,
        )
        add_data_rows(diagram.container, {"Source": page.name, "Kind": "lane_container"})
        for lane, shape in zip(page.lanes, diagram.lanes, strict=True):
            add_data_rows(shape, {"Source": lane.id, "Kind": "lane"})
        for shape in target.children:
            name = shape.xml.attrib.get("NameU")
            if name in ("Swimlane List", "Phase List", "Separator"):
                add_data_rows(shape, {"Source": f"{page.name}/{name}", "Kind": "lane_part"})
    for group in _all_groups(page):
        if group.id in layout.groups:
            box = layout.groups[group.id]
            add_data_rows(
                draw_backdrop(target, box.x, box.y, box.width, box.height, group.label, dashed=True),
                {"Source": group.id, "Kind": "group"},
            )
    for node in page.nodes:
        box = layout.nodes[node.id]
        text = node.label if node.sublabel is None else f"{node.label}\n{node.sublabel}"
        add_data_rows(draw_node(target, node.kind, box.x, box.y, *sizes[node.id], text), _rows(node, links))
    parallel: dict[tuple[str, str], int] = {}
    for edge in page.edges:
        if edge.kind == "page-link":
            continue
        n = parallel.get((edge.source, edge.target), 0)
        parallel[(edge.source, edge.target)] = n + 1
        points = layout.routes[(edge.source, edge.target, n)]
        source = f"{edge.source}->{edge.target}"
        add_data_rows(
            draw_path(target, points, arrow=True, dashed=edge.kind in _DASHED_EDGES), {"Source": source, "Kind": edge.kind}
        )
        if edge.label:
            (x1, y1), (x2, y2) = max(pairwise(points), key=lambda s: abs(s[0][0] - s[1][0]) + abs(s[0][1] - s[1][1]))
            add_data_rows(
                draw_label(target, snap((x1 + x2) / 2), snap((y1 + y2) / 2), edge.label),
                {"Source": source, "Kind": "edge_label"},
            )
