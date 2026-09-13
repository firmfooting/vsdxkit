# Checking `dave-howard/vsdx` for fixes worth taking

vsdxkit began as a fork of [`dave-howard/vsdx`](https://github.com/dave-howard/vsdx)
and is no longer downstream of it. We do not track that repository, we owe it
nothing, and no release of ours waits on one of theirs. What remains is a shared
ancestry: the same module layout, and a lot of the same code under the 0.x API.
If Dave fixes a bug in that shared code, the fix may apply here too, and taking
it is cheaper than finding the same bug ourselves.

## Occasionally, not quarterly

[Issue #80](https://github.com/firmfooting/vsdxkit/issues/80) asked for a
quarterly reconciliation. That was written while this was still a fork, and a
calendar cadence is the wrong shape now:

- Upstream is quiet. Its last commit is `6703e6c`, the v0.6.1 release of
  2026-01-04, eight months before this page was written, with nothing since.
  Three of four quarterly checks would find an empty range.
- We are diverging on purpose. The 1.0 refactor renames the whole public object
  model, so the further we go, the less of an upstream patch applies verbatim
  and the more each check costs to evaluate.
- A recurring task that almost always finds nothing stops being performed, and
  then stops being trusted when it is.

Check when there is a reason to:

- upstream publishes a release or a burst of commits;
- a bug is reported here that smells like one they may already have hit;
- before a major release of ours, as a cheap last look.

## The sync point

The last upstream commit considered is recorded here, and nowhere else.

| Checked | Upstream HEAD | New commits reviewed | Taken |
|---|---|---|---|
| 2026-09-13 | `6703e6c` | 0 | none |

That first check ran while this page was being written. `6703e6c` is both
upstream's current HEAD and an ancestor of our `main`, so everything upstream
has published is already in this history, inherited through the fork rather
than merged in.

## The procedure

### 1. Fetch

Upstream is not a remote in a fresh clone. Add it as a read-only one:

```bash
git remote add upstream https://github.com/dave-howard/vsdx.git
git fetch upstream
```

`master` is upstream's only branch, and it publishes no tags: releases are
marked by commit message (`Release v0.6.1 - ...`). Do not go looking for
`upstream/main`.

### 2. Review the range

```bash
git log --oneline 6703e6c..upstream/master
git diff --stat 6703e6c..upstream/master
```

Replace `6703e6c` with whatever the table above records. An empty range ends the
check: update the `Checked` date, note zero commits, stop.

Read the diff, not just the subjects. Worth taking:

- bug fixes in package handling, XML parsing or formula generation, the code we
  still share;
- correctness fixes with a reproducer we can turn into a test.

Not worth taking:

- anything touching the public API surface, which 1.0 is rewriting anyway;
- packaging, CI and tooling, where upstream still uses `setup.py` and
  `requirements.txt` against our uv and locked `pyproject.toml`, and nothing
  transfers;
- features. A feature we want is one we design for our object model, not a
  patch we import.

### 3. Take what is worth taking

The module layout still lines up, with `vsdx/pages.py`, `vsdx/shapes.py`,
`vsdx/connectors.py` and the rest on both sides, so a cherry-pick often applies:

```bash
git switch -c fix/<short-name> origin/main
git cherry-pick -x <sha>
```

`-x` appends the source sha to the commit message, which keeps the origin
visible while you work on the branch. It does not reach `main`; see the PR step
below for where the credit has to go.

Expect conflicts inside those files: contents have diverged heavily even where
paths have not. When a cherry-pick fights back, abort it and write the fix
ourselves against our code. The upstream commit is then a reference, and belongs
in the commit message as a link rather than as a parent.

Either way the change lands through a normal PR: a regression test, a
conventional-commit title, and CI green. There is no changelog entry to write by
hand; release-please builds one from that title, as "Releases" in
CONTRIBUTING.md explains.

Put the upstream credit in the PR description (`dave-howard/vsdx#<n>`, or the
commit sha). This repository squash-merges with the PR title and body as the
commit message, so the branch's own commits never reach `main` and the `-x` line
goes with them.

### 4. Record the new point

Add a row to the table above in the same PR, or in a docs-only PR when the check
found nothing. A check whose result is not written down has to be redone.

## Sending a fix the other way

A fix of ours that is not entangled with our object model may be worth offering
upstream. The `upstream` label marks issues and PRs in that category.

GitHub will not open a pull request between two repositories with no fork
relationship. `firmfooting/vsdxkit` is not a fork of `dave-howard/vsdx` any
more, but [`firmfooting/vsdx-fork`](https://github.com/firmfooting/vsdx-fork),
this project's previous home, still is. Push the branch there and open the PR
from it.

Nothing here depends on that PR being accepted, and no release waits on it.
