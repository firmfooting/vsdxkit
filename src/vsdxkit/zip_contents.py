"""`VisioFile.zip_file_contents`, kept working over the package store until #91.

The old mapping held the package itself, keyed by a filesystem path no file was
ever at. The store holds it now, by part name, so this is only a translation:
it holds nothing, and every read and write lands in the store. A second copy
here would be a second writer, which is what #89 exists to remove.
"""

from __future__ import annotations

import io
import sys
from collections.abc import Iterable, Iterator, MutableMapping

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

from .package import PackageStore


class _WriteThroughBuffer(io.BytesIO):
    """A BytesIO that writes mutations back to the package store.

    The old zip_file_contents dict handed out its own BytesIO objects, so
    mutating one changed the package immediately. When those buffers are no
    longer backed by the dict, mutations are silent losses. This buffer
    restores that behaviour by writing back to the store when the buffer
    is mutated, ensuring that buf.write(...); buf.truncate() changes the
    package the way it did before.

    A write through the buffer replaces the part with bytes, detaching any
    promoted tree (the same way __setitem__ does), so a caller who holds the
    buffer and a removed tree keeps a working, detached tree.
    """

    def __init__(self, store: PackageStore, name: str, initial_bytes: bytes) -> None:
        super().__init__(initial_bytes)
        self._store = store
        self._name = name

    @override
    def write(self, __s):  # type: ignore[override]
        result = super().write(__s)
        self._store.write_bytes(self._name, self.getvalue())
        return result

    @override
    def writelines(self, __lines: Iterable[bytes]) -> None:  # type: ignore[override]
        result = super().writelines(__lines)
        self._store.write_bytes(self._name, self.getvalue())
        return result

    @override
    def truncate(self, __size: int | None = None) -> int:  # type: ignore[override]
        result = super().truncate(__size)
        self._store.write_bytes(self._name, self.getvalue())
        return result


def part_name_for_path(directory: str, path: str) -> str | None:
    """The part name the old pseudo-path spells, or None if it is not under `directory`."""
    prefix = directory + "/"
    if not path.startswith(prefix):
        return None
    return "/" + path[len(prefix) :]


class ZipFileContentsView(MutableMapping[str, io.BytesIO]):
    """The store, addressed by `f"{directory}/{member}"` and valued as `BytesIO`."""

    def __init__(self, store: PackageStore, directory: str) -> None:
        self._store = store
        self._directory = directory

    def _name(self, key: object) -> str | None:
        return part_name_for_path(self._directory, key) if isinstance(key, str) else None

    @override
    def __getitem__(self, key: str) -> io.BytesIO:
        name = self._name(key)
        try:
            data = None if name is None else self._store.read_bytes(name)
        except ValueError:  # not a part name, so not a part
            data = None
        if data is None:
            raise KeyError(key)
        assert name is not None  # name is guaranteed non-None if data is not None
        return _WriteThroughBuffer(self._store, name, data)

    @override
    def __setitem__(self, key: str, value: io.BytesIO) -> None:
        name = self._name(key)
        if name is None:
            raise ValueError(f"{key!r} is not under the package directory {self._directory!r}")
        self._store.write_bytes(name, value.getvalue())

    @override
    def __delitem__(self, key: str) -> None:
        name = self._name(key)
        if name is None:
            raise KeyError(key)
        try:
            self._store.remove(name)
        except ValueError as e:
            # not a valid part name, so not a part
            raise KeyError(key) from e

    @override
    def __contains__(self, key: object) -> bool:
        # asked of the store's index rather than through __getitem__, which
        # would serialise a promoted part to answer a yes/no question
        name = self._name(key)
        if name is None:
            return False
        try:
            return self._store.part(name) is not None
        except ValueError:
            return False

    @override
    def __iter__(self) -> Iterator[str]:
        # names() is a snapshot, so deleting while iterating is safe
        return (f"{self._directory}{name}" for name in self._store.names())

    @override
    def __len__(self) -> int:
        return len(self._store.names())
