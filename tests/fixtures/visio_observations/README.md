# Recorded Visio observations

One JSON file per fixture, recording what a real Microsoft Visio 16.0 reported
when it opened that fixture: every page, every shape id including group members,
every glue record. They are the far half of a differential oracle — the near
half is `tests/helpers/visio_observation.py`, which derives the same account
from the package's own XML.

Regenerate with, on Windows with desktop Visio:

```console
$ python tools/visio_verify.py record tests/test4_connectors.vsdx
```

## Why record at all

The oracle problem here is real: for a given `.vsdx` there is no independent
statement of what it ought to contain, and the library's own tests can only
confirm that vsdxkit wrote what vsdxkit meant to write. Visio is the one
authority that can disagree with us, and the interesting disagreements are
silent — a package declaring four shapes opens as three, no error, no repair
prompt, and it saves again quite happily.

Visio is also slow, stateful, Windows-only and licensed, and CI is none of those
things. So the oracle is consulted rarely and its answers are kept. That splits
the checking into layers by how much each costs and what each can prove:

| Layer | Runs | Oracle | Catches |
| --- | --- | --- | --- |
| The suite | everywhere, always | the library's own expectations | what we know to assert |
| `PackageManifest` | everywhere, always | a parser that does not share ours | round-trip drift in the bytes and the canonical XML |
| Replay of this corpus | everywhere, always | a recorded Visio | a change to what we write that Visio would reject |
| `visio_verify.py check` | one Windows desktop, by hand | Visio, live | everything above, plus a change in Visio itself |

Only the last row can observe Visio. The third row is what makes the last one
worth the trouble: it is how one afternoon's Visio run keeps paying out on every
CI run afterwards.

## What a recording is worth

A recording describes one exact file and stores its SHA-256. It is evidence, and
it expires:

- the fixture changes → replay reports `STALE` and **fails**. Re-record it.
- the fixture is deleted → replay reports `ORPHAN` and **fails**. Delete the
  recording too.
- the schema version moves → the recording is refused, not guessed at.

None of those are allowed to pass quietly. A harness believed to be checking
something it is not is worse than no harness, because the green tick is spent on
it.

Do not hand-edit these files. A recording that says what someone wished Visio
had done is not evidence of anything.

## What is compared, and what is not

Compared: page count and order, page names, shape ids per page, each shape's
enclosing group, and every glue record.

Not compared:

- **Shape names.** Visio synthesises `Sheet.5` for a shape the package never
  named, so comparing names would report a difference on nearly every shape and
  bury the real ones. Names are recorded for the failure message only.
- **Geometry, text, cell values and formatting.** Not yet extracted. Whether a
  shape is where it should be, and says what it should say, is still checked by
  eye. See the open issues on extending the observation.

The narrower claim is the honest one: these recordings say Visio agrees about
the *structure* of these documents, not that it renders them correctly.
