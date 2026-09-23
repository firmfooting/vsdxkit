"""How the parts of a Visio package name one another.

A part is named by where it sits in the package, and it reaches every other
part through a relationship whose Target is relative to its own folder. The
library derives every name it uses from those two facts, here, so a page, a
master, and any part a shape refers to -- an image, an embedded object, a
data recordset -- are named by the same rules rather than by a folder string
of their own.
"""

from __future__ import annotations

import posixpath

PAGES_PART = "/visio/pages/pages.xml"
MASTERS_PART = "/visio/masters/masters.xml"
CONTENT_TYPES_PART = "/[Content_Types].xml"
APP_PART = "/docProps/app.xml"
DOCUMENT_PART = "/visio/document.xml"


def relationships_part_name(part_name: str) -> str:
    """The part holding `part_name`'s relationships: `/a/b.xml` -> `/a/_rels/b.xml.rels`."""
    folder, name = posixpath.split(part_name)
    return f"{folder.rstrip('/')}/_rels/{name}.rels"


def folder_of(part_name: str) -> str:
    """The folder a part sits in, as a part-name prefix with its trailing slash: `/a/b.xml` -> `/a/`.

    The slash keeps the prefix from matching a sibling folder whose name
    merely starts the same way, `/a-old/` beside `/a/`.
    """
    return f"{posixpath.dirname(part_name).rstrip('/')}/"


def target_part_name(source_part_name: str, target: str) -> str:
    """The part a relationship of `source_part_name` points at.

    The Target is joined onto the source part's folder exactly as written.
    `.` and `..` segments, an absolute Target and a percent-encoded one are
    left as they are, and the store's part-name check refuses them. OPC
    resolves them instead, and doing that here is #378.
    """
    return folder_of(source_part_name) + target


def relationship_target(source_part_name: str, part_name: str) -> str:
    """The Target a relationship of `source_part_name` writes to reach `part_name`, relative to the source's folder.

    The inverse of `target_part_name`: every folder of `part_name` below the
    one the two parts share is kept, so a part in a subfolder is reached where
    it is rather than by its file name alone.
    """
    return posixpath.relpath(part_name, posixpath.dirname(source_part_name))
