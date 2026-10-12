"""Describe a diagram as data, and compile it to a Visio document with no coordinates supplied.

A :class:`Diagram` is pages of :class:`Node`, :class:`Edge`, :class:`Group` and :class:`Lane`
values, each named by an id the caller chooses. :meth:`Diagram.build` lays the pages out
(see :mod:`vsdxkit.layout`) and draws them. The same description gives the same document, and
:meth:`Diagram.save` writes it as the same bytes on every platform.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, get_args

from vsdxkit._drawing import (
    KINDS,
    add_data_rows,
    clip_route,
    draw_backdrop,
    draw_label,
    draw_node,
    draw_path,
    label_size,
)
from vsdxkit.document import Document
from vsdxkit.errors import GraphError, InvalidOperationError
from vsdxkit.layout import Layout, LayoutNode, LayoutOptions, layered_layout, snap
from vsdxkit.pages import Page as VisioPage
from vsdxkit.swimlanes import DECORATION_ROW, DIAGRAM_WIDTHS, LABEL_CHARS_PER_INCH, LANE_HEIGHTS, MAX_LANES

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
_RESERVED_DATA = ("Linked page", "Linked node")
"""The Shape Data names a page-link writes on an ``off_page`` node."""
_XML_ILLEGAL = re.compile("[^\t\n\r\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")
"""Characters XML 1.0 cannot carry, which the package writer would fail on at save."""
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
    """Shape Data rows, written after the ``Source`` and ``Kind`` rows, sorted by name. Names and values must be strings. A ``Source`` entry replaces the default, the id; a ``Kind`` entry is refused, because the node's kind is always written. On an ``off_page`` node, ``Linked page`` and ``Linked node`` are reserved for page links and refused."""


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
        if isinstance(self.node_ids, str):
            raise GraphError(f"group {self.id!r} has node_ids {self.node_ids!r}, a string; pass a list of ids")
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
        if isinstance(self.node_ids, str):
            raise GraphError(f"lane {self.id!r} has node_ids {self.node_ids!r}, a string; pass a list of ids")
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

    def validate(self) -> dict[str, dict[str, str]]:
        """Refuse a description that cannot be drawn, naming the first thing wrong; otherwise return the Shape Data rows each ``page-link`` end gets.

        :raises GraphError: on a title, page name, id, label, sublabel or Shape Data name or value that is not a string or
            holds a character XML 1.0 cannot carry (a control character other than tab, newline and carriage return, a lone
            surrogate, U+FFFE or U+FFFF), a ``Kind`` entry in a
            node's ``data``, a repeated or empty id or page name, an edge or member naming a node
            not on its page, a node in two lanes or two groups, a node outside every lane on a page with lanes,
            a group split across lanes or nested two deep, more lanes than a page draws, a blank lane label, an
            unknown kind, a label or sublabel that is not a string, an edge end that is not a string, an ``off_page``
            node that ends two ``page-link`` edges, or a ``page-link`` that does not join an ``off_page`` node on its
            own page to one on another, or an ``off_page`` node whose ``data`` uses the reserved ``Linked page`` or ``Linked node``. Whether a laned page fits is known only after layout, so :meth:`build` checks it.
        """
        _text(self.title, "the diagram's title")
        if not self.pages:
            raise GraphError("a diagram needs at least one page")
        names = [p.name for p in self.pages]
        if not all(isinstance(n, str) and n.strip() for n in names):
            raise GraphError("every page needs a name with something in it")
        for name in names:
            _text(name, f"page name {name!r}")
        if len(set(names)) != len(names):
            raise GraphError(f"page names must be unique, and {sorted({n for n in names if names.count(n) > 1})} are not")
        where: dict[str, tuple[str, str]] = {}
        for page in self.pages:
            _register(page, where)
        for page in self.pages:
            _check_lanes(page)
            _check_membership(page, where)
            _check_edges(page, where)
        return _links(self)

    def build(self, *, layout: LayoutOptions | None = None) -> Document:
        """Compile to a new document with one page per :class:`Page`, creating shapes in input order.

        :param layout: spacing and flow direction; the defaults flow left to right
        :raises GraphError: as :meth:`validate`, and when a laid-out page with lanes is wider than 60 inches of diagram,
            a lane is more than 6 inches tall, a lane label is longer than 11 characters for each inch of its lane, or
            the layout refuses the graph, including an edge label or group heading with no room clear of the nodes and
            other labels
        """
        links = self.validate()
        options = layout if layout is not None else LayoutOptions()
        document = Document.new(page_name=self.pages[0].name)
        _set_title(document, self.title)
        for n, page in enumerate(self.pages):
            _draw_page(page, document.pages[0] if n == 0 else document.pages.create(page.name), options, links)
        return document

    def save(self, target: str | os.PathLike[str], *, layout: LayoutOptions | None = None) -> Path:
        """Build (see :meth:`build`) and write the document with a deterministic save: equal diagrams give equal bytes.

        :raises GraphError: as :meth:`build`
        """
        return self.build(layout=layout).save(target, deterministic=True)


