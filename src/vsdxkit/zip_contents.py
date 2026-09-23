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
from typing import TYPE_CHECKING

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

if TYPE_CHECKING:
    # annotations only: typing_extensions grew Buffer in 4.6, and the declared
    # floor is 4.4, so importing it at runtime would break an install the
    # package metadata allows
    if sys.version_info >= (3, 12):
        from collections.abc import Buffer
    else:
        from typing_extensions import Buffer

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

    `getbuffer()` is the one mutation this cannot see: a write through the
    memoryview it returns lands in the buffer's memory without calling any
    method here. So an exported buffer records what it held when it was first
    exported and registers with its view, and `ZipFileContentsView.sync()`
    writes whatever changed since, which `VisioFile.save_vsdx` does before it
    writes anything. The buffer holds the view's registry rather than the
    view, so a buffer a caller keeps does not keep the view alive.
    """

    def __init__(self, store: PackageStore, name: str, initial_bytes: bytes, exports: dict[int, _WriteThroughBuffer]) -> None:
        super().__init__(initial_bytes)
        self._store = store
        self._name = name
        self._exports = exports
        # what the store last agreed this buffer held, set on first export;
        # None means no memoryview has ever been handed out
        self._baseline: bytes | None = None

    def _write_through(self) -> None:
        value = self.getvalue()
        self._store.write_bytes(self._name, value)
        if self._baseline is not None:
            # the store has these bytes now, so a later sync has nothing of
            # this buffer's to write and must not write them over whatever the
            # store is given after this
            self._baseline = value

    @override
    def write(self, buffer: Buffer, /) -> int:
        result = super().write(buffer)
        self._write_through()
        return result

    @override
    def writelines(self, lines: Iterable[Buffer], /) -> None:
        result = super().writelines(lines)
        self._write_through()
        return result

    @override
    def truncate(self, size: int | None = None, /) -> int:
        result = super().truncate(size)
        self._write_through()
        return result

    @override
    def getbuffer(self) -> memoryview:
        view = super().getbuffer()
        if self._baseline is None:
            # only the first export sets the baseline and registers: a second
            # export while an earlier memoryview still has unsynced edits must
            # not hide them, and must not register the same buffer twice
            self._baseline = self.getvalue()
            self._exports[id(self)] = self
        return view

    def sync(self) -> None:
        """Write memoryview edits made since the baseline to the store, if the part is still there.

        A part removed since this buffer was read stays removed: the old dict
        dropped its buffer on delete, so an edit to it never reached a save,
        and bringing a deleted page's part back as an orphan would be worse.
        The view only calls this on an open buffer; a closed one has nothing
        left to read.
        """
        if self._baseline is None:
            return
        value = self.getvalue()
        if value == self._baseline:
            return
        self._baseline = value
        if self._store.part(self._name) is not None:
            self._store.write_bytes(self._name, value)


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
        # buffers a caller has taken a memoryview of, by id so each is held
        # once however often it is exported. Held strongly: the commonest edit
        # is `view[k].getbuffer()[i] = x`, whose buffer nothing else keeps
        # alive until save, and the old dict kept every buffer it handed out
        # for the life of the document anyway. They stay registered after a
        # sync, so a memoryview a caller still holds is synced again next time.
        self._exports: dict[int, _WriteThroughBuffer] = {}

    def sync(self) -> None:
        """Write to the store every change made through a `getbuffer()` memoryview.

        The old dict handed out its own buffers, so a write through
        `buf.getbuffer()` changed the package. A memoryview write calls no
        method that could forward it, so it is written here instead, and
        `VisioFile.save_vsdx` calls this before it writes anything. The cost
        is ordering: an exported buffer's edit, synced at save, wins over a
        store write to the same part made after the edit, where the old dict
        would have kept whichever came last.
        """
        # a snapshot, because a closed buffer is dropped while iterating: it
        # can take no more edits, and its bytes can no longer be read
        for key, buffer in list(self._exports.items()):
            if buffer.closed:
                del self._exports[key]
            else:
                buffer.sync()

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
        return _WriteThroughBuffer(self._store, name, data, self._exports)

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
