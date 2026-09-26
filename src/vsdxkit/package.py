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
    max_member_size: int = 64 * 1024 * 1024
    max_total_uncompressed: int = 256 * 1024 * 1024
    max_ratio: float = 100.0

    def __post_init__(self) -> None:
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