def _text(value: object, what: str) -> None:
    """Refuse `value` unless it is a string XML can carry, naming `what` it was found in."""
    if not isinstance(value, str):
        raise GraphError(f"{what} is {value!r}; it must be a string")
    if match := _XML_ILLEGAL.search(value):
        raise GraphError(
            f"{what} holds {match.group()!r}, a character XML 1.0 cannot carry (a control character other than tab, newline and carriage return, a lone surrogate, U+FFFE or U+FFFF)"
        )


def _check_data(node: Node) -> None:
    """Refuse Shape Data that is not a mapping of strings, or that names the reserved ``Kind`` row."""
    if not isinstance(node.data, Mapping):
        raise GraphError(f"node {node.id!r} has data that is {node.data!r}; it must be a mapping of strings")
    for name, value in node.data.items():
        _text(name, f"node {node.id!r} has a Shape Data name that")
        _text(value, f"node {node.id!r} has Shape Data {name!r} that")
    if "Kind" in node.data:
        raise GraphError(f"node {node.id!r} sets Shape Data 'Kind', which is always written from its kind")


def _register(page: Page, where: dict[str, tuple[str, str]]) -> None:
    """Record every id on `page` as (page name, kind), refusing a repeat or an unknown kind."""
    for node in page.nodes:
        if node.kind not in get_args(NodeKind):
            raise GraphError(f"node {node.id!r} has kind {node.kind!r}; the kinds are {sorted(get_args(NodeKind))}")
        _claim(where, node.id, page.name, node.kind)
        for field_name in ("label", "sublabel"):
            value = getattr(node, field_name)
            if not (field_name == "sublabel" and value is None):
                _text(value, f"node {node.id!r} has a {field_name} that")
        _check_data(node)
        if node.kind == "off_page" and any(key in node.data for key in _RESERVED_DATA):
            raise GraphError(f"off_page node {node.id!r} uses {sorted(_RESERVED_DATA)}, which are reserved for page links")
    for lane in page.lanes:
        _claim(where, lane.id, page.name, "lane")
    for group in _all_groups(page):
        _claim(where, group.id, page.name, "group")
        _text(group.label, f"group {group.id!r} has a label that")


def _claim(where: dict[str, tuple[str, str]], id_: str, page: str, kind: str) -> None:
    """Record `id_` as belonging to `page`, or refuse it as used twice."""
    if not isinstance(id_, str) or not id_.strip():
        raise GraphError(f"id {id_!r} must be a string with something in it")
    _text(id_, f"id {id_!r}")
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
        for child in group.groups:
            if child.groups:
                raise GraphError(f"group {child.id!r} nests inside {group.id!r}; groups nest one level")
        direct = _group_members(group)
        for node_id, owner in direct:
            _on_page(page, node_id, where, f"group {owner!r}")
            if node_id in group_of:
                raise GraphError(f"node {node_id!r} is in groups {group_of[node_id]!r} and {owner!r}")
            group_of[node_id] = owner
        used = {lane_of[i] for i, _owner in direct if i in lane_of}
        if len(used) > 1:
            raise GraphError(f"group {group.id!r} holds nodes from lanes {sorted(used)}; a group stays in one lane")


def _group_members(group: Group) -> list[tuple[str, str]]:
    """Every (node id, innermost group id) under `group` and its children, in order, repeats kept so a caller can refuse them."""
    return [*((i, group.id) for i in group.node_ids), *((i, c.id) for c in group.groups for i in c.node_ids)]


def _check_lanes(page: Page) -> None:
    """Refuse more lanes than the swimlane drawing is verified for."""
    if len(page.lanes) > MAX_LANES:
        raise GraphError(f"page {page.name!r} has {len(page.lanes)} lanes; a page draws at most {MAX_LANES}")
    for lane in page.lanes:
        if not isinstance(lane.label, str) or not lane.label.strip():
            raise GraphError(f"lane {lane.id!r} needs a label with something in it")
        _text(lane.label, f"lane {lane.id!r} has a label that")


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
        if edge.label is not None:
            _text(edge.label, f"edge {edge.source!r} -> {edge.target!r} has a label that")
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
    _shape, width, height = KINDS[node.kind]
    lines = [*node.label.split("\n"), *(node.sublabel.split("\n") if node.sublabel else [])]
    return snap(max(width, 0.09 * max(len(line) for line in lines) + 0.5)), snap(max(height, 0.25 * len(lines) + 0.4))


def _rows(node: Node, links: Mapping[str, Mapping[str, str]]) -> dict[str, str]:
    """The Shape Data rows a node is written with: Source and Kind first, then the rest sorted by name."""
    rows = {"Source": node.data.get("Source", node.id), "Kind": node.kind}
    rows.update({k: node.data[k] for k in sorted(node.data) if k not in rows})
    rows.update(links.get(node.id, {}))
    return rows


