# Recorded Visio observations

One JSON file per fixture, recording what a real Microsoft Visio 16.0 reported
when it opened **the file vsdxkit wrote from that fixture**: every page, every
shape id including group members, the cells that place each shape, and every glue
record. They are the far half of a differential oracle — the near half is
`tests/helpers/visio_observation.py`, which derives the same account from a
package's own XML.

The distinction matters more than it looks. A recording of a fixture *as it sits
in git* would be worthless as a regression gate: the bytes are frozen, so the
reader can only ever return what it returned at record time, and the comparison
would prove that the XML reader still reads the same way — nothing at all about
what the library writes. Recording the round-tripped output instead means replay
re-runs today's writer and compares its result to what Visio vouched for.

Regenerate with, on Windows with desktop Visio:

```console
$ python tools/visio_verify.py record tests/test4_connectors.vsdx
RECORD test4_connectors.vsdx (roundtrip) -> tests/fixtures/visio_observations/test4_connectors.json
```

`--transform none` records the fixture itself rather than our output. That is
occasionally useful for asking Visio about a file we did not write, but such a
recording is not a regression gate, for the reason below.

## Why record at all

The oracle problem here is real: for a given `.vsdx` there is no independent
statement of what it ought to contain, and the library's own tests can only
confirm that vsdxkit wrote what vsdxkit meant to write. Visio is the one
authority that can disagree with us, and its disagreements are silent ones
(see "When a change needs Visio" in CONTRIBUTING.md for what that looks like).

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

- the input fixture changes, so replay reports `STALE` and fails. Re-record it.
  The hash is of the *input*, not of the file Visio opened: the output is
  supposed to change when the writer changes, and that is the thing being
  checked.
- the fixture is deleted, so replay reports `ORPHAN` and fails. Delete the
  recording too.
- the schema version moves, so the recording is refused rather than guessed at.

None of those are allowed to pass quietly. A harness believed to be checking
something it is not is worse than no harness, because the green tick is spent on
it.

Do not hand-edit these files. A recording that says what someone wished Visio
had done is not evidence of anything.

## What is compared, and what is not

Compared: page count and order, page names, shape ids per page, each shape's
enclosing group, every glue record, and the **placement cells** — `PinX`,
`PinY`, `Width`, `Height`, `Angle`, `LocPinX`, `LocPinY`, `FlipX`, `FlipY`, and
on a 1-D shape `BeginX`, `BeginY`, `EndX`, `EndY`.

Not compared:

- **Shape names.** Visio synthesises `Sheet.5` for a shape the package never
  named, so comparing names would report a difference on nearly every shape and
  bury the real ones. Names are recorded for the failure message only.
- **Visio's `ResultIU`.** Recorded, printed in failure messages, and left
  uncompared — see below.
- **Where a glued connector actually sits.** Every placement cell on a dynamic
  connector is a formula — `_WALKGLUE(...)`, `GUARD((BeginX+EndX)/2)` — inherited
  from the same master on both sides, so all thirteen are compared as text and
  none as a number. Move such a connector and this comparison does not notice.
  Its endpoints are still covered by the glue records, which is a weaker claim
  than the one made for every other shape.
- **Text, colour and everything else in the ShapeSheet.** Not yet extracted.
  Whether a shape *says* what it should say is still checked by eye. See the
  open issues on extending the observation.

The narrower claim is the honest one: these recordings say Visio agrees about
the structure of these documents and about where their shapes sit, not that it
renders them correctly.

## Formula and result

Each recorded cell carries two numbers, because a cell is two facts.
`Cell.FormulaU` is what the cell says; `Cell.ResultIU` is what that evaluates to,
in internal units. A package that writes a correct-looking formula in the wrong
unit differs only in the result; a package whose formula we rewrote but which
still evaluates the same differs only in the formula. Recording one of the two
would hide half the bugs.

Only the formula is compared. The package side has no evaluator: the `V`
attribute next to a formula in the XML is a cache written by whoever last opened
the file, and vsdxkit never recomputes it, so comparing it against what Visio
evaluated would turn someone else's stale cache into a failure of ours. The
result is recorded for the failure message — a message that says `PinX` changed
and cannot say where the shape ended up is half a message — and for a future
comparison of one Visio version against another, where both sides really do
evaluate.

The one place the result is used as evidence is a formula that is nothing but a
literal. There the two sides spell the same fact differently — the package
writes `1.332677148526936` in internal units and Visio renders the same cell as
`33.849999572584 mm` — and a literal formula evaluates to itself, so its result
*is* that constant in internal units. No unit parser is needed, and none exists.

Constants are compared to a tolerance of 1e-9, relative or absolute, defined
once as `PLACEMENT_TOLERANCE` in `tests/helpers/visio_observation.py`. An exact
comparison on a double that has been through inches to millimetres and back
fails on arithmetic that is correct, and a check that cries wolf gets switched
off.
