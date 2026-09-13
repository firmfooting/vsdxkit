"""Serialised parts must carry the prefixes Visio itself writes.

Consumers stricter than Visio — libvisio (LibreOffice Draw) and draw.io's
importer — reject parts whose elements arrive under a generated ``ns0:``
prefix instead of the expected default namespace. See upstream
dave-howard/vsdx#90 and #35.
"""

import io
import os
import re
import zipfile
from xml.etree import ElementTree

import pytest

import vsdxkit
from vsdxkit import namespace, xmlio

FIXTURES = os.path.dirname(os.path.realpath(__file__))

# ElementTree invents ns0:, ns1:, … for any namespace it has no prefix for.
GENERATED_PREFIX_RE = re.compile(rb"[<\s]/?ns\d+:")

ALL_PACKAGES = sorted(name for name in os.listdir(FIXTURES) if name.endswith((".vsdx", ".vsdm")))


def _saved_copy(filename: str, tmp_path) -> str:
    out = os.path.join(str(tmp_path), "out" + os.path.splitext(filename)[1])
    with vsdxkit.VisioFile(os.path.join(FIXTURES, filename)) as vis:
        page = vis.pages[0]
        _ = page.child_shapes  # force the page part to be parsed and re-serialised
        vis.save_vsdx(out)
    # save_vsdx may adjust the suffix it was handed; take whatever it wrote
    written = os.listdir(str(tmp_path))
    assert len(written) == 1, written
    return os.path.join(str(tmp_path), written[0])


@pytest.mark.parametrize("filename", ALL_PACKAGES)
def test_saved_parts_have_no_generated_namespace_prefixes(filename, tmp_path):
    with zipfile.ZipFile(_saved_copy(filename, tmp_path)) as archive:
        offenders = {
            name
            for name in archive.namelist()
            if name.endswith((".xml", ".rels")) and GENERATED_PREFIX_RE.search(archive.read(name))
        }
    assert offenders == set()


@pytest.mark.parametrize("filename", ALL_PACKAGES)
def test_saved_parts_are_well_formed(filename, tmp_path):
    """Re-prefixing must not rebind a reserved prefix such as `xml:`."""
    with zipfile.ZipFile(_saved_copy(filename, tmp_path)) as archive:
        for name in archive.namelist():
            if not name.endswith((".xml", ".rels")):
                continue
            ElementTree.fromstring(archive.read(name))  # raises ParseError if not


@pytest.mark.parametrize("filename", ALL_PACKAGES)
def test_visio_parts_declare_the_visio_default_namespace(filename, tmp_path):
    """Parts rooted in the Visio vocabulary must carry it as the default namespace.

    Theme parts are rooted in DrawingML and keep their `a:` prefix, so the rule
    follows each part's own root element rather than its path.
    """
    visio_uri = namespace[1:-1]
    checked = 0
    with zipfile.ZipFile(_saved_copy(filename, tmp_path)) as archive:
        for name in archive.namelist():
            if not name.endswith(".xml"):
                continue
            body = archive.read(name)
            root_tag = ElementTree.fromstring(body).tag
            if not root_tag.startswith(f"{{{visio_uri}}}"):
                continue
            checked += 1
            head = body[:1024].decode("utf-8", "replace")
            # parts the library did not rewrite keep Visio's own single quotes
            declared = f'xmlns="{visio_uri}"' in head or f"xmlns='{visio_uri}'" in head
            assert declared, f"{name} does not declare the Visio default namespace"
    assert checked, "expected the package to contain parts in the Visio namespace"


