# Design: slope-overview

## Context

- Issue #321 (owner, UAT of garmin-map's slope layer, 2026-11-24): slopes must show further out than
  zoom 9-10. The per-cell files can't: at zoom 8 a phone view meets ~100 cells.
- Measured on the four pilot cells' live manifest (2026-11-25): tier 4 holds 71–266 polygons and
  783–4,066 points per cell; `t1-4` is 66–510 KB gzip, tier 4 a small part of it.
- Colorado is 464 cells, perhaps 250 of them mountainous: roughly 50,000 polygons and 1M points
  statewide, an estimated 2–4 MB gzip (not measured; the backfill will tell).

## Decisions

- **Vector, in the cell encoding** (assumption, open question 1): the app already parses that format
  and draws its polygons with the watch's dots, so the overview needs no new library or look.
- **Tier 4 as built** (assumption, open question 2): no new recipe, no rebuild of the cells.
- **Written by the deploy job** from the files it publishes: the deploy job already holds every cell
  file (this run's from artifacts, the rest read back and checked), so the overview is derived from
  checked data with the standard library alone. A token-less job would have to fetch the site again.
- **Rebuilt every deploy, never read back**: it is a pure function of the published cells, so there is
  nothing on the live site to trust or check.
- **Cells in coverage order, polygons in their file's order**: the same cells give the same bytes.

## Open questions (for the owner)

1. **Vector or raster.** Assumed: vector polygons in the cell encoding. Rejected for now: pre-rendered
   raster tiles (e.g. one PMTiles file), which bound a view's work at any zoom but need a tile renderer
   in the pipeline and a PMTiles reader in the app.
2. **Detail.** Assumed: tier 4 exactly as in `t1-4`. If the statewide file turns out too large or too
   slow on a phone, a later change adds a coarser, more simplified overview tier (a recipe bump).
3. **How far out the app draws it.** garmin-map's change, not this one.

## Rollout

The overview is written only by a run that builds a cell (a run with nothing to build deploys nothing).
With the four pilot cells built and current, that is the first run after the all-Colorado change
(`regions.json` without `only`) merges. Until then the live site has built cells and no overview, and
garmin-map must treat a region with no `overview` entry as having none.

## Risks

- A phone drawing ~1M points: unmeasured; open question 2 is the fallback.
- One file per region grows with the region; the 20 MiB guard applies to it too. The overview is a pure
  function of every published cell, so once it passes the guard every later deploy fails, the yearly
  refresh included, until a change splits or coarsens it. The 2–4 MB estimate makes that unlikely.
- The overview is cached for an hour and the manifest for five minutes, so the manifest's
  `overview.bytes` may not match the file a cache serves for up to an hour. garmin-map's reader must not
  check the overview's size against the manifest (its 25 MiB cap stays).

## Review rounds

- Spec review, round 1 (2026-11-25): 0 blockers, 4 should-fix, 4 consider; all taken in the spec. No round 2.
- Conformance review, round 1 (2026-11-25): 2 hard fails (two tests that couldn't catch their regressions),
  4 soft fails (the "Deploying adds to the live site" file list, the rollout, two untested halves); all fixed.
