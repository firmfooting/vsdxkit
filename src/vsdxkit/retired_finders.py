"""The finders :class:`vsdxkit.shapes.ShapeCollection` replaced (#103), kept until 1.0.0.

``Page`` and ``Shape`` each had their own copy of every finder. Both now
forward here with the collection they search - a page's ``shapes``, a shape's
``descendants`` - so each finder has one implementation, and all of them go
in Phase 5 by deleting this module.

Each keeps the behaviour it had: the ``find_shape_*`` forms answer the first
match, text matches a substring, and a property value is compared as text.

``vsdxkit.shapes`` imports this module, so it cannot import that one back.
What a finder reads of a shape and of a collection is declared here instead.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Iterator, Mapping
from typing import Protocol, TypeVar
from xml.etree.ElementTree import Element


class SearchedProperty(Protocol):
    """What a finder reads of a Shape Data property."""

    @property
    def value(self) -> str | None: ...


class SearchedShape(Protocol):
    """What a finder reads of a shape."""

    @property
    def ID(self) -> str | None: ...

    @property
    def text(self) -> str: ...

    @property
    def xml(self) -> Element: ...

    @property
    def master_page_ID(self) -> str | None: ...

    @property
    def master_shape_ID(self) -> str | None: ...

    @property
    def data_properties(self) -> Mapping[str, SearchedProperty]: ...


S = TypeVar("S", bound=SearchedShape)
S_co = TypeVar("S_co", bound=SearchedShape, covariant=True)


class Searched(Protocol[S_co]):
    """What a finder reads of the shapes it searches: a ``ShapeCollection``."""

    def __iter__(self) -> Iterator[S_co]: ...

    def matching_property(self, label: str, value: str | None = None) -> tuple[S_co, ...]: ...


def warn(finder: str, instead: str) -> None:
    """Warn that `finder` is removed in 1.0.0, naming what replaces it, from the caller's caller's line."""
    warnings.warn(f"{finder}() is deprecated and will be removed in 1.0.0. Use {instead}.", DeprecationWarning, stacklevel=3)


def first_by_id(shapes: Searched[S], shape_id: str) -> S | None:
    return next((shape for shape in shapes if shape_id == shape.ID), None)


def all_by_id(shapes: Searched[S], shape_id: str) -> list[S]:
    return [shape for shape in shapes if shape_id == shape.ID]


def first_by_attr(shapes: Searched[S], attr: str, attr_value: str) -> S | None:
    return next((shape for shape in shapes if str(shape.xml.attrib.get(attr)) == attr_value), None)


def all_by_master(shapes: Searched[S], master_page_id: str | None, master_shape_id: str | None) -> list[S]:
    return [shape for shape in shapes if shape.master_page_ID == master_page_id and shape.master_shape_ID == master_shape_id]


def first_by_text(shapes: Searched[S], text: str) -> S | None:
    return next((shape for shape in shapes if text in shape.text), None)


def all_by_text(shapes: Searched[S], text: str) -> list[S]:
    return [shape for shape in shapes if text in shape.text]


def all_by_regex(shapes: Searched[S], regex: str) -> list[S]:
    return [shape for shape in shapes if re.search(regex, shape.text)]


def first_by_property(shapes: Searched[S], label: str, value: str | None = None) -> S | None:
    # shape by shape, stopping at the first: matching_property reads every
    # shape's properties, which resolves the master of each
    for shape in shapes:
        found = shape.data_properties.get(label)
        if found is not None and (value is None or str(found.value) == value):
            return shape
    return None


def all_by_property(shapes: Searched[S], label: str, value: str | None = None) -> list[S]:
    return list(shapes.matching_property(label, value))
