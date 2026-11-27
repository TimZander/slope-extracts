# Proposal: b-bands-tier-0

## Why

The app that reads these cells now shades the closest zoom in seven finer bands, owner-chosen after a
watch test on the Enduro 3 (2026-11-26, design "B"): finer steps from 27° to 35°, one 35–45° band,
45–50° and 50–60° bands, and cliffs from 60°. Tier 0 today holds 30, 35, 40, 45 (45–55°) and cliffs 55, so
the app has to read those as approximations until every cell is rebuilt with the new bands.

## What Changes

- Tier 0 (both `t0-3m` and `t0-2m`) holds bands `27`, `30`, `32`, `35` (35–45°), `45`, `50` (50–60°)
  and cliffs `60` (2 m) instead of `30`, `35`, `40`, `45` and `55`. Sieve, simplify and minimum area
  are unchanged.
- `RECIPE` goes from 1 to 2, so the scheduled runs rebuild every live cell, Colorado first, at the
  existing 48 cells per run.
- While the site holds cells of both recipes, the deploy job also accepts recipe 1's tier-0 classes
  `40` and `55`, so a kept cell read back before it is rebuilt doesn't fail the deploy.
- Tiers 1–4 (`t1-4`) don't change: same classes, same numbers.

## Capabilities

### Modified Capabilities

- `slope-extract`: tier 0's classes; the deploy job's cell-file check during the rebuild.

## Impact

- `slope_extracts/recipe.py` (tier-0 edges, `RECIPE`), `slope_extracts/publish.py` (tier-0 classes
  accepted), tests, the README.
- The cell format and manifest are unchanged: a class is still named by its lower bound, and the app
  already reads both recipes' tier-0 classes. No change to the build workflow file.
- Every live cell is rebuilt: about 800 at the time of writing, at roughly 75 an hour.
