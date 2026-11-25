---
status: accepted
date: 2026-11-25
decision-makers: the owner ("expand the coverage area", after the four-cell pilot passed its watch test); Claude (dropping the list rather than widening it)
---
# Build all of Colorado: drop the pilot's `only` list

## Context and Problem Statement

The first deploy built four pilot cells around Dillon Reservoir, held there by Colorado's `only` list in
`regions.json`. The app's slope layer has passed its test on the watch with those cells, and the owner
asked for a larger coverage area.

## Considered Options

- Drop the `only` list, so the scheduled runs build every covered Colorado cell
- Widen the `only` list to the mountain cells first, then drop it
- Add a second region

## Decision Outcome

Chosen option: drop the `only` list.
- Colorado's 464 covered cells are built in coverage order, 48 per 3-hourly run, as ADR 0006 planned:
  about 10 runs, roughly 30 hours.
- Nothing in the pipeline changes. The four pilot cells are already built with the current recipe, so
  they are kept.
- About 1,400 cell files, well under the deploy's 19,000-file guard.

### Consequences

- Good, because the whole state fills in with no further change; flat cells are cheap.
- Good, because widening the list in stages would need a commit per stage for the same end state.
- Bad, because cells are built in coverage order, not mountains first, so a given range may wait up to
  about 30 hours.
- Bad, because once the backfill is done the schedule still needs ADR 0006's switch to June only.
