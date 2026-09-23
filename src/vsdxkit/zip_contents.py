"""`VisioFile.zip_file_contents`, kept working over the package store until #91.

The old mapping held the package itself, keyed by a filesystem path no file was
ever at. The store holds it now, by part name, so this is only a translation:
it holds nothing, and every read and write lands in the store. A second copy
here would be a second writer, which is what #89 exists to remove. The one
buffer per member it does keep is only ever handed out while it holds exactly
the part the store has.
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

from .package import BytesPart, PackageStore, PartValue, XmlPart


class _WriteThroughBuffer(io.BytesIO):
    """A BytesIO that writes mutations back to the package store.

    The old zip_file_contents dict handed out its own BytesIO objects, so
    mutating one changed the package immediately. When those buffers are no
    longer backed by the dict, mutations are silent losses. This buffer
    restores that behaviour by writing back to the store when the buffer
    is mutated, ensuring that buf.write(...); buf.truncate() changes the
    package the way it did before.

    A write through the buffer goes to the store the way `__setitem__` does,
    through `PackageStore.write_bytes_keeping_tree`: a parsed part keeps the
    tree the document is editing. Replacing it on every write would detach
    that tree, and the document's later edits would go into a tree nothing
    saves; a buffer read and truncated at its end would be enough to do it.

    Bytes that do not parse are held back rather than written over a parsed
    part. They are usually a step on the way: `seek(0); write(new);
    truncate()` with new XML shorter than the old calls `write()` while the
    buffer holds the new head with the old tail behind it, and writing that
    would turn the part into bytes, leaving the `truncate()` to put valid XML
    into a part the document's tree is no longer. So the buffer registers as
    pending with its view instead, and the store keeps the tree; until then a
    read of the member sees the tree, not these bytes. The next write from
    this buffer that parses lands in the tree as usual and clears it. If none
    comes, the bytes are the caller's last word, and they replace the part
    when the buffer is closed or at `ZipFileContentsView.sync()`, which
    `VisioFile.save_vsdx` runs before it writes anything, so the package
    saves what the caller left, as it did before the store.

    `getbuffer()` is the one mutation this cannot see: a write through the
    memoryview it returns lands in the buffer's memory without calling any
    method here. So an exported buffer records what it held when it was first
    exported and registers with its view, and `ZipFileContentsView.sync()`
    writes whatever changed since, which `VisioFile.save_vsdx` does before it
    writes anything. The buffer holds the view's registry rather than the
    view, so a buffer a caller keeps does not keep the view alive.

    Every write this buffer makes to the store also makes it the view's live
    buffer for its part, because the part the store now holds is exactly
    these bytes: the next read of the key has nothing newer to snapshot, and
    handing back this buffer is what keeps a second holder's edits from
    being written over by a stale copy.

    A buffer is bound to the part object it was made from, and writes through
    only while the store still holds that object. The old dict detached a
    BytesIO the moment its key was deleted or rebound, so a later write to it
    changed nothing; writing it to the store would bring a deleted member
    back, or put stale bytes over the value that replaced them. So anything
    that replaces the part -- `view[key] = ...`, `del view[key]`, a store
    write, a new tree, another buffer's write that becomes a new part --
    detaches this one for good, and it carries on as a plain in-memory
    BytesIO. Its own writes re-bind it to the part they leave in the store,
    and so does a promotion of its part, which changes how the store holds
    the part and not what it holds.

    The part object alone cannot see every replacement: new XML assigned to
    a parsed part goes into its tree, and the part object stays. So the
    buffer is also bound to its view's generation for the name, which
    `view[key] = ...` and `del view[key]` bump, and it writes through only
    while both still match. Its own writes do not bump it. Two snapshots of
    one parsed part therefore both stay bound: neither rebinds the member,
    each write lands in the tree in turn, and the last of them to write wins,
    the documented limitation.
    """

    def __init__(
        self,
        store: PackageStore,
        name: str,
        part: PartValue,
        initial_bytes: bytes,
        exports: dict[int, _WriteThroughBuffer],
        live: dict[str, _WriteThroughBuffer],
        pending: dict[int, _WriteThroughBuffer],
        generations: dict[str, int],
    ) -> None:
        super().__init__(initial_bytes)
        self._store = store
        self._name = name
        # the part this buffer speaks for, or None once it is detached
        self._bound: PartValue | None = part
        self._exports = exports
        self._live = live
        self._pending = pending
        self._generations = generations
        # the view's generation for the name when this buffer was bound; a
        # different one means the member was rebound or deleted through the
        # view since
        self._generation = generations.get(name, 0)
        # what the store last agreed this buffer held, set on first export;
        # None means no memoryview has ever been handed out
        self._baseline: bytes | None = None

    def is_bound_to(self, part: PartValue) -> bool:
        """Whether this buffer speaks for exactly this part object, under the name's current generation."""
        return self._bound is part and self._generation == self._generations.get(self._name, 0)

    def _attached(self) -> bool:
        """Whether the store still holds the part this buffer is bound to, detaching it for good if not."""
        bound = self._bound
        if bound is None:
            return False
        held = self._store.part(self._name)
        if self._generation == self._generations.get(self._name, 0):
            if held is bound:
                return True
            if isinstance(held, XmlPart) and held.promoted_from is bound:
                self._bound = held
                return True
        self._bound = None
        # a detached buffer has nothing left to sync or settle, and must not
        # be handed out as the member's buffer again
        self._exports.pop(id(self), None)
        self._pending.pop(id(self), None)
        if self._live.get(self._name) is self:
            del self._live[self._name]
        return False

    def _store_value(self, value: bytes, *, final: bool) -> bool:
        """Write `value` as this buffer's part, or hold it back and return False.

        Only bytes that do not parse, bound for a parsed part, are held back,
        and only while more writes may follow (`final` is False).
        """
        if not self._store.write_bytes_keeping_tree(self._name, value, refuse_unparseable=not final):
            self._pending[id(self)] = self
            return False
        self._pending.pop(id(self), None)
        part = self._store.part(self._name)
        self._bound = part
        # a write of this buffer's own does not bump the generation, so this
        # changes nothing today; it keeps the buffer bound if that ever changes
        self._generation = self._generations.get(self._name, 0)
        if isinstance(part, BytesPart):
            self._live[self._name] = self
        else:
            # a parsed part kept its tree, which is authoritative and is read
            # as a fresh snapshot every time, so no buffer is live for it
            self._live.pop(self._name, None)
        return True

    def _write_through(self, *, final: bool = False) -> None:
        if not self._attached():
            return
        value = self.getvalue()
        if self._store_value(value, final=final) and self._baseline is not None:
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
    def close(self) -> None:
        # a closed buffer can be neither written nor read again, so bytes it
        # held back are as final as they will ever be
        if not self.closed and id(self) in self._pending:
            self._write_through(final=True)
        super().close()

    @override
    def getbuffer(self) -> memoryview:
        view = super().getbuffer()
        if self._baseline is None and self._attached():
            # only the first export sets the baseline and registers: a second
            # export while an earlier memoryview still has unsynced edits must
            # not hide them, and must not register the same buffer twice
            self._baseline = self.getvalue()
            self._exports[id(self)] = self
        return view

    def sync(self) -> None:
        """Write memoryview edits made since the baseline to the store, if this buffer is still bound.

        A part removed or replaced since this buffer was read stays as it is
        now: the old dict dropped its buffer on delete or rebind, so an edit
        to it never reached a save, and bringing a deleted page's part back as
        an orphan would be worse. The view only calls this on an open buffer;
        a closed one has nothing left to read.
        """
        if self._baseline is None or not self._attached():
            return
        value = self.getvalue()
        if value == self._baseline:
            return
        self._baseline = value
        self._store_value(value, final=True)

    def settle(self) -> None:
        """Write bytes held back because they did not parse, if this buffer is still bound.

        Called by the view's sync, when no later write can come before the
        save: the bytes are the caller's last word, so they replace the part
        even though that detaches its tree.
        """
        if id(self) in self._pending:
            self._write_through(final=True)


