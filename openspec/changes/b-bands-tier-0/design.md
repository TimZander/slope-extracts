# Design: b-bands-tier-0

## Context

- The reader's tier-0 bands (owner's choice, 2026-11-26): 27–30, 30–32, 32–35, 35–45, 45–50, 50–60,
  and cliffs 60+. The reader keeps reading recipe 1's `40` (as 35–45) and `55` (as cliffs) until every
  cell is rebuilt.
- A class is named by its lower bound, and in tier 0 the cliffs layer's class sits beside the bands'
  (`{**bands, **cliffs}` in `build_cell.py`), so `50` from the 3 m or 2 m bands covers 50°+ pixels and
  `60` from the 2 m cliffs covers 60°+, as `45` and `55` did.
- The live site holds about 800 built cells of recipe 1 (Colorado and part of British Columbia). The
  plan rebuilds a cell whose entry names another recipe, at most 48 a run, in the areas' order.
- The deploy job re-reads a kept file when `hashes.json` doesn't list it or Cloudflare no longer holds
  it, and checks it with the cell-file check, classes per tier included.

## Goals / Non-Goals

**Goals:** every cell's tier 0 in the new bands; no deploy fails while old and new cells sit side by
side.

**Non-Goals:** tiers 1–4 (their classes stay; the reader keeps them); new sieve or simplify values;
faster rebuilding; the build workflow file.

## Decisions

1. **Both tier-0 layers get the same bands** (the reader treats `t0-2m` as the same bands at 2 m).
2. **Cliffs from 60°, still from the 2 m DEM** with the existing cliff numbers. The 3 m bands' top
   band is `50`. Rejected: a 3 m `60` class beside the 2 m cliffs (two `60` classes in one tier).
3. **`RECIPE` 2, nothing else changes in the plan.** The existing rule rebuilds stale cells; Colorado
   comes first because it is first in `areas.json`. Rejected: rebuilding faster with more cells per
   run (a workflow change, high-risk, for a one-off).
4. **The deploy job accepts both recipes' tier-0 classes,** `27`, `30`, `32`, `35`, `40`, `45`, `50`,
   `55` and `60`, in any tier-0 file. Rejected: classes chosen by the cell's recipe (the check would
   need the entry beside every file, for a window of a day or so); accepting only the new classes
   (a kept recipe-1 file read back would fail every deploy until it is rebuilt). Narrowing it again
   after the rebuild is a later change.
5. **The test cone gets eight rings** (62, 53, 47, 42, 37, 33, 31, 28°) so tier 0 shows all seven
   classes and tier 1 still shows all four of its own.

## Risks

- Finer bands mean more polygons per cell: more cells may be split into quarters, and a quarter's
  `t0-2m` may be left out more often. The existing limits and fallback handle both; the counts are
  measured after the rebuild.
- Rebuild time: about 800 cells at about 75 an hour, so roughly 11 hours of runs; Colorado's cells
  are done first.

## Open questions

None.
