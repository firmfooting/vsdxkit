"""What a shape or page reads is computed from the XML, not held (#102).

Two Shape objects for one shape are equal (#101), so a write through one has
to be read through the other. Each test names the cache that used to make it
fail.
"""

import copy

from vsdxkit import namespace
from vsdxkit.document import Document


def test_a_cell_added_through_one_shape_object_is_read_through_another(vsdx_copy):
    """Fails if `Shape.cells` is a snapshot taken when the Shape was built."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    writer = page.shapes.require_id("1")
    reader = page.shapes.require_id("1")
    assert reader.cell_value("Added") is None

    writer.set_cell_value("Added", 7)

    assert reader.cell_value("Added") == "7"
    assert "Added" in reader.cells


def test_a_cell_removed_from_the_xml_is_gone_from_the_shape(vsdx_copy):
    """Fails if a Shape keeps answering from a cell no longer in its XML."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    shape = vis.pages[0].shapes.require_id("1")
    pin_x = shape.cells["PinX"]

    shape.xml.remove(pin_x.xml)

    assert "PinX" not in shape.cells
    assert shape.cell_value("PinX") is None


def test_a_property_relabelled_in_place_is_keyed_under_its_new_label(vsdx_copy):
    """Fails if `data_properties` is held and keyed on its rows' identity, which a relabel leaves alone."""
    vis = Document.open(vsdx_copy("test6_shape_properties.vsdx"))
    page = vis.pages[0]
    writer = page.shapes.require_id("1")
    reader = page.shapes.require_id("1")
    assert "my_property_label" in reader.data_properties

    writer.data_properties["my_property_label"].set_attribute("Label", "V", "relabelled")

    assert "relabelled" in reader.data_properties
    assert "my_property_label" not in reader.data_properties
    assert "relabelled" in writer.data_properties


def test_a_page_s_background_is_read_from_pages_xml(vsdx_copy):
    """Fails if `Page.background` answers from what it read first."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    assert page.background is False

    page._page_xml().attrib["Background"] = "1"

    assert page.background is True


def test_a_master_added_after_a_shape_missed_it_is_resolved(vsdx_copy):
    """Fails if a shape holds on to finding no master after the document gains the one it names.

    The memo on `Shape.master_shape` survives the benchmark, so it has to be
    let go when the masters change: the catalog counts those changes.
    """
    source_path = vsdx_copy("test5_master.vsdx")
    target_path = vsdx_copy("test1.vsdx")
    source = Document.open(source_path)
    rehearsal = Document.open(target_path)
    instance = next(shape for shape in source.pages[0].all_shapes if shape.xml.attrib.get("Master"))
    imported_id = instance.copy(rehearsal.pages[0]).master_page_ID

    source = Document.open(source_path)
    target = Document.open(target_path)
    instance = next(shape for shape in source.pages[0].all_shapes if shape.xml.attrib.get("Master"))
    waiting = target.pages[0].shapes.require_id("1")
    waiting.master_page_ID = imported_id
    assert waiting.master_shape is None

    instance.copy(target.pages[0])

    master = waiting.master_shape
    assert master is not None
    assert master.page.page_id == imported_id


def test_a_geometry_section_added_to_a_resolved_master_is_merged(vsdx_copy):
    """Fails if a shape holds on to a master resolved before the master's Geometry section changed.

    The Shape held for the master locates its Geometry section when it is
    built, so the memo is keyed on the master element's children as well as
    on the catalog's revision.
    """
    vis = Document.open(vsdx_copy("test5_master.vsdx"))
    instance = vis.pages[0].shapes.require_id("2")
    master = instance.master_shape
    assert master is not None
    section = master.xml.find(f"{namespace}Section[@N='Geometry']")
    assert section is not None
    replacement = copy.deepcopy(section)
    row = replacement.find(f"{namespace}Row")
    assert row is not None
    replacement.remove(row)

    position = list(master.xml).index(section)
    master.xml.remove(section)
    master.xml.insert(position, replacement)

    held = instance.master_shape
    assert held is not None
    assert held.geometry is not None
    assert held.geometry.xml is replacement
