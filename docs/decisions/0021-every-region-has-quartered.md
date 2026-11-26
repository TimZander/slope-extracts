---
status: accepted
date: 2026-11-26
decision-makers: the owner (split-dense-cells open question 3, 2026-11-26: the assumption the change proceeded on)
---
# Every region has `quartered`, `{}` when it has no split cell

## Context and Problem Statement

A few very steep cells build a layer file too large to publish: over 20 MiB of gzip or 64 MiB of JSON.
Cloudflare Pages caps a file at 25 MiB, so the limits stay. ADR 0013 left such a cell's `t0-2m` out as
a stop-gap; issue #10 asked to split such a cell into four 0.125° quarters instead (change
split-dense-cells). ADR 0015 adds the region map `quartered`. Is it written always, or only when a region has a
split cell?

## Considered Options

- Always, `{}` when empty (as osm-extracts always writes `split`)
- Only when the region has a split cell

## Decision Outcome

Chosen option: "always", so a reader that knows quarters never has to test for the key. A live
manifest without it, as every manifest before this change, is read as having no split cell.

### Consequences

- Good, because one form for readers that know quarters.
- Neutral, because a reader that knows only `cells` ignores the key either way.