def _layout_page(page: Page, options: LayoutOptions) -> tuple[Layout, dict[str, tuple[float, float]]]:
    """Lay `page` out with `options` and return the layout and each node's size; nothing is drawn."""
    lane_of = {i: lane.id for lane in page.lanes for i in lane.node_ids}
    group_of: dict[str, str] = {}
    parents: list[tuple[str, str]] = []
    for group in page.groups:
        group_of.update(dict(_group_members(group)))
        parents.extend((child.id, group.id) for child in group.groups)
    sizes = {n.id: _size(n) for n in page.nodes}
    if page.lanes:
        options = replace(options, margin=max(options.margin, _LANE_MARGIN))
    layout = layered_layout(
        tuple(LayoutNode(n.id, *sizes[n.id], lane_of.get(n.id), group_of.get(n.id)) for n in page.nodes),
        tuple((e.source, e.target) for e in page.edges if e.kind != "page-link"),
        tuple(lane.id for lane in page.lanes),
        tuple(g.id for g in _all_groups(page)),
        replace(
            options,
            parents=tuple(parents),
            headings=tuple((g.id, *_heading_size(g.label)) for g in _all_groups(page) if g.label.strip()),
            edge_labels=tuple(label_size(e.label) if e.label else None for e in page.edges if e.kind != "page-link"),
        ),
    )
    return layout, sizes


def _drawn_edges(page: Page) -> list[tuple[Edge, tuple[str, str, int]]]:
    """Each routed edge of `page` with its layout key (source, target, parallel index), in input order."""
    parallel: dict[tuple[str, str], int] = {}
    out = []
    for edge in page.edges:
        if edge.kind == "page-link":
            continue
        n = parallel.get((edge.source, edge.target), 0)
        parallel[(edge.source, edge.target)] = n + 1
        out.append((edge, (edge.source, edge.target, n)))
    return out


def _drawn_paths(
    page: Page, layout: Layout, sizes: Mapping[str, tuple[float, float]]
) -> dict[tuple[str, str, int], tuple[tuple[float, float], ...]]:
    """The points each edge is drawn through, its route clipped to the node outlines; the digest hashes these."""
    kinds = {node.id: node.kind for node in page.nodes}
    out = {}
    for edge, key in _drawn_edges(page):
        ends = [(kinds[i], (layout.nodes[i].x, layout.nodes[i].y, *sizes[i])) for i in (edge.source, edge.target)]
        out[key] = tuple(clip_route(layout.routes[key], *ends))
    return out


def _draw_page(page: Page, target: VisioPage, options: LayoutOptions, links: Mapping[str, Mapping[str, str]]) -> None:
    """Lay `page` out and draw it onto `target`: backdrops first, then nodes, then edges, so ids follow input order within each."""
    layout, sizes = _layout_page(page, options)
    if page.lanes:
        low, high = DIAGRAM_WIDTHS
        if layout.width - 2 * _LANE_LEFT > high:
            columns = len({box.x for box in layout.nodes.values()})  # a lane never wraps, so one x is one layer
            raise GraphError(
                f"page {page.name!r} lays out {layout.width:.1f} inches wide in {columns} columns, and a page with "
                f"lanes is drawn at most {high + 2 * _LANE_LEFT:g}; split the flow across pages"
            )
        layout = replace(layout, width=max(layout.width, low + 2 * _LANE_LEFT))
    target.width = layout.width
    target.height = layout.height
    _draw_layout(page, target, layout, sizes, links)


def _heading_size(text: str) -> tuple[float, float]:
    """Width and height in inches a group's heading needs: wide enough for its longest line, tall enough for its lines."""
    lines = text.split("\n")
    return snap(0.09 * max(len(line) for line in lines) + 0.5), snap(0.25 * len(lines))


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
        try:
            diagram = target.create_swimlanes(
                [(lane.label, box.height) for lane, box in zip(page.lanes, boxes, strict=True)],
                left=_LANE_LEFT,
                top=boxes[0].y + boxes[0].height / 2,
                width=layout.width - 2 * _LANE_LEFT,
            )
        except InvalidOperationError as error:  # a limit the checks above missed must still leave the builder as a GraphError
            raise GraphError(f"page {page.name!r} cannot draw its lanes: {error}") from error
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
                {"Source": group.id, "Kind": "group", DECORATION_ROW: "1"},
                clear=True,
            )
    for node in page.nodes:
        box = layout.nodes[node.id]
        text = node.label if node.sublabel is None else f"{node.label}\n{node.sublabel}"
        add_data_rows(draw_node(target, node.kind, box.x, box.y, *sizes[node.id], text), _rows(node, links), clear=True)
    drawn = _drawn_paths(page, layout, sizes)
    for edge, key in _drawn_edges(page):
        points = drawn[key]
        source = f"{edge.source}->{edge.target}"
        add_data_rows(
            draw_path(target, points, arrow=True, dashed=edge.kind in _DASHED_EDGES),
            {"Source": source, "Kind": edge.kind, DECORATION_ROW: "1"},
            clear=True,
        )
        if edge.label:
            label = layout.labels[key]
            add_data_rows(
                draw_label(target, label.x, label.y, edge.label),
                {"Source": source, "Kind": "edge_label", DECORATION_ROW: "1"},
                clear=True,
            )
