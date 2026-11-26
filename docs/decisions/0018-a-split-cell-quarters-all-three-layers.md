---
status: accepted
date: 2026-11-26
decision-makers: the owner (2026-11-26, from the options Claude put; the recommended one)
---
# A split cell quarters all three layers, not only the oversize one

## Context and Problem Statement

A few very steep cells build a layer file too large to publish: over 20 MiB of gzip or 64 MiB of JSON.
Cloudflare Pages caps a file at 25 MiB, so the limits stay. ADR 0013 left such a cell's `t0-2m` out as
a stop-gap; issue #10 asked to split such a cell into four 0.125° quarters instead (change
split-dense-cells). In practice only `t0-2m` is too large. Is only that layer quartered, or the whole cell?

## Considered Options

- All three layers are quartered when any one is over a limit
- Only the oversize layer is quartered; the others stay whole-cell files

## Decision Outcome

Chosen option: "all three layers", because a cell is then in one form, whole or split, and a reader
handles it one way. Rejected: only the oversize layer (a mix within one cell, and the manifest would
say per layer which form each is in).

### Consequences

- Good, because the manifest and the reader have one rule per cell.
- Bad, because a split cell is 12 files, where quartering only `t0-2m` would make 6; only cells over a
  limit split, and the site is far from its 19,000-file cap.
