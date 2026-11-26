---
status: accepted; its schedule superseded by ADR 0035 (runs follow one another)
date: 2026-11-23
decision-makers: the owner (cadence: "each region will run once per year or so. dem doesn't change often"); Claude (batch size, the 300-day rule, the schedules)
---
# A run builds at most 48 missing, stale or year-old cells; every 3 hours during the backfill, then every 3 hours in June only

## Context and Problem Statement

Colorado is 464 cells at ~8 minutes each, and a job may run 6 hours. The DEM rarely changes, so a weekly
full rebuild like osm-extracts' would be waste. The owner wants each region refreshed about once a year.

## Considered Options

- Each run builds, at most 48 at a time, covered cells that are missing, built with another recipe, or
  built over 300 days ago. Every 3 hours until the backfill is done, then every 3 hours in June.
- Rebuild every cell each run
- Build only by hand, with a cell list as input (inputs widen what a run's caller can steer, ADR 0007)

## Decision Outcome

Chosen option: the first.
- 48 steep cells are ~0.75 GB, which bounds a run's jobs and upload.
- The Colorado backfill takes about 10 runs (~30 hours) on the 3-hourly schedule `41 */3 * * *`.
- Once every cell is built, a follow-up change sets the schedule to `41 */3 * 6 *`. In June, cells over
  300 days old are rebuilt 48 at a time. The rest of the time a run does nothing, and a manual run still
  works.
- Bumping `RECIPE` rebuilds every cell the same way.

### Consequences

- Good, because the site fills in and refreshes without anyone watching.
- Good, because "build what is covered and missing" is also what an on-demand request would need.
- Bad, because switching the schedule after the backfill is a manual follow-up (task 4.4).
- Bad, because GitHub disables a schedule after 60 days of repository inactivity, and the June runs may
  find it disabled. A manual run still works.
