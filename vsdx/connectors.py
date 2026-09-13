from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element

import vsdx

from .shapes import Shape

namespace = "{http://schemas.microsoft.com/office/visio/2012/main}"


class Connect:
    """Connect class to represent a connection between two `Shape` objects"""

    @staticmethod
    def _parse_route(route: str) -> tuple[bool, str | None]:
        """Return point-glue and routing choices after validating route tokens."""
        route_parts: list[str] = route.split("|") if route else []
        allowed_parts = {"dynamic", "point", "straight", "rightangle", "curved"}
        unknown_parts = set(route_parts) - allowed_parts
        if unknown_parts:
            raise ValueError(f"unknown connector route part(s): {', '.join(sorted(unknown_parts))}")
        routing_parts = [part for part in route_parts if part in {"straight", "rightangle", "curved"}]
        if len(routing_parts) > 1:
            raise ValueError("connector route may specify only one routing behaviour")
        return "point" in route_parts, routing_parts[0] if routing_parts else None

    def __init__(self, xml: Element | None = None, page: vsdx.Page | None = None):
        if page is None:
            raise ValueError("Connect requires the page containing the connection")
        if xml is None:
            raise ValueError("Connect requires the connection's XML element")
        if type(xml) is not Element or xml.tag != f"{namespace}Connect":
            raise ValueError(f"Connect requires a {namespace}Connect element, got {xml.tag!r}")
        missing = [name for name in ("FromSheet", "ToSheet") if name not in xml.attrib]
        if missing:
            raise ValueError(f"Connect element is missing required attribute(s): {', '.join(missing)}")
        self.xml = xml
        self.page = page

    # Read from the element on each access, not copied in. `_remap_connect_records`
    # rewrites these very attributes when a shape is renumbered, so a Connect
    # built before the renumber would otherwise keep naming the vacated id - the
    # same second-store drift that #320 fixed on Shape.

    @property
    def from_id(self) -> str:
        """The connector shape this record leads from."""
        return self.xml.attrib["FromSheet"]

    @property
    def to_id(self) -> str:
        """The shape this record's connector terminates at."""
        return self.xml.attrib["ToSheet"]

    @property
    def from_rel(self) -> str | None:
        """Which end of the connector is glued: ``BeginX``, ``EndX``, or absent."""
        return self.xml.attrib.get("FromCell")

    @property
    def to_rel(self) -> str | None:
        """What the connector is glued to: ``PinX``, a ``Connections.Xn`` row, or absent."""
        return self.xml.attrib.get("ToCell")

    @staticmethod
    def create(
        page: vsdx.Page | None = None,
        from_shape: Shape | None = None,
        to_shape: Shape | None = None,
        route: str = "dynamic",
        from_cp: int = 0,
        to_cp: int = 0,
    ) -> Shape:
        """Create a new Connect object between from_shape and to_shape

        route: 'dynamic' (shape glue, default), 'point' (connection-point glue),
        optionally combined routing behaviour via 'straight', 'rightangle' or
        'curved'. When route='point', from_cp/to_cp give the 0-based connection
        point row index on the from/to shapes respectively.

        :returns: a new Connect object
        :rtype: Shape
        """
        if page is None:
            raise ValueError("Connect.create() requires a page")
        if from_shape is None or to_shape is None:
            raise ValueError("Connect.create() requires both from_shape and to_shape")
        page.vis._require_open("Connect.create()")
        Connect._parse_route(route)
        # validate everything _apply_glue can reject BEFORE provisioning
        # masters, copying shapes or appending records (issue #9 atomicity)
        Connect._validate_point_glue(from_shape, to_shape, route, from_cp, to_cp)
        if (
            from_shape is not None and to_shape is not None
        ):  # create new connector shape and connect items between this and the two shapes
            # create new connect shape and get id
            media = page.vis._shared_media()
            media_shape = media.straight_connector
            # state-based guard: masters provisioned if the document already
            # carries the masters relationship (the on-disk folder only exists
            # after save, so an os.path.exists guard double-provisioned on
            # 2nd+ calls)
            masters_rel_present = any(
                r.attrib.get("Type") == "http://schemas.microsoft.com/visio/2010/relationships/masters"
                for r in page.vis.document_rels()
            )
            new_master_id = None
            if not masters_rel_present:
                # document has no masters at all: copy the media masters folder
                for file_name, file in media.media.zip_file_contents.items():
                    if file_name.startswith(media.media._masters_folder):
                        new_file_name = file_name.replace(media.media._masters_folder, page.vis._masters_folder)
                        page.vis.zip_file_contents[new_file_name] = file
                page.vis.load_master_pages()  # load copied master page files into VisioFile object
                # document-level masters relationship
                page.vis._add_document_rel(
                    rel_type="http://schemas.microsoft.com/visio/2010/relationships/masters", target="masters/masters.xml"
                )
                # content-type overrides for masters.xml and master1.xml
                page.vis._add_content_types_override(
                    content_type="application/vnd.ms-visio.masters+xml", part_name_path="/visio/masters/masters.xml"
                )
                page.vis._add_content_types_override(
                    content_type="application/vnd.ms-visio.master+xml", part_name_path="/visio/masters/master1.xml"
                )
                # per-page master relationship (creates + registers the page
                # rels part so save_vsdx persists it)
                page._ensure_page_master_rel("rId1", "master1.xml")
            else:
                # document has masters: import the connector master (by name)
                # BEFORE the copy, while media_shape still points at its source
                new_master_id = page.vis._ensure_masters_for_shape(media_shape) or None

            connector_shape = media_shape.copy(page)  # default to straight connector
            connector_shape.text = ""  # clear text used to find shape
            if new_master_id:
                # repoint the copied shape at this document's imported master
                connector_shape.master_page_ID = new_master_id

            # per-page relationship for whichever master the connector uses
            effective_master_id = new_master_id or connector_shape.master_page_ID
            master_page = page.vis.get_master_page_by_id(effective_master_id) if effective_master_id else None
            if master_page is not None:
                master_part = master_page.filename.replace(page.vis._masters_folder + "/", "")
                page._ensure_page_master_rel(master_page.rel_id, master_part)

            # TitlesOfParts entry for the master name (app.xml 'Masters' count
            # is deliberately not written: real Visio packages omit it)
            shape_name = connector_shape.shape_name
            if shape_name and shape_name not in page.vis._titles_of_parts_list():
                page.vis._add_titles_of_parts_item(shape_name)

            # copy style used by new connector shape
            master_shape = connector_shape.master_shape
            line_style_id = master_shape.line_style_id if master_shape is not None else None
            if line_style_id is not None and not isinstance(page.vis._get_style_by_id(line_style_id), Element):
                # assume same if is ok, todo: use names for match and increment IDs
                media_style = media.media._get_style_by_id(line_style_id)
                if media_style is not None:
                    # copy, not alias: the donor document now outlives this
                    # call, so appending its live element would leave the two
                    # documents sharing one mutable StyleSheet
                    page.vis._style_sheets().append(copy.deepcopy(media_style))

            # wire glue to the from/to shapes (Visio-faithful formulas, see
            # tests/fixtures/com_reference/manifest.json for ground truth)
            Connect._apply_glue(connector_shape, from_shape, to_shape, route=route, from_cp=from_cp, to_cp=to_cp)

            # initial endpoints so the file renders sensibly even before Visio recalculates
            connector_shape.set_start_and_finish(from_shape.center_x_y, to_shape.center_x_y)
            return connector_shape
        raise ValueError("Connect.create() requires both from_shape and to_shape")

    @staticmethod
    def _connection_point_count(shape: Shape) -> int:
        sections = shape.xml.findall(f"{vsdx.namespace}Section")
        for section in sections:
            if section.attrib.get("N") == "Connection":
                return len(section.findall(f"{vsdx.namespace}Row"))
        return 0

    @staticmethod
    def _validate_point_glue(from_shape: Shape, to_shape: Shape, route: str, from_cp: int, to_cp: int) -> None:
        """Validate route and point-glue indices before any package mutation.

        Issue #9: Connect.create() provisioned masters and appended the
        connector, and retarget() removed existing records, before
        _apply_glue() rejected invalid indices — a caught ValueError left the
        package half-changed. Everything _apply_glue can reject is checked
        here so callers can fail before their first mutation.
        """
        point_glue, _routing = Connect._parse_route(route)
        if not point_glue:
            return
        for shape, cp in ((from_shape, from_cp), (to_shape, to_cp)):
            cp_count = Connect._connection_point_count(shape)
            if cp < 0 or cp >= cp_count:
                raise ValueError(
                    f"Shape ID {shape.ID} has {cp_count} connection point(s); cannot glue to connection point index {cp}"
                )

    @staticmethod
    def _apply_glue(
        connector_shape: Shape, from_shape: Shape, to_shape: Shape, route: str = "dynamic", from_cp: int = 0, to_cp: int = 0
    ):
        """Apply Visio-faithful glue between connector and from/to shapes.

        Shape glue (default): _WALKGLUE formulas + GlueType=2, matching what
        Visio writes for a dynamic connector glued to shape PinX.
        Point glue (route='point'): PAR(PNT(...)) formulas referencing
        Connections.Xn/Yn rows; raises ValueError if the shape has too few
        connection points.
        route may also set routing behaviour: 'straight' (ShapeRouteStyle=16),
        'rightangle' (ShapeRouteStyle=1), 'curved' (ShapeRouteStyle=17 +
        ConLineRouteExt=2).
        """
        conn_id = connector_shape.ID
        point_glue, routing = Connect._parse_route(route)

        if point_glue:
            ends = (("Begin", "EndX", from_shape, from_cp), ("End", "BeginX", to_shape, to_cp))
            for prefix, _opposite_cell, shape, cp in ends:
                cp_count = Connect._connection_point_count(shape)
                if cp >= cp_count:
                    raise ValueError(
                        f"Shape ID {shape.ID} has {cp_count} connection point(s); cannot glue to connection point index {cp}"
                    )
                k = cp + 1
                connector_shape.get_or_create_cell(f"{prefix}Trigger", f=f"_XFTRIGGER(Sheet{shape.ID}!EventXFMod)")
                pnt = f"PAR(PNT(Sheet{shape.ID}!Connections.X{k},Sheet{shape.ID}!Connections.Y{k}))"
                connector_shape.get_or_create_cell(f"{prefix}X", f=pnt)
                connector_shape.get_or_create_cell(f"{prefix}Y", f=pnt)
            beg_connect = (
                f'<Connect xmlns="http://schemas.microsoft.com/office/visio/2012/main" '
                f'FromSheet="{conn_id}" FromCell="BeginX" FromPart="9" '
                f'ToSheet="{from_shape.ID}" ToCell="Connections.X{from_cp + 1}" '
                f'ToPart="{99 + from_cp + 1}"/>'
            )
            end_connect = (
                f'<Connect xmlns="http://schemas.microsoft.com/office/visio/2012/main" '
                f'FromSheet="{conn_id}" FromCell="EndX" FromPart="12" '
                f'ToSheet="{to_shape.ID}" ToCell="Connections.X{to_cp + 1}" '
                f'ToPart="{99 + to_cp + 1}"/>'
            )
        else:
            # shape glue - dynamic connector behaviour, formulas as written by Visio 16
            connector_shape.get_or_create_cell("BegTrigger", f=f"_XFTRIGGER(Sheet{from_shape.ID}!EventXFMod)")
            connector_shape.get_or_create_cell("EndTrigger", f=f"_XFTRIGGER(Sheet{to_shape.ID}!EventXFMod)")
            walkglue_begin = "_WALKGLUE(BegTrigger,EndTrigger,WalkPreference)"
            walkglue_end = "_WALKGLUE(EndTrigger,BegTrigger,WalkPreference)"
            connector_shape.get_or_create_cell("BeginX", f=walkglue_begin)
            connector_shape.get_or_create_cell("BeginY", f=walkglue_begin)
            connector_shape.get_or_create_cell("EndX", f=walkglue_end)
            connector_shape.get_or_create_cell("EndY", f=walkglue_end)
            connector_shape.get_or_create_cell("GlueType", v="2")
            connector_shape.get_or_create_cell("ObjType", v="2")
            # explicit dynamic routing, as written by Visio 16; overrides the
            # template connector's inherited ShapeRouteStyle=16 (straight)
            connector_shape.get_or_create_cell("ShapeRouteStyle", v="0")
            connector_shape.get_or_create_cell("ConLineRouteExt", v="0")
            connector_shape.get_or_create_cell("ConFixedCode", v="6")
            beg_connect = (
                f'<Connect xmlns="http://schemas.microsoft.com/office/visio/2012/main" '
                f'FromSheet="{conn_id}" FromCell="BeginX" FromPart="9" '
                f'ToSheet="{from_shape.ID}" ToCell="PinX" ToPart="3"/>'
            )
            end_connect = (
                f'<Connect xmlns="http://schemas.microsoft.com/office/visio/2012/main" '
                f'FromSheet="{conn_id}" FromCell="EndX" FromPart="12" '
                f'ToSheet="{to_shape.ID}" ToCell="PinX" ToPart="3"/>'
            )

        if routing == "straight":
            connector_shape.get_or_create_cell("ShapeRouteStyle", v="16")
        elif routing == "rightangle":
            connector_shape.get_or_create_cell("ShapeRouteStyle", v="1")
        elif routing == "curved":
            connector_shape.get_or_create_cell("ShapeRouteStyle", v="17")
            connector_shape.get_or_create_cell("ConLineRouteExt", v="2")

        # Add these new connection relationships to the page
        page = connector_shape.page
        page.add_connect(Connect(xml=ET.fromstring(end_connect), page=page))
        page.add_connect(Connect(xml=ET.fromstring(beg_connect), page=page))

    @staticmethod
    def retarget(
        page: vsdx.Page,
        connector_shape: Shape,
        from_shape: Shape | None = None,
        to_shape: Shape | None = None,
        route: str = "dynamic",
        from_cp: int = 0,
        to_cp: int = 0,
    ) -> Shape:
        """Retarget an existing connector to new endpoints.

        Only the ends provided are moved; the other end keeps its current
        glue (resolved from the page's existing Connect records). Reuses
        _apply_glue for cells and records — removal of the old records goes
        through the page's single record-removal path.

        :returns: the connector Shape
        """
        # its own guard: the first write is page.remove_connect_records(), so
        # without this the error names a method the caller never called
        page.vis._require_open("Connect.retarget()")
        current_from = current_to = None
        current_from_cp = current_to_cp = 0
        for connect in page.connects:
            if connect.from_id == str(connector_shape.ID):
                # note: deliberately not named to_shape - that is the parameter
                connected_shape = page.find_shape_by_id(connect.to_id) if connect.to_id else None
                if connect.from_rel == "BeginX":
                    current_from = connected_shape
                    if connect.to_rel and connect.to_rel.startswith("Connections"):
                        current_from_cp = int(connect.to_rel.rsplit(".", 1)[1]) - 1
                elif connect.from_rel == "EndX":
                    current_to = connected_shape
                    if connect.to_rel and connect.to_rel.startswith("Connections"):
                        current_to_cp = int(connect.to_rel.rsplit(".", 1)[1]) - 1
        new_from = from_shape if from_shape is not None else current_from
        new_to = to_shape if to_shape is not None else current_to
        if new_from is None or new_to is None:
            raise ValueError("connector has no resolvable endpoints to keep")

        # validate everything _apply_glue can reject BEFORE removing the
        # existing records (issue #9 atomicity)
        Connect._validate_point_glue(
            new_from,
            new_to,
            route,
            from_cp if from_shape is not None else current_from_cp,
            to_cp if to_shape is not None else current_to_cp,
        )
        page.remove_connect_records({str(connector_shape.ID)})
        Connect._apply_glue(
            connector_shape,
            new_from,
            new_to,
            route=route,
            from_cp=from_cp if from_shape is not None else current_from_cp,
            to_cp=to_cp if to_shape is not None else current_to_cp,
        )
        connector_shape.set_start_and_finish(new_from.center_x_y, new_to.center_x_y)
        return connector_shape

    @property
    def shape_id(self) -> str | None:
        # ref to the shape where the connector terminates - convenience property
        return self.to_id

    @property
    def shape(self) -> Shape | None:
        return self.page.find_shape_by_id(self.shape_id) if self.shape_id else None

    @property
    def connector_shape_id(self) -> str | None:
        # ref to the connector shape - convenience property
        return self.from_id

    @property
    def connector_shape(self) -> Shape | None:
        return self.page.find_shape_by_id(self.connector_shape_id) if self.connector_shape_id else None

    def __repr__(self):
        return f"Connect: from={self.from_id} to={self.to_id} connector_id={self.connector_shape_id} shape_id={self.shape_id}"
