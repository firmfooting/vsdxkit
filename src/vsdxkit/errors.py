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
or nothing at all.
"""

from __future__ import annotations


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
    """A part of the package does not hold what the format requires.

    Bytes that are not well-formed XML, or a ShapeSheet cell holding something
    that is not the number its cell has to be.
    """


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
        self.reason = reason


class VisioFileNotOpen(InvalidOperationError):
    """The document is closed, so the change this call would make can never be saved."""
