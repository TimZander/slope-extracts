---
status: accepted
date: 2026-11-26
decision-makers: the owner (2026-11-26, from the options Claude put; the recommended one)
---
# The manifest lists split cells in a region map `quartered`, apart from `cells`; version stays 1

## Context and Problem Statement

A few very steep cells build a layer file too large to publish: over 20 MiB of gzip or 64 MiB of JSON.
Cloudflare Pages caps a file at 25 MiB, so the limits stay. ADR 0013 left such a cell's `t0-2m` out as
a stop-gap; issue #10 asked to split such a cell into four 0.125° quarters instead (change
split-dense-cells). The manifest is read by other software, which fetches
`<region>/<cell>/<layer>.json.gz` for every key of a region's `cells`. How is a split cell listed so
that existing readers keep working?

## Considered Options

- A new region map `quartered` beside `cells`, manifest version 1
- The cell stays in `cells`, and a region list `split` names it (as osm-extracts does)
- The cell stays in `cells`, and its entry gains `quarters`
- A manifest version 2

## Decision Outcome

Chosen option: "a new region map `quartered`", because a reader that knows only `cells` sees a split
cell as not yet built, a gap rather than a 404, and keeps working on every whole cell. A cell is in at
most one of the two maps. Rejected: a `split` list or a `quarters` key in `cells` (existing readers
would request whole-cell files that don't exist, and a strict reader might reject the entry); a version
bump (every existing reader would reject the whole manifest, whole cells included).

### Consequences

- Good, because no existing reader breaks; each misses only the split cells.
- Bad, because a reader that knows only `cells` shows nothing for a split cell, where the stop-gap
  gave it `t0-3m` and `t1-4`, until it learns `quartered`.
- Bad, because "absent from `cells`" no longer means "not built"; the plan job reads both maps.
