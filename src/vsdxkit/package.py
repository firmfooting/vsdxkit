"""The limits a package is read under.

:class:`PackageLimits` caps what :meth:`vsdxkit.document.Document.open` reads
from an archive, so a hostile or accidental file is refused before it can
exhaust memory. The store that holds a document's parts once it is open is
internal.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from vsdxkit.errors import PackageLimitError

# --------------------------------------------------------------------------
# load limits
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PackageLimits:
    """Conservative caps applied while loading a package from disk.

    The defaults suit documents from unknown sources: a hostile or accidental
    archive is rejected well before it can exhaust process memory. Even at the
    caps the loader materialises at most ``max_total_uncompressed`` bytes
    (256 MiB by default); callers loading larger trusted documents should raise
    the caps explicitly via ``Document.open(filename, limits=PackageLimits(...))``
    or a JSON file passed as ``limits_path`` with the same keys.

    A count or size field below 1, or ``max_ratio`` below 1.0, raises
    :class:`ValueError`, as does one that is not finite. A field that is not
    a number raises :class:`TypeError`: ``None``, a list, a string (a numeric
    one such as ``"5"`` included) and a ``bool``, which is an ``int`` but
    never a count or a size.
    """

    max_members: int = 512
    """The most entries the archive may hold, directory entries included; 512 by default. A save of more parts is refused too."""
    max_member_size: int = 64 * 1024 * 1024
    """The most bytes one member may hold uncompressed; 64 MiB by default. A save is held to it too."""
    max_total_uncompressed: int = 256 * 1024 * 1024
    """The most bytes the members may hold together, uncompressed; 256 MiB by default. A save is held to it too."""
    max_ratio: float = 100.0
    """The most one member may expand by, its uncompressed size over its compressed size; 100 by default.

    A save stores a member uncompressed rather than compress it past this
    ratio or the default, whichever is lower.
    """

    def __post_init__(self) -> None:
        """Refuse limits that could not be applied; see the class docstring for what is raised."""
        for field_name in ("max_members", "max_member_size", "max_total_uncompressed", "max_ratio"):
            value = getattr(self, field_name)
            if isinstance(value, (bool, str)):
                raise TypeError(f"{field_name} must be a number, not {value!r}")
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"{field_name} must be a finite number")
            minimum = "1.0" if field_name == "max_ratio" else "1"
            if number < 1:
                raise ValueError(f"{field_name} must be at least {minimum}")

    @classmethod
    def from_json_file(cls, path: str) -> PackageLimits:
        """Load limits from a JSON object; unusable files are PackageLimitError, not surprises."""
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError) as error:  # ValueError covers json.JSONDecodeError
            raise PackageLimitError("limits_file", f"unable to read limits file {path}: {error}") from error
        if not isinstance(payload, dict):
            raise PackageLimitError("limits_file", f"limits file {path} must contain a JSON object")
        known = {"max_members", "max_member_size", "max_total_uncompressed", "max_ratio"}
        unknown = sorted(set(payload) - known)
        if unknown:
            raise PackageLimitError("limits_file", f"unknown limit keys in {path}: {', '.join(unknown)}")
        try:
            return cls(**payload)
        except (TypeError, ValueError) as error:
            raise PackageLimitError("limits_file", f"invalid limits in {path}: {error}") from error
