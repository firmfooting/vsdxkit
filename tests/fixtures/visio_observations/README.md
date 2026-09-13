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
enclosing group, every glue record, and, for the **placement cells** — `PinX`,
`PinY`, `Width`, `Height`, `Angle`, `LocPinX`, `LocPinY`, `FlipX`, `FlipY`, and
on a 1-D shape `BeginX`, `BeginY`, `EndX`, `EndY` — three things: that both sides
have the cell, that both hold the same *kind* of formula (a literal or an
expression), and, where it is a literal, its value as a number.

Across the recorded corpus that is 1371 cell pairs checked for presence and kind,
803 of them compared as numbers.

Not compared:

- **Shape names.** Visio synthesises `Sheet.5` for a shape the package never
  named, so comparing names would report a difference on nearly every shape and
  bury the real ones. Names are recorded for the failure message only.
- **The text of an expression.** The remaining 568 pairs. Recorded, printed, not
  compared — see "Formula and result" below. A green replay says nothing about
  whether an expression still reads the way it did.
- **Visio's `ResultIU`.** Recorded, printed in failure messages, and left
  uncompared — see below.
- **Where a glued connector actually sits.** Every placement cell on a dynamic
  connector is an expression — `_WALKGLUE(...)`, `GUARD((BeginX+EndX)/2)` — so
  none of its thirteen is compared as a number. Move such a connector and this
  does not notice. Its endpoints are still covered by the glue records, which is
  a weaker claim than the one made for every other shape.
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

### Why an expression's text is not compared

`Cell.FormulaU` is Visio's *rendering* of a formula, not the text the file holds.
Visio parses the stored formula and prints it back from its own parse tree, and
on correct files the two do not match. Measured against Visio 16.0 over this
corpus, four ways:

| stored in the package | rendered by Visio | |
| --- | --- | --- |
| `GUARD(0DA)` | `GUARD(0 deg)` | unit spelling |
| `GUARD(0.19685039370079DL)` | `GUARD(5.0000000000001 mm)` | unit conversion, with its own rounding |
| `Width*0.499973064698594` | `Width*0.49997306469859` | reprinted to 14 digits |
| `Height*0.0` | `Height*0` | zero normalised |
| `Sheet.5!Width*0.5` | `Sheet.7!Width*0.5` | reference rebound to the instance |

The last one settles it. The package reports the formula as the master stores it,
naming shapes inside the master; Visio renders it resolved against the instance
on the page. Those are two different sentences that mean the same thing, so
comparing them as text is comparing the wrong pair — and rewriting one into the
other would mean mapping master shape ids to page shape ids through Visio's own
shape-naming rules.

Normalising until the rest matched would mean reimplementing Visio's formula
printer from examples. That is unbounded, and every rule guessed at is somewhere
a real difference can hide, which is the thing this whole harness is built to
avoid. So both spellings are recorded and printed and neither is trusted.

What survives is not nothing. A cell that changes from an expression to a literal,
or the reverse, is still reported: Visio's renderer never turns one into the
other, so that comparison is sound. It is the case the issue behind these cells
called out — a formula replaced by the number it happened to evaluate to has
stopped tracking what it referred to, and the shape moves the next time that
changes.

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
