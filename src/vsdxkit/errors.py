"""The exceptions this library raises.

Every error the library raises about a package, a document or an operation on
one derives from :class:`VsdxError`, so one ``except`` clause covers the
library and nothing else. Errors that report a mistake in the *arguments a
caller passed* are not in here: a ``TypeError`` for a ``None`` where a number
belongs, or a ``ValueError`` for a page dimension that is not positive, is a
plain builtin, because it says nothing about Visio, packages or documents.

Most classes keep a builtin base alongside :class:`VsdxError`. Those sites
raised the builtin before this module existed, and code catching it is entitled
to go on working; the second base is what keeps that true. The exception is
:class:`PackageError`, whose sites raised ``OSError`` (``PackageLimitError``)
or nothing at all. The hierarchy, with each builtin base in brackets::

   VsdxError
   +-- InvalidOperationError (ValueError)
   +-- NotFoundError (ValueError)
   |   +-- MissingPartError
   +-- PackageError
       +-- MalformedPackageError (ValueError)
       |   +-- PartParseError (xml.etree.ElementTree.ParseError)
       +-- PackageLimitError (OSError)

The guarantee covers what the library checks, which is not the whole Visio
schema. Opening a document validates the parts and attributes it reads on the
way in, so a package that is truncated, unparsable or missing what those reads
need is reported here; a package that is well-formed but breaks the schema
somewhere the library only reaches later can still surface a plain ``KeyError``
or ``AttributeError`` from the element it reads. Validating the schema up front
is separate work.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class VsdxError(Exception):
    """Base class for every error this library raises itself."""


class InvalidOperationError(VsdxError, ValueError):
    """The document cannot do what was asked of it in the state it is in.

    A drawing package asked to save under a ``.vsdm`` name, a lane label on a
    shape that has no heading, a shape appended to something that is not a
    group: the call is well-formed and the document is the reason it cannot
    happen.
    """


class NotFoundError(VsdxError, ValueError):
    """A named thing was looked for in the document and is not there."""


class MissingPartError(NotFoundError):
    """A part or element the document must contain to be read is absent.

    Visio parts are schema-driven, so a missing ``pages.xml``, master part or
    required element means the package is incomplete rather than that the
    caller asked for something optional. It is a :class:`NotFoundError` because
    that is still what happened: the thing is not there.
    """


class PackageError(VsdxError):
    """The package could not be read as a Visio package."""


class MalformedPackageError(PackageError, ValueError):
    """The package's own content breaks the format, so it cannot be read as it stands.

    Raised for:

    - an archive, or a member of one, that cannot be read or decoded;
    - a part that is not well-formed XML, as :class:`PartParseError`;
    - a part that declares an encoding that cannot be decoded;
    - a required element or attribute that is missing when the package is read;
    - a relationship target that is not a part name;
    - a ShapeSheet number that is not a number.

    Every one of these is a fault in the file, not in how the caller used the
    library. It is a ``ValueError`` because several of these sites raised one
    before the hierarchy existed, and code that caught that still catches this.
    """


class PartParseError(MalformedPackageError, ET.ParseError):
    """A part that is not well-formed XML, named, and catchable as every error it has been.

    Before the package store a malformed part reached the caller as the bare
    `ET.ParseError` the parser raised; callers of the package store's first
    cut catch it as `ValueError`, and the hierarchy's callers as
    `MalformedPackageError` or `VsdxError`.
    A caller should not have to know which release it runs against to catch a
    broken package, so this is all of them. It carries the parser's
    `position` and `code`, which say where in the part it broke.

    `msg` and `__str__` are set here, not inherited. `SyntaxError` formats
    itself from `msg`, and before Python 3.14 an instance built through this
    MRO never has `msg` set, so it printed as "None" instead of its message.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.msg = message

    @override
    def __str__(self) -> str:
        return self.msg


class PackageLimitError(PackageError, OSError):
    """A package violated a load limit: size, member count, ratio, names or duplicates.

    ``reason`` is a stable slug (``member_size``, ``total_size``,
    ``member_count``, ``compression_ratio``, ``duplicate_member``,
    ``member_name``, ``limits_file``) so callers can branch by failure mode.

    ``OSError`` stays a base because it was the only base before this module
    existed. ``PackageError`` is the one to catch in new code.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason: str = reason