def part_name_for_path(directory: str, path: str) -> str | None:
    """The part name the old pseudo-path spells, or None if it is not under `directory`."""
    prefix = directory + "/"
    if not path.startswith(prefix):
        return None
    return "/" + path[len(prefix) :]


class ZipFileContentsView(MutableMapping[str, io.BytesIO]):
    """The store, addressed by `f"{directory}/{member}"` and valued as `BytesIO`.

    The old dict returned the same BytesIO every time a key was read, so two
    holders of one member edited one buffer and both edits survived. A fresh
    snapshot per read would break that: the second holder's write-through
    would put back the bytes the first holder had just changed. So the view
    keeps one live buffer per member and returns it for as long as the store
    still holds the very part that buffer was made from. When anything else
    replaces or removes the part -- `view[key] = ...`, a store write, a
    `VisioFile` setter -- the buffer no longer describes the part, and the
    next read makes a new one from what the store holds now. The old buffer
    is detached and writes nothing more to the store, the way a BytesIO the
    old dict had let go of changed nothing (see `_WriteThroughBuffer`).

    A write to a part that has been parsed lands in its tree rather than
    replacing it (see `PackageStore.write_bytes_keeping_tree`), because the
    document holds that tree and goes on editing it: the old
    `xml_to_file(page.xml, page.filename, vis.zip_file_contents)` idiom, or
    new XML for the page, must leave `page.xml` the tree the package saves.

    Known limitation, left for #91 to delete along with the view: a part that
    has been parsed (an `XmlPart`) is read as a fresh snapshot every time,
    because its tree is authoritative and can change without the view seeing
    it. Two holders of such a part's buffers are back to one snapshot each,
    both stay bound, and the second write-through wins -- unless one of them
    holds bytes back because they do not parse: those are written at sync or
    close, so they win over a later valid write from the other. An assignment or
    delete through the view does detach both, as it would have detached a
    dict value. Likewise `view[key] = buf` stores the bytes of `buf` rather
    than `buf` itself, so a later read does not return the object assigned,
    and a later write to `buf` does not reach the store.
    New XML written to a parsed part replaces its tree's root, so an element
    a caller took from the old root belongs to no part any more. Bytes that
    do not parse, written through a buffer of a parsed part, reach the store
    only when the buffer is closed or synced, so a read in between sees the
    tree (see `_WriteThroughBuffer`).
    """

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
        # the one buffer each member is read as, by part name. Held strongly,
        # like the old dict held its buffers, so `view[k].seek(0);
        # view[k].write(...)` edits one buffer. An entry no longer bound to
        # the part the store holds is stale and is replaced on the next read
        # of that member.
        self._live: dict[str, _WriteThroughBuffer] = {}
        # buffers holding back bytes that do not parse from a parsed part, by
        # id. Held strongly for the reason exports are: `view[k].write(...)`
        # leaves nothing else holding the buffer whose bytes sync must write.
        self._pending: dict[int, _WriteThroughBuffer] = {}
        # how often each name has been rebound or deleted through the view.
        # A buffer bound under an older generation is detached: assigning new
        # XML to a parsed part keeps the part object, so the part alone cannot
        # tell a buffer read before the assignment that it no longer speaks
        # for the member
        self._generations: dict[str, int] = {}

    def sync(self) -> None:
        """Write to the store every change made through a `getbuffer()` memoryview.

        The old dict handed out its own buffers, so a write through
        `buf.getbuffer()` changed the package. A memoryview write calls no
        method that could forward it, so it is written here instead, and
        `VisioFile.save_vsdx` calls this before it writes anything. The cost
        is ordering: an exported buffer's edit, synced at save, wins over a
        store write to the same part made after the edit, where the old dict
        would have kept whichever came last. A buffer detached since it was
        exported is not written: its member has been deleted or replaced.

        It also writes the bytes any buffer held back because they did not
        parse (see `_WriteThroughBuffer`): nothing more can arrive before the
        save, so what the buffer holds is what the caller left the member as.
        """
        # snapshots, because entries are dropped while iterating: a closed
        # buffer can take no more edits and can no longer be read, and a
        # buffer that syncs or settles leaves the pending registry
        for key, buffer in list(self._exports.items()):
            if buffer.closed:
                self._exports.pop(key, None)
            else:
                buffer.sync()
        for key, buffer in list(self._pending.items()):
            if buffer.closed:
                self._pending.pop(key, None)
            else:
                buffer.settle()

    def copy(self) -> dict[str, io.BytesIO]:
        """A plain dict of every member and the buffer a read of it returns now.

        The old `zip_file_contents` was a dict, so `copy()` worked on it, and
        `MutableMapping` does not supply one. The copy is shallow, as the
        dict's was: it is a dict of its own, so adding or deleting keys in it
        leaves the package alone, but its values are the view's buffers, and
        a write to one of those still writes through while it is bound.
        """
        return dict(self)

    def _name(self, key: object) -> str | None:
        return part_name_for_path(self._directory, key) if isinstance(key, str) else None

    @override
    def __getitem__(self, key: str) -> io.BytesIO:
        name = self._name(key)
        try:
            part = None if name is None else self._store.part(name)
        except ValueError:  # not a part name, so not a part
            part = None
        if part is None:
            raise KeyError(key)
        assert name is not None  # name is guaranteed non-None if part is not None
        if not isinstance(part, BytesPart):
            # a promoted tree is authoritative and changes without telling
            # the view, so a cached buffer could hold bytes the tree has
            # moved past; this is the documented limitation
            self._live.pop(name, None)
            return self._new_buffer(name, part, part.current_bytes())
        cached = self._live.get(name)
        if cached is not None and cached.is_bound_to(part) and not cached.closed:
            return cached
        buffer = self._new_buffer(name, part, part.data)
        self._live[name] = buffer
        return buffer

    def _new_buffer(self, name: str, part: PartValue, data: bytes) -> _WriteThroughBuffer:
        return _WriteThroughBuffer(self._store, name, part, data, self._exports, self._live, self._pending, self._generations)

    @override
    def __setitem__(self, key: str, value: io.BytesIO) -> None:
        name = self._name(key)
        if name is None:
            raise ValueError(f"{key!r} is not under the package directory {self._directory!r}")
        self._store.write_bytes_keeping_tree(name, value.getvalue())
        self._rebound(name)
        # the cached buffer no longer holds what the part does, and the new
        # part detaches it; the binding check would catch that on the next
        # read, but dropping it here lets its bytes go now
        self._live.pop(name, None)

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
        self._rebound(name)
        self._live.pop(name, None)

    def _rebound(self, name: str) -> None:
        """Detach every buffer handed out for `name` before now, the way rebinding a dict key let its value go."""
        self._generations[name] = self._generations.get(name, 0) + 1

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
