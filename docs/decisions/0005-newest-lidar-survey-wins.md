---
status: accepted
date: 2026-11-23
decision-makers: Claude (assumption; the owner can reverse it)
---
# Where lidar surveys overlap, the newest publication wins; the 10 m DEM fills what no lidar covers

## Context and Problem Statement

Around Dillon, three 3DEP lidar projects overlap: CO_Central_Western_2016, CO_DRCOG_2020 and
CO_ArapahoRooseveltPikeNF_D23. The spike listed tiles by hand, 2016 first. A pipeline needs a rule.

## Considered Options

- Newest publication date first, then by URL
- Oldest first (the spike's order)
- The survey covering most of the cell first

## Decision Outcome

Chosen option: "newest first", because a newer survey is the best guess at today's terrain, and the
rule needs nothing but the API's answer. The mosaic keeps the first valid value per pixel, so older
surveys fill only where the newer one has no data.

### Consequences

- Good, because it is deterministic, and the projects used are listed per cell.
- Bad, because it differs from the spike's Dillon build. The pilot cell came out with 157,624 tier-0
  polygons, against the spike's 154,625 (its frame had no buffer).
