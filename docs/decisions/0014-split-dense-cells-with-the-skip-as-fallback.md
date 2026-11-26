---
status: accepted
date: 2026-11-26
decision-makers: the owner (split dense cells into quarters; the limits stay); Claude (the split replaces the skip, which stays as the fallback, as the owner asked Claude to decide)
---
# A cell too large to publish whole is split into four quarters; leaving out `t0-2m` is the fallback

## Context and Problem Statement

A few very steep cells build a layer file too large to publish: over 20 MiB of gzip or 64 MiB of JSON.
Cloudflare Pages caps a file at 25 MiB, so the limits stay. ADR 0013 left such a cell's `t0-2m` out as
a stop-gap; issue #10 asked to split such a cell into four 0.125° quarters instead (change
split-dense-cells). In the first run with the stop-gap, `150_-431`'s `t0-2m` was 25,061,558 bytes of gzip
(104,510,741 of JSON) and `151_-431`'s 85,357,762 bytes of JSON. Should the split replace the skip,
or should the skip stay?

## Considered Options

- The split replaces the skip for whole cells; a quarter whose `t0-2m` is still over a limit is
  left out with ADR 0013's marker (the fallback)
- The split alone: a cell whose quarter is still too large fails
- Split again into sixteenths when a quarter is still too large
- Raise the limits

## Decision Outcome

Chosen option: the split, with the skip as its fallback. When any of a cell's layer files would be over
a limit, the build job writes the cell as its four quarters instead, and never leaves out a whole
cell's layer. If a quarter's `t0-2m` is still over a limit, that quarter is written without it,
marked as ADR 0013 marks it, so one file can't block the deploy. A quarter's `t0-3m` or `t1-4` over
a limit fails the cell, as a whole cell's did. Rejected: the split alone, which would let a dense
enough cell block its job again; a second level of splitting, for a case no cell has shown; raising
the limits (the 25 MiB cap).

### Consequences

- Good, because the two known cells get their 2 m bands back: their quarters average about 26 and
  21 MB of JSON, under 64 MiB.
- Good, because one oversize file still can't block the deploy.
- Bad, because a quarter can still lose its `t0-2m`, and readers must still check `bytes` 0.
- This supersedes ADR 0013 for whole cells; its marker stays, on quarters and on live cells built
  before this change.
