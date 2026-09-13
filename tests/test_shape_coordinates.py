import pytest

from vsdxkit import VisioFile


@pytest.mark.parametrize(
    "attribute",
    (
        "x",
        "y",
        "loc_x",
        "loc_y",
        "line_to_x",
        "line_to_y",
        "begin_x",
        "begin_y",
        "end_x",
        "end_y",
        "width",
        "height",
        "angle",
    ),
)
def test_coordinate_setters_reject_none(vsdx_copy, attribute):
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_text("Shape to copy")
        assert shape is not None

        with pytest.raises(TypeError, match="coordinate value cannot be None"):
            setattr(shape, attribute, None)

        assert all(cell.value != "None" for cell in shape.cells.values())


@pytest.mark.parametrize("attribute", ("line_weight", "end_arrow"))
def test_scalar_setters_do_not_bypass_null_guard(vsdx_copy, attribute):
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_text("Shape to copy")
        assert shape is not None

        with pytest.raises(TypeError, match="XML attribute value cannot be None"):
            setattr(shape, attribute, None)

        assert all(cell.value != "None" for cell in shape.cells.values())


def test_cell_value_rejects_none_without_mutation(vsdx_copy):
    with VisioFile(vsdx_copy("test2.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_id("16")
        assert shape is not None
        cell = shape.cells["PinX"]
        before = dict(cell.xml.attrib)

        with pytest.raises(TypeError, match="XML attribute value cannot be None"):
            cell.value = None

        assert cell.xml.attrib == before


def test_geometry_row_rejects_none(vsdx_copy):
    with VisioFile(vsdx_copy("test2.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_id("16")
        assert shape is not None and shape.geometry is not None
        row = next(row for row in shape.geometry.rows.values() if str(row.row_type).lower() == "moveto")
        x_cell = row.cells.pop("X")
        if x_cell.xml in list(row.xml):
            row.xml.remove(x_cell.xml)
        before = list(row.xml)

        with pytest.raises(TypeError, match="XML attribute value cannot be None"):
            row.x = None

        assert "X" not in row.cells
        assert list(row.xml) == before


def test_geometry_move_skips_missing_coordinates(vsdx_copy):
    with VisioFile(vsdx_copy("test2.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_id("16")
        assert shape is not None and shape.geometry is not None
        row = next(row for row in shape.geometry.rows.values() if str(row.row_type).lower() == "moveto")
        x_cell = row.cells.pop("X")
        if x_cell.xml in list(row.xml):
            row.xml.remove(x_cell.xml)

        shape.geometry.move(1.0, 1.0)

        assert "X" not in row.cells
        assert all(cell.value != "None" for cell in row.cells.values())


def test_connector_coordinates_reject_none_before_mutation(vsdx_copy):
    with VisioFile(vsdx_copy("test8_simple_connector.vsdx")) as vis:
        page = vis.pages[0]
        source = page.find_shape_by_text("Shape A")
        target = page.find_shape_by_text("Shape B")
        assert source is not None and target is not None
        connector = page.connect_shapes(source, target)
        before = (connector.x, connector.y, connector.begin_x, connector.begin_y, connector.end_x, connector.end_y)

        with pytest.raises(ValueError, match="start and finish coordinates cannot be None"):
            connector.set_start_and_finish((None, 1.0), (2.0, 3.0))

        assert (connector.x, connector.y, connector.begin_x, connector.begin_y, connector.end_x, connector.end_y) == before
