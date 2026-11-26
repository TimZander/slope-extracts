---
status: accepted
date: 2026-11-26
decision-makers: the owner (split-dense-cells open question 2, 2026-11-26: the assumption the change proceeded on)
---
# The plan rebuilds a whole cell the live manifest lists with a layer left out

## Context and Problem Statement

A few very steep cells build a layer file too large to publish: over 20 MiB of gzip or 64 MiB of JSON.
Cloudflare Pages caps a file at 25 MiB, so the limits stay. ADR 0013 left such a cell's `t0-2m` out as
a stop-gap; issue #10 asked to split such a cell into four 0.125° quarters instead (change
split-dense-cells). The stop-gap published `150_-431` and `151_-431` whole without `t0-2m`, with the current
recipe, so the plan would not build them again until the yearly refresh.

## Considered Options

- The plan also chooses a cell listed in `cells` with a layer left out; a split cell with a quarter's
  layer left out is not chosen
- Bump `RECIPE`
- Wait for the yearly refresh

## Decision Outcome

Chosen option: "rebuild whole cells with a layer left out", so the next run rebuilds the stop-gap's
cells as quarters. Rejected: a recipe bump (it would rebuild all 464 cells, and no number in
`recipe.py` changes); waiting (about a year without 2 m bands). A split cell with a quarter's layer
left out is not chosen again, since it would build the same way every run.

### Consequences

- Good, because the two cells regain their 2 m bands on the first run after merge.
- Bad, because a whole cell with a layer left out, should one come back from an older build, is
  rebuilt every run until it builds whole or split.
