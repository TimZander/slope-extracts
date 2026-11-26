---
status: proposed
date: 2026-11-26
decision-makers: the owner (grid-v2's open questions, 2026-11-26)
---
# A layer with no polygons has no file

## Context and Problem Statement

The site moves from regions to the coordinate grid (change grid-v2): cells stored once, indexed by
tiles, covered by named areas. The owner chose among the draft's options.

## Considered Options

- The chosen one, below
- Keeping a file for every layer (about three per flat cell); a separate change before British Columbia

## Decision Outcome

Chosen: A layer, a whole cell's or a quarter's, whose tiers hold no polygon is published as no file, its entry bytes 0 and tiers {}; the first run turns v1 layers counted empty into such entries.

### Consequences

- Good, because flat and ocean cells cost almost no files, before large areas.
- Bad, because a reader must check bytes before requesting a layer, as it already must for a left-out t0-2m.
