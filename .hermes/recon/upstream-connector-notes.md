# Upstream recon: dave-howard/vsdx

**Date:** 2026-09-11. Gathered via `gh` against upstream master (`6703e6c`, v0.6.1).

## 1. Maintenance status

- Last push: **2026-01-04** (v0.6.1 release). Not archived. 33 open issues.
- The release folded in community PRs #78/#80/#83 (all one contributor,
  jchan-legendpower, Jan 2026) — so the maintainer **was** merging community
  work recently.
- Since that release: **6 PRs open with none merged** (#84–#89, all small: text
  handling, zip path normalisation, background pages, foreign data WIP, load
  performance from 2024). #68 (perf) has sat since Jan 2024.
- Maintainer responds on issues sporadically (replied on #70; silent on #90, #92).
- Implication: alive but low cadence, and the merge backlog is 8 months deep.
  Universal bugfixes are worth sending up; capability work cannot wait on this
  cadence.

## 2. Connector-related items

| # | State | Date | Ask | Lesson for us |
| --- | ------- | ------ | ----- | --------------- |
| 77 | open | 2025-11 | `Connect.create` getroot problem | Same in-memory extraction gap as our corruption fix (#93 filed upstream): the elif/master provisioning path |
| 63 | closed | 2023-10 | AttributeError 'NoneType' getroot while connecting | Same region; closed without visible fix — recurring symptom class |
| 46 | open | 2022-07 | Glue to shape | Users want real glue; our _WALKGLUE engine is the answer shape |
| 73 | open | 2024-09 | Get from/to node for directed arrow | Users expect to query connector endpoints — connect()/Connectors API should expose from/to cleanly (our Connect already does) |
| 37 | open | 2022-02 | Connectors + page size | Page sizing interacts with routing; page-size setter work should be tested with connectors |

## 3. Swimlane/container items

None found in 92 issues. Greenfield — nobody has asked upstream, and nothing
blocks a fork-first implementation. Our s05 CFF corpus capture (`msvSD*` cells,
Swimlane/CFF Container/Phase List masters) has no upstream prior art to conflict
with.

## 4. Shape-creation items

| # | State | Date | Ask |
| --- | ------- | ------ | ----- |
| 70 | open | 2024-02 | Create .vsdx from scratch, create shapes in an empty file — maintainer's only guidance: hand-build a template and copy shapes (validates our palette/template approach) |
| 54 | open | 2022-11 | Create shape, drop on page, set location/attributes |
| 41 | open | 2022-05 | Copy shapes between vsdx files |
| 75 | open | 2025-03 | Import/add image |
| 69 | open | 2024-01 | Multiple geometries per shape |

## 5. Top API expectations distilled from user asks

1. Create shapes on a blank document without hand-building templates first
   (#70, #54).
2. Copy shapes from one vsdx file into another (#41).
3. Glue connectors to specific shapes and specific connection points, not just
   coordinates (#46, #73).
4. Connector creation that works reliably on documents opened in memory (#63, #77).
5. Set text without breaking field-bearing shapes (#88, #92).
6. Set page width/height on newly added or copied pages (#72).
7. Data properties that round-trip values and refresh dependent text (#79, #64).
8. Hyperlinks on shapes (#74).
9. Embedded images (#75).
10. Acceptable load time on large documents (#67) — we rejected PR #68's unsound
    cache; a sound fix would be valued.

## 6. Recommendation: upstream-PR vs fork-forward

**Fork-forward for capability, targeted PRs for universal bugs.**

- Fork-forward: connector engine, swimlanes/containers, extended palette,
  create_shape API. Upstream's 8-month merge backlog cannot absorb feature work,
  and these are the whole point of our fork.
- Upstream PRs (staged small-first): #93 corruption fix (anchors issue #93 —
  concrete bug, small tested diff, likely explains open #90), then #94
  curved_connector one-liner (anchor #94). Use maintainer responsiveness on
  these to decide whether to also offer the connector engine as a PR.
- Convention per upstream-contribution-conventions: issue first, fix PR anchored
  to it, no labels/reviewers/assignees.
