---
status: accepted
date: 2026-11-26
decision-makers: the owner ("For now leave empty when no lidar")
---
# Where Canada has no lidar, a cell is left empty: no 30 m fill

## Context and Problem Statement

British Columbia's lidar is NRCan's HRDEM. Measured against the 1 m mosaic's coverage footprints, it
covers about 8% of BC: 24 of 2,338 cells fully, 455 partly, 1,859 not at all, nothing north of 57° N.
The only national fill is MRDEM-30 (30 m) or the older CDEM (about 20 m), much coarser than the 10 m
fill used in the United States: at 30 m, steep terrain is smoothed, so much 30°+ terrain would read as
gentler.

## Considered Options

- Fill gaps from MRDEM-30, marked in the manifest as a new `dem30m` source
- Leave pixels and cells without lidar empty
- Cover only the parts of BC with lidar

## Decision Outcome

Chosen option: "leave them empty", the owner's, for now. A pixel with no lidar is `none` and in no
class; a cell no lidar project meets is built with every layer empty (no file), so the manifest says
there is no data and a later run picks up lidar NRCan adds (the 300-day refresh).

### Consequences

- Good, because nothing shown in BC is coarser than lidar.
- Good, because the manifest's form doesn't change: no new source key.
- Bad, because most of BC shows no slope, the north none at all.
