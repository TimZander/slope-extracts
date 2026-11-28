---
status: accepted
date: 2026-11-28
decision-makers: the owner (the states, Idaho's box, Utah to 42° N, the order: 2026-11-26, confirmed 2026-11-28); Claude (the insets)
---
# Wyoming, Utah and Idaho are areas after British Columbia; Idaho is its whole box, Utah reaches 42° N

## Context and Problem Statement

The owner asked on 2026-11-26 for Wyoming, Utah and Idaho. That change was paused until the deploy
scaled, then overtaken by grid-v2 (ADRs 0028–0033), which stores a cell once whatever covers it and
indexes the site by tiles. Under grid-v2 adding a state is an entry in `areas.json`; the open questions
the paused change raised (a border cell built twice, a job holding a cell twice, the manifest's size)
no longer arise. On 2026-11-28 the owner asked to finish it, with all three states.

## Considered Options

- Idaho: its whole bounding box (42–49° N, 117.23–111.05° W); up to 45° N; osm-extracts' southern block
- Utah: up to 42° N, its north line; up to 41° N
- Order: after Colorado and British Columbia, Wyoming, Utah, Idaho; or another order

## Decision Outcome

Chosen (the owner's, from 2026-11-26):
- **Idaho is its whole bounding box**: 700 cells, the panhandle and Bitterroots included; about 38% of
  them lie in Montana, Oregon or Washington.
- **Utah reaches 42° N**: 420 cells, Ogden and Logan included, Wyoming's corner shared.
- **Order: Colorado, British Columbia, Wyoming, Utah, Idaho.** The plan builds in list order, so the
  states start once British Columbia is done.

The boxes are inset 0.01° from a state line on a cell line (as Colorado's): Wyoming 41.01 / −111.04 /
44.99 / −104.06, Utah 37.01 / −114.04 / 41.99 / −109.06, Idaho 42.01 / −117.23 / 48.99 / −111.05. All
three read USGS 3DEP (`source` `3dep`).

### Consequences

- Good, because 1,520 cells are new to the site (Wyoming 464, Utah 368, Idaho 688); the 52 cells Utah
  shares with Colorado and Wyoming and the 12 Idaho shares with Wyoming are built once.
- Good, because the site grows from 61 to 90 tiles and about 3,700 to 9,100 files, under the 19,000 limit.
- Bad, because about 32 more runs, roughly a day with runs back to back.
- Bad, because Idaho's box spends about 260 cells outside Idaho (the owner's choice).
