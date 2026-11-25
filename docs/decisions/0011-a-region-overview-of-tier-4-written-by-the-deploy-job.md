---
status: accepted
date: 2026-11-25
decision-makers: the owner (slopes must show further out than zoom 9-10, garmin-map issue #321; "do the public work now"); Claude (the format and where it is written, as assumptions the owner hasn't answered yet)
---
# A per-region overview of every built cell's tier 4, written by the deploy job

## Context and Problem Statement

The app can draw slope cells only from zoom 9 in: further out, a phone view meets about 100 cells and
40+ MB. Tier 4 (30°+, 72 m) is small: on the four pilot cells it is 71–266 polygons and 783–4,066 points
per cell (live manifest, 2026-11-25). One file per region holding every built cell's tier 4 is estimated
at 2–4 MB for Colorado (not measured).

## Considered Options

- Vector tier 4 in the cell encoding, one file per region, written by the deploy job
- The same file written by a token-less job after the build jobs
- Pre-rendered raster tiles (e.g. one PMTiles file per region)
- A coarser new overview tier (a recipe bump)

## Decision Outcome

Chosen option: the first.
- The app already parses the cell encoding and draws its polygons with the watch's dots, so it needs no
  new library or look.
- The deploy job already holds every cell file it publishes, checked, so the overview is derived from
  checked data with the standard library alone. A token-less job would have to fetch the whole site
  again and hand the deploy job a file it would then have to check.
- It is rebuilt on every deploy and never read back, so nothing on the live site steers it. A build job
  can't upload one: the artifact check refuses any file it doesn't expect.

Vector over raster and tier 4 as built are **assumptions**: open questions 1 and 2 in the change's
`design.md`. Each answer from the owner gets its own record.

### Consequences

- Good, because there is no new job, input or dependency, and the cells are not rebuilt.
- Good, because the same cells give the same bytes, so Direct Upload skips an unchanged overview.
- Bad, because the file grows with the region, and a phone drawing ~1M points is unmeasured. The
  fallback is a coarser tier (open question 2).
- Bad, because once an overview passes 20 MiB every deploy fails until a change splits or coarsens it.
- Bad, because the cell cache rule had to be narrowed to `/:region/:cell/*` so the overview's one-hour
  rule is the only one matching its path.
