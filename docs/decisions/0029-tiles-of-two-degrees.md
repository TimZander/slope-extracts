---
status: proposed
date: 2026-11-26
decision-makers: the owner (grid-v2's open questions, 2026-11-26)
---
# The grid is indexed by 2-degree tiles of 64 cells

## Context and Problem Statement

The site moves from regions to the coordinate grid (change grid-v2): cells stored once, indexed by
tiles, covered by named areas. The owner chose among the draft's options.

## Considered Options

- The chosen one, below
- 1-degree tiles of 16 cells (four times the files for a zoomed-out view); 4-degree tiles of 256 cells (a dense mountain tile's overview near the 20 MiB cap)

## Decision Outcome

Chosen: A tile is floor(lat / 2)_floor(lon / 2); each with a covered cell has an index of its cells and an overview of their tier 4. Colorado spans 12 tiles.

### Consequences

- Good, because no tile file grows with an area, and a reader fetches only the tiles in view.
- Bad, because the plan job reads one index per tile.
