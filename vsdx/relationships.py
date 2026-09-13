"""Pure functions over a `.rels` tree and over `[Content_Types].xml`.

Three implementations of "allocate a relationship id" had grown up in this
package and disagreed on inputs no fixture happened to carry: one raised on an
empty rels part, one raised on any id not spelled `rIdN`, and one derived the id
from a part *filename*, so two parts numbered alike collided. Two
implementations of "declare a content type" disagreed on whether declaring the
same part twice was safe - one appended a duplicate, which is invalid OPC.

Everything here takes an element and returns a value or mutates that element.
Nothing reaches for a `VisioFile`, so these can be tested against a tree built
in three lines.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from vsdx import cont_types_namespace as CONTENT_TYPES_NS
from vsdx import document_rels_namespace as RELATIONSHIPS_NS

__all__ = [
    "all_of",
    "allocate_id",
    "append_if_absent",
    "ensure_override",
    "find",
    "remove",
    "remove_override",
]


def all_of(rels: Element) -> list[Element]:
    """Every relationship in the tree.

    One reading of "the relationships", so a caller cannot scan every child
    where this scans tagged elements and reach a different set.
    """
    return rels.findall(f"{RELATIONSHIPS_NS}Relationship")


def find(rels: Element, *, rel_type: str | None = None, target: str | None = None) -> Element | None:
    """The first relationship matching every criterion given, or None."""
    for relationship in all_of(rels):
        if rel_type is not None and relationship.attrib.get("Type") != rel_type:
            continue
        if target is not None and relationship.attrib.get("Target") != target:
            continue
        return relationship
    return None


def allocate_id(rels: Element) -> str:
    """The lowest `rIdN` not already in use.

    An id not spelled `rIdN` is left alone rather than parsed: OPC only requires
    it to be a unique XML id, and a package from another tool is free to use
    anything.
    """
    used = {relationship.attrib.get("Id") for relationship in all_of(rels)}
    candidate = 1
    while f"rId{candidate}" in used:
        candidate += 1
    return f"rId{candidate}"


def append_if_absent(rels: Element, *, rel_type: str, target: str, mode: str | None = None) -> Element:
    """Return the relationship for this type and target, adding one if needed.

    Idempotent: the callers only ever want one relationship per target.
    """
    existing = find(rels, rel_type=rel_type, target=target)
    if existing is not None:
        return existing

    attributes = {"Id": allocate_id(rels), "Type": rel_type, "Target": target}
    if mode is not None:
        # omitted rather than "Internal": that is the default, and Visio omits it
        attributes["TargetMode"] = mode
    relationship = Element(f"{RELATIONSHIPS_NS}Relationship", attributes)
    rels.append(relationship)
    return relationship


def remove(rels: Element, identifier: str) -> bool:
    """Remove the relationship with this id. True if one was there."""
    for relationship in all_of(rels):
        if relationship.attrib.get("Id") == identifier:
            rels.remove(relationship)
            return True
    return False


def _normalise_part(part_name: str) -> str:
    """Fold a part name for comparison: OPC compares them without regard to case."""
    return part_name.lower()


def ensure_override(types: Element, part_name: str, content_type: str) -> Element:
    """Declare `part_name`'s content type, once.

    Matched on the part name alone: a part already declared keeps the content
    type it was declared with, and this reports no disagreement. Nothing in this
    package declares one part two ways, and a checker is the right place to
    notice if something ever does.

    A new Override is placed after the last one sharing its content type, which
    is how Visio groups them, and at the end when it is the first of its kind.
    """
    overrides = types.findall(f"{CONTENT_TYPES_NS}Override")
    wanted = _normalise_part(part_name)
    for override in overrides:
        if _normalise_part(override.attrib.get("PartName", "")) == wanted:
            return override

    element = Element(f"{CONTENT_TYPES_NS}Override", {"PartName": part_name, "ContentType": content_type})
    same_kind = [o for o in overrides if o.attrib.get("ContentType") == content_type]
    if same_kind:
        types.insert(list(types).index(same_kind[-1]) + 1, element)
    else:
        types.append(element)
    return element


def remove_override(types: Element, part_name: str) -> bool:
    """Remove a part's content type declaration. True if one was there."""
    wanted = _normalise_part(part_name)
    for override in types.findall(f"{CONTENT_TYPES_NS}Override"):
        if _normalise_part(override.attrib.get("PartName", "")) == wanted:
            types.remove(override)
            return True
    return False