def test_setting_text_preserves_the_formatting_runs_as_elements(tmp_path):
    """The cp/pp runs bracketing a shape's text survive an edit as real elements.

    The runs used to be spliced back as serialised text matched by an `ns0:`
    regex, which broke the moment the Visio namespace stopped being prefixed.
    """
    with vsdxkit.VisioFile(os.path.join(FIXTURES, "test2.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_id("9")
        text_element = shape.xml.find(f"{namespace}Text")
        before = [(child.tag, dict(child.attrib)) for child in text_element]
        assert before, "fixture shape is expected to carry formatting runs"

        shape.text = "replaced"

        text_element = shape.xml.find(f"{namespace}Text")
        assert shape.text == "replaced"
        assert [(child.tag, dict(child.attrib)) for child in text_element] == before


# --------------------------------------------------------------------------
# prefixes the document chose
# --------------------------------------------------------------------------

VISIO_MAIN = "http://schemas.microsoft.com/office/visio/2012/main"
RELATIONSHIPS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
LUCIDCHART = "http://www.lucidchart.com"


def _round_trip_part(source: str) -> str:
    """Parse a part the way the library does, then write it straight back out."""
    contents = {"part.xml": io.BytesIO(source.encode("utf-8"))}
    tree = xmlio.file_to_xml("part.xml", contents)
    assert tree is not None
    xmlio.xml_to_file(tree, "part.xml", contents)
    return contents["part.xml"].getvalue().decode("utf-8")


def test_a_prefix_the_document_chose_survives_a_round_trip():
    """A prefix belongs to the document that chose it, not to this library.

    Lucidchart binds `lc:`, which is a vocabulary the library has no entry for,
    so it used to invent a prefix from the URI: `xwwwlucidchartcom:`.
    """
    written = _round_trip_part(
        f'<PageContents xmlns="{VISIO_MAIN}"><lc:Property xmlns:lc="{LUCIDCHART}" Name="RuleList"/></PageContents>'
    )
    assert f'xmlns:lc="{LUCIDCHART}"' in written
    assert "<lc:Property" in written
    assert "lucidchartcom" not in written  # the prefix invented from the URI


def test_the_prefix_the_document_chose_beats_the_registered_one():
    """The registered table is the fallback, not an override.

    The library spells the relationships namespace `r:`; a part that spells it
    `rel:` has to come back spelled `rel:`.
    """
    written = _round_trip_part(
        f'<PageContents xmlns="{VISIO_MAIN}" xmlns:rel="{RELATIONSHIPS}"><Shape rel:id="rId1"/></PageContents>'
    )
    assert f'xmlns:rel="{RELATIONSHIPS}"' in written
    assert "rel:id=" in written


def test_a_generated_prefix_in_the_source_is_not_preserved():
    """`ns0:` is ElementTree's invention, not a spelling any document chose.

    A part carrying one was written by a vsdx older than the per-part prefix
    fix, and re-prefixing it is what issue #60 is for.
    """
    written = _round_trip_part(f'<ns0:PageContents xmlns:ns0="{VISIO_MAIN}"/>')
    assert f'<PageContents xmlns="{VISIO_MAIN}"' in written


def _round_trip_with_added(source: str, tag: str) -> str:
    """Round-trip a part with one element the source never declared added to it."""
    contents = {"part.xml": io.BytesIO(source.encode("utf-8"))}
    tree = xmlio.file_to_xml("part.xml", contents)
    assert tree is not None
    root = tree.getroot()
    assert root is not None
    root.append(ElementTree.Element(tag))
    xmlio.xml_to_file(tree, "part.xml", contents)
    return contents["part.xml"].getvalue().decode("utf-8")


def test_a_namespace_the_part_never_declared_takes_the_registered_prefix():
    """An element added in memory has no declared prefix to preserve."""
    written = _round_trip_with_added(f'<PageContents xmlns="{VISIO_MAIN}"/>', f"{{{RELATIONSHIPS}}}Rel")
    assert f'xmlns:r="{RELATIONSHIPS}"' in written
    assert "<r:Rel" in written


def test_a_namespace_neither_declared_nor_registered_is_still_not_ns0():
    """Only a vocabulary introduced in memory can reach the invented prefix now.

    Every namespace a parsed part uses is one that part declared, so the
    fallback is left guarding issue #60 for trees the library builds.
    """
    written = _round_trip_with_added(f'<PageContents xmlns="{VISIO_MAIN}"/>', "{urn:example:widgets}Widget")
    assert not GENERATED_PREFIX_RE.search(written.encode("utf-8"))
    assert [child.tag for child in ElementTree.fromstring(written)] == ["{urn:example:widgets}Widget"]


def test_a_tree_the_library_built_itself_still_takes_the_registered_prefixes():
    """Templating and page creation parse from a string, not from the package."""
    root = ElementTree.fromstring(f'<PageContents xmlns="{VISIO_MAIN}"/>')
    root.append(ElementTree.Element(f"{{{RELATIONSHIPS}}}Rel"))
    contents: dict[str, io.BytesIO] = {}
    xmlio.xml_to_file(ElementTree.ElementTree(root), "part.xml", contents)
    written = contents["part.xml"].getvalue().decode("utf-8")
    assert f'<PageContents xmlns="{VISIO_MAIN}"' in written
    assert f'xmlns:r="{RELATIONSHIPS}"' in written


def test_two_namespaces_that_chose_the_same_prefix_are_kept_distinct():
    """A prefix binding belongs to the element that declares it.

    One document can therefore bind `lc:` to two namespaces, and only one of
    them can keep it on the way out.
    """
    written = _round_trip_part(
        f'<PageContents xmlns="{VISIO_MAIN}"><lc:One xmlns:lc="urn:one"/><lc:Two xmlns:lc="urn:two"/></PageContents>'
    )
    bound = {
        prefix: uri for _, (prefix, uri) in ElementTree.iterparse(io.BytesIO(written.encode("utf-8")), events=("start-ns",))
    }
    assert bound["lc"] == "urn:one"
    assert set(bound.values()) >= {"urn:one", "urn:two"}
    assert not GENERATED_PREFIX_RE.search(written.encode("utf-8"))


# `test5_master.vsdx` is the only non-conformant fixture in the corpus (#298)
# and these three read it by name rather than by parameter, so the structural
# check cannot tell its inherited defects from ones a save introduced.
@pytest.mark.allow_invalid_package
def test_the_lucidchart_prefix_survives_a_real_save(tmp_path):
    """The whole save path, not `xmlio` alone.

    `test5_master.vsdx` carries 28 `lc:Property` elements on its one page.
    """
    with zipfile.ZipFile(_saved_copy("test5_master.vsdx", tmp_path)) as archive:
        page = archive.read("visio/pages/page1.xml").decode("utf-8")
    assert f'xmlns:lc="{LUCIDCHART}"' in page
    assert page.count("<lc:Property") == 28
    assert "lucidchartcom" not in page


def test_a_declared_prefix_beats_a_registered_one_that_wants_the_same_spelling():
    """Which of the two gets suffixed cannot depend on how the URIs sort.

    This part spells Lucidchart `r:`, and the library then adds an element in
    the relationships namespace, which it also spells `r:`.
    """
    written = _round_trip_with_added(
        f'<PageContents xmlns="{VISIO_MAIN}"><r:Property xmlns:r="{LUCIDCHART}"/></PageContents>',
        f"{{{RELATIONSHIPS}}}Rel",
    )
    bound = {
        prefix: uri for _, (prefix, uri) in ElementTree.iterparse(io.BytesIO(written.encode("utf-8")), events=("start-ns",))
    }
    assert bound["r"] == LUCIDCHART
    assert set(bound.values()) >= {LUCIDCHART, RELATIONSHIPS}


def _page_part(path: str, member: str = "visio/pages/page1.xml") -> str:
    with zipfile.ZipFile(path) as archive:
        return archive.read(member).decode("utf-8")


# `test5_master.vsdx` is the only non-conformant fixture in the corpus (#298)
# and these three read it by name rather than by parameter, so the structural
# check cannot tell its inherited defects from ones a save introduced.
@pytest.mark.allow_invalid_package
def test_a_copied_page_keeps_the_prefixes_its_source_declared(tmp_path):
    """Otherwise one package spells the same vocabulary two ways.

    `copy_page` serialises the source page and parses the string back, which
    loses what `file_to_xml` recorded about it.
    """
    out = os.path.join(str(tmp_path), "copied.vsdx")
    with vsdxkit.VisioFile(os.path.join(FIXTURES, "test5_master.vsdx")) as vis:
        vis.copy_page(vis.pages[0])
        vis.save_vsdx(out)
    assert f'xmlns:lc="{LUCIDCHART}"' in _page_part(out, "visio/pages/page2.xml")
    assert "lucidchartcom" not in _page_part(out, "visio/pages/page2.xml")


# `test5_master.vsdx` is the only non-conformant fixture in the corpus (#298)
# and these three read it by name rather than by parameter, so the structural
# check cannot tell its inherited defects from ones a save introduced.
@pytest.mark.allow_invalid_package
def test_a_rendered_page_keeps_the_prefixes_it_declared(tmp_path):
    """Rendering a template replaces the page tree with one parsed from a string."""
    out = os.path.join(str(tmp_path), "rendered.vsdx")
    with vsdxkit.VisioFile(os.path.join(FIXTURES, "test5_master.vsdx")) as vis:
        vis.jinja_render_vsdx(context={})
        vis.save_vsdx(out)
    assert f'xmlns:lc="{LUCIDCHART}"' in _page_part(out)
    assert "lucidchartcom" not in _page_part(out)


# --------------------------------------------------------------------------
# the package as it is held in memory
# --------------------------------------------------------------------------

PACKAGE_RELATIONSHIPS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _in_memory_offenders(vis) -> dict[str, str]:
    """Parts sitting in the open package that carry a generated prefix.

    Read from `zip_file_contents` rather than from a saved file. `save_vsdx`
    re-serialises every page, its rels and the document-level parts on the way
    out, so a part written with a generated prefix when it was built is
    overwritten before it reaches disk -- which is why no assertion against a
    saved archive can see it (#360).
    """
    return {
        name: part.getvalue()[:160].decode("utf-8", "replace")
        for name, part in vis.zip_file_contents.items()
        if name.endswith((".xml", ".rels")) and GENERATED_PREFIX_RE.search(part.getvalue())
    }


def test_connecting_shapes_writes_the_page_rels_in_the_default_namespace(vsdx_copy, tmp_path):
    """A page gaining its first master relationship gains a rels part with it.

    That part is in the package-relationships namespace, which is not the one
    holding the default prefix process-wide, so serialising it outside the
    per-part prefix map wrote `<ns0:Relationships>` -- the spelling issue #60
    exists to keep out of the package.
    """
    out = os.path.join(str(tmp_path), "connected.vsdx")
    with vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        page.connect_shapes(page.child_shapes[0], page.child_shapes[1])
        rels_member = f"{vis.directory}/visio/pages/_rels/page1.xml.rels"
        in_memory = vis.zip_file_contents[rels_member].getvalue()
        vis.save_vsdx(out)

    assert f'<Relationships xmlns="{PACKAGE_RELATIONSHIPS}"'.encode() in in_memory
    assert not GENERATED_PREFIX_RE.search(in_memory)
    with zipfile.ZipFile(out) as archive:
        assert archive.read("visio/pages/_rels/page1.xml.rels") == in_memory


def test_bootstrapping_masters_writes_the_visio_default_namespace(vsdx_copy):
    """The masters part created for a document that declares one but has none.

    Called directly because its only caller overwrites the part a few lines
    later, so these bytes never reach the package through the public API -- but
    they are still what the next caller would get.
    """
    with vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as vis:
        assert vis.masters_xml is None, "fixture is expected to have no masters part"
        vis._bootstrap_masters()
        written = vis.zip_file_contents[f"{vis._masters_folder}/masters.xml"].getvalue()

    assert f'<Masters xmlns="{namespace[1:-1]}"'.encode() in written
    assert not GENERATED_PREFIX_RE.search(written)


def _connect_two_shapes(vis) -> None:
    page = vis.pages[0]
    page.connect_shapes(page.child_shapes[0], page.child_shapes[1])


# The operations that write a part into the package before save. An operation
# that only edits a tree in memory cannot fail this check -- nothing it touched
# has been serialised yet -- so the test asserts each entry writes a part, and
# an entry belongs here when an operation starts writing one, not when it starts
# changing the document.
#
# Creating a connector is currently the whole of that list, and it reaches both
# master-provisioning branches: `test1.vsdx` has no masters, so the bundled
# masters folder is copied wholesale; `test3_house.vsdx` has one, so the
# connector master is imported into the existing `masters.xml` instead.
PACKAGE_MUTATIONS = (
    ("test1.vsdx", _connect_two_shapes),
    ("test3_house.vsdx", _connect_two_shapes),
)


@pytest.mark.parametrize(
    ("filename", "mutate"),
    PACKAGE_MUTATIONS,
    ids=[f"{name}-{mutate.__name__[1:]}" for name, mutate in PACKAGE_MUTATIONS],
)
def test_no_operation_leaves_a_generated_prefix_in_the_package(filename, mutate, vsdx_copy):
    """The class of defect, rather than the two call sites #360 found.

    A part serialised outside `xmlio` stays invisible until #89 stops the save
    path rewriting every page on the way out, so the next one would otherwise
    be found by a LibreOffice import failure rather than by this suite.
    """
    with vsdxkit.VisioFile(vsdx_copy(filename)) as vis:
        before = {name: part.getvalue() for name, part in vis.zip_file_contents.items()}
        mutate(vis)
        written = {name for name, part in vis.zip_file_contents.items() if before.get(name) != part.getvalue()}
        assert written, "the operation wrote no part into the package, so it cannot fail this check"
        assert _in_memory_offenders(vis) == {}
