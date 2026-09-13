"""Namespace URIs and part paths the file format fixes, shared by the oracles.

Everything here is settled by MS-VSDX or ECMA-376. None of it is a judgment an
oracle is entitled to make differently, so a copy that has drifted is a typo,
and a typo in a namespace URI does not make one oracle argue with the other. It
makes it find zero shapes and agree with everything.

What the oracles keep separate is what they do with these names: which parts
they read, how they resolve a relationship, and what they do with one that will
not resolve. None of that is here.
"""

__all__ = [
    "CONTENT_TYPES_PART",
    "DOC_REL_NS",
    "MAIN_NS",
    "MASTERS_PART",
    "MASTERS_RELS_PART",
    "PAGES_PART",
    "PAGES_RELS_PART",
]

# ElementTree spells a qualified name `{uri}local`, so the braces belong to the
# constant.
MAIN_NS = "{http://schemas.microsoft.com/office/visio/2012/main}"
DOC_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# Package paths, as `zipfile` spells a member name: no leading slash. An OPC
# part name written inside `[Content_Types].xml` has one, and is not this.
CONTENT_TYPES_PART = "[Content_Types].xml"
PAGES_PART = "visio/pages/pages.xml"
PAGES_RELS_PART = "visio/pages/_rels/pages.xml.rels"
MASTERS_PART = "visio/masters/masters.xml"
MASTERS_RELS_PART = "visio/masters/_rels/masters.xml.rels"
