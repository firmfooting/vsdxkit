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
        """Refuse limits that could not be applied.

        A limit that is not a finite number, a count or size below 1, or a
        ratio below 1.0 raises :class:`ValueError`; a value that is not a
        number at all can raise :class:`TypeError` instead.
        """
        if not math.isfinite(float(self.max_ratio)):
            raise ValueError("max_ratio must be a finite number")
        for field_name in ("max_members", "max_member_size", "max_total_uncompressed"):
            value = getattr(self, field_name)
            if not math.isfinite(float(value)):
                raise ValueError(f"{field_name} must be a finite number")
            if value < 1:
                raise ValueError(f"{field_name} must be at least 1")
        if self.max_ratio < 1.0:
            raise ValueError("max_ratio must be at least 1.0")

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
