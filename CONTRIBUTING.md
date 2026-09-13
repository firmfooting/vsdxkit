# Contributions are welcome!

This repository is `vsdxkit`. The distribution
installs as `vsdxkit` and imports as `vsdx`. Python 3.10 or later is required.

#### Development environment

The repository uses [uv](https://docs.astral.sh/uv/) with a committed lockfile:

```
uv sync --group docs    # test, lint and build groups plus Sphinx (needs Python 3.12+)
uv run pytest tests -q
uv run ruff check vsdx tests tools
uv run ruff format --check vsdx tests tools
uv run pyrefly check vsdx --min-severity warn
uv run zizmor .github/workflows
uv run sphinx-build -W --keep-going -b html docs docs/_build/html
```

CI runs the tests across Python 3.10–3.14 on Linux and Windows, and on 3.10 and
3.14 on macOS. The ruff, pyrefly and Sphinx gates run once, on Linux under
Python 3.12. There is more besides: a lowest-direct dependency-floor job, a
distribution build-and-smoke-test, a LibreOffice import test, a coverage
threshold, a mypy consumer fixture, and `tools/check_action_pins.py` and
`tools/check_public_annotations.py`. zizmor runs as its own workflow rather than
inside CI. You do not need to run those locally; the list above is what to run
before submitting.

Commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:`, `ci:`,
`chore:`), matching the existing history.

#### Ideas / Features
If you have ideas for new features or improvements please raise a new
issue (_though please do check existing issues_).

If you would like to see an existing feature request delivered - please
comment on the issue.

If you identify a problem - then please raise a new issue with details
on how to recreate the problem so it can be resolved. If you are able
to provide a failing test case that would be super helpful :)

#### Code contributions
If you want to work on an existing issue please comment your intent on
the issue in case someone else is already actively working on it.

Feel free to fork, develop and submit pull requests. I will try to be
responsive - but apologies in advance if I am not!

Please add new tests for any new features you create, and keep the
existing type-checking and formatting gates green.

#### When a change needs Visio

Nothing in this library can tell you what Visio will do with the file it wrote.
Visio repairs some packages on open and silently discards parts of others: a
page declaring four shapes can open as three, with no error, no repair prompt,
and a clean save afterwards. Connector glue, routing, swimlanes, masters and
anything touching content types or relationships all have that failure mode.
Changes in that territory get the `needs-visio` label, which means the change is
not done until a real Visio has been asked.

You do not need Visio to contribute such a change. Open the PR, apply
`needs-visio`, and say which files a checker should generate. A maintainer on
Windows runs the harness.

##### The harness

`tools/visio_verify.py` compares two accounts of the same document: what the
package claims, read from its XML, and what Visio reports over COM. Where they
disagree, at least one of them is wrong, and neither is our own opinion of our
own output. It needs Windows and a licensed desktop Visio; Visio for the web has
no COM and cannot do this.

```console
$ python tools/visio_verify.py check out/generated.vsdx
AGREE  generated.vsdx: 1 page(s), 3 shape(s) - Visio sees the same document
```

A disagreement names the page, the shape and the side that is short:

```console
$ python tools/visio_verify.py check out/broken.vsdx
DIFFER broken.vsdx: 2 difference(s)
    page 1 shape 2: package declares shape 2 more than once on this page. Ids are
        page-scoped and unique; Visio keeps one and drops the rest without an
        error, so the rest of this page cannot be compared.
    page 1 connect 7.EndX: package glues shape 7 cell EndX to shape 5 cell PinX;
        visio does not
```

Unlike the checker it replaces, it exits non-zero on a disagreement, so it can
fail a pipeline. It also refuses to start when Visio is already running: a
stranded instance from an earlier crashed run holds the file, and the error that
produces reads exactly like a corrupt file. Pass `--allow-running-visio` if you
have Visio open and want to proceed anyway; the harness only ever shuts down
instances it started itself.

##### Recording, so that CI can check it too

Visio exists on one Windows desktop and CI runs on Linux, so a Visio run is
worth keeping:

```console
$ python tools/visio_verify.py record tests/test4_connectors.vsdx
RECORD test4_connectors.vsdx -> tests/fixtures/visio_observations/test4_connectors.json
```

`tests/test_visio_harness_replay.py` then re-derives what each fixture claims
*today* and compares it to that recording, on every run, with no Visio involved.
A change that alters the shapes, groups or glue in a recorded fixture fails in
ordinary CI. What that cannot catch is a change in what *Visio* does with
unchanged bytes; only re-running `check` on Windows catches that.

A recording describes one exact file and stores its hash. Edit the fixture and
replay reports `STALE` and fails, rather than passing on a comparison it did not
make — re-record it on a Windows machine. Delete the fixture and its recording
is reported as an `ORPHAN`. Neither is allowed to go quietly green, because a
harness that is believed and wrong is worse than no harness.

Add a recording whenever you add a fixture that a Visio run has vouched for. Do
not hand-edit one: the schema is versioned and a recording written under another
version is refused, not guessed at.

The connector and swimlane ground truth the engine was built against lives in
`tests/fixtures/com_reference/`, generated by `tools/com_reference.ps1`. See
[that directory's README](tests/fixtures/com_reference/README.md) before
changing a fixture or adding a scenario.

#### Releases
Releases are cut by [release-please](https://github.com/googleapis/release-please),
not by hand. You do not bump a version, write a changelog entry, or push a tag.

**What you do:** give your pull request a
[conventional commit](https://www.conventionalcommits.org/) title. That is
enforced by the `PR title` check, because this repository squash-merges and the
title becomes the commit subject on `main` — which is what release-please reads.

```
fix: remap every Sheet reference in a formula when copying shapes
feat(pages): add Page.background
docs: document the COM reference corpus
feat!: rename VisioFile to Document          # `!` marks a breaking change
```

`fix:` bumps the patch version, `feat:` the minor, and `!` or a
`BREAKING CHANGE:` footer the major — though while the project is pre-1.0 a
breaking change bumps the minor instead.

Only `feat:`, `fix:` and `perf:` reach the release notes. **`build:`, `chore:`,
`ci:`, `docs:`, `refactor:`, `style:` and `test:` are silent** — a change titled
`refactor:` that users can actually observe disappears from the notes entirely.
So pick the type from what the change does to someone using the library, not
from which directory it touches: a rework that changes behaviour is a `fix:`.

**What happens then:** release-please keeps a release PR open, updating the
version and `CHANGELOG.md` as commits land. Merging that PR creates the tag and
the GitHub release, and the same workflow run builds the distribution, re-runs
the tests and lint gates, smoke-tests the wheel in a clean environment, and
publishes to PyPI with [PEP 740](https://peps.python.org/pep-0740/)
attestations. No API tokens exist anywhere; PyPI authenticates the workflow
through Trusted Publishing, matched on the repository, the workflow **filename**
and the `pypi` environment. Renaming `.github/workflows/publish.yml` breaks
publishing, and the failure reads like a permissions error rather than a naming
one.

**If the release run fails after the release PR is merged**, do not use "Re-run
all jobs": release-please finds the release already made, reports no new
release, and the run goes green having published nothing. Fix forward and use a
manual run of the Publish workflow, which republishes the tagged version through
the same gates. A manual run only works from `main` and only for a version that
already has a tag.

**Before merging a release PR**, read the generated changelog. Release notes
built from commit subjects are terser than what a reader usually wants; you can
edit the PR's `CHANGELOG.md` to add detail, and release-please will respect it.

The version lives in one place, `vsdx/__init__.py`, marked with an
`x-release-please-version` annotation. `pyproject.toml` reads it through
`tool.setuptools.dynamic`; a static `[project].version` would go stale in
`uv.lock` on every bump and fail the `uv sync --locked` gate.

**First release only:** the manifest already records `0.7.0`, so release-please
manages releases *after* it. `v0.7.0` is tagged by hand and published with a
manual run of the Publish workflow.

#### The project this one descends from
vsdxkit began as a fork of [dave-howard/vsdx](https://github.com/dave-howard/vsdx)
and is now developed independently — it does not track that project. If a change
you are making is a plain bug fix that would help users of the original too,
offering it there as well is a kindness, but nothing here depends on it.

Maintainers: [`docs/maintainers/upstream-sync.md`](docs/maintainers/upstream-sync.md)
records when to check that repository for fixes worth taking, how to take one
with attribution that survives a squash merge, and the last sync point. It is
not part of the published documentation, so the path is the only way in.

#### Security
Please report vulnerabilities privately — see [SECURITY.md](SECURITY.md).

Thank you :)
