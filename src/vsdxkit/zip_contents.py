"""`VisioFile.zip_file_contents`, kept working over the package store until #91.

The old mapping held the package itself, keyed by a filesystem path no file was
ever at. The store holds it now, by part name, so this is only a translation:
it holds nothing, and every read and write lands in the store. A second copy
here would be a second writer, which is what #89 exists to remove.
"""

from __future__ import annotations

import io
from collections.abc import Iterator, MutableMapping
from typing import override

from .package import PackageStore


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
        return io.BytesIO(data)

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
        self._store.remove(name)

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
