---
status: proposed
date: 2026-11-26
decision-makers: the owner (grid-v2's open questions, 2026-11-26)
---
# The site switches to manifest version 2 at once

## Context and Problem Statement

The site moves from regions to the coordinate grid (change grid-v2): cells stored once, indexed by
tiles, covered by named areas. The owner chose among the draft's options.

## Considered Options

- The chosen one, below
- Publishing both layouts until the reader moves (double the cell paths for a while); version 2 on another Pages project or host

## Decision Outcome

Chosen: manifest.json becomes version 2 and the region layout goes in the same deploy; the reader's change ships first.

### Consequences

- Good, because one layout, one set of files and no transition code.
- Bad, because this change can't merge until the reader reads version 2.
