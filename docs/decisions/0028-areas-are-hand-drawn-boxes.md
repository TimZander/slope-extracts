---
status: proposed
date: 2026-11-26
decision-makers: the owner (grid-v2's open questions, 2026-11-26)
---
# Areas are lists of hand-drawn boxes, not outlines

## Context and Problem Statement

The site moves from regions to the coordinate grid (change grid-v2): cells stored once, indexed by
tiles, covered by named areas. The owner chose among the draft's options.

## Considered Options

- The chosen one, below
- Outline polygons from a public-domain boundary set (exact, but outside data and a point-in-polygon test in the stdlib-only plan job); one box per area, as regions are today (Idaho's box 38% outside it)

## Decision Outcome

Chosen: An area is a list of boxes, each a south/west/north/east box; its coverage is every cell a box touches. Idaho is three or four boxes following its outline.

### Consequences

- Good, because no outside data and the plan job stays simple.
- Bad, because edges are approximate: a few cells outside an area are built.
