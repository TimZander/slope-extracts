---
status: accepted
date: 2026-11-26
decision-makers: the owner (the bands, after a watch test); Claude (the rollout)
---
# Tier 0 in the reader's seven "B" bands, recipe 2, with both recipes' classes accepted during the rebuild

## Context and Problem Statement

The app reading these cells now shades the closest zoom in seven bands: 27–30, 30–32, 32–35, 35–45,
45–50, 50–60 and cliffs 60+ ("B"). The owner chose B over the current bands and a nine-band variant after
trying all three on the Enduro 3 on 2026-11-26: B's bands were told apart (yellow and orange clearly,
yellow-green and yellow less so, accepted as long as file size and build time don't grow excessively).
Recipe 1's tier 0 holds 30, 35, 40, 45 (45–55) and cliffs 55, which the app can only approximate.
Changing tier 0 means rebuilding every live cell, about 800, while the site serves both recipes.

## Considered Options

- Bands: B at both tier-0 layers; B at `t0-3m` only; the nine-band variant
- Rollout: bump `RECIPE` and let the scheduled runs rebuild; also raise the cells per run
- The deploy check during the rebuild: both recipes' tier-0 classes; classes by the cell's recipe;
  only the new classes

## Decision Outcome

Chosen: **B at both tier-0 layers, `RECIPE` 2, the existing 48 cells per run, and a deploy check that
accepts both recipes' tier-0 classes**, because:

- the reader treats `t0-2m` as the same bands at 2 m, and the owner chose B;
- a recipe bump is how this pipeline already rebuilds stale cells, Colorado first in `areas.json`'s
  order; raising the cells per run is a change to the high-risk build workflow for a one-off;
- a kept recipe-1 file is re-read and checked when `hashes.json` doesn't list it or Cloudflare lacks it,
  so accepting only the new classes could fail every deploy until the rebuild ends; choosing classes by
  the cell's recipe would need the entry beside every file check, for a window of about a day.

Tiers 1–4 are unchanged. Cliffs stay 2 m with their numbers; the bands' top class is `50`, so a 3 m
pixel above 60° is in `50`, as one above 55° was in `45`.

### Consequences

- Good, because every cell's closest zoom ends up in the bands the owner chose, with no manual step.
- Good, because the cell format and manifest don't change; the app already reads both recipes.
- Bad, because the rebuild takes about 800 cells at about 75 an hour, roughly 11 hours of runs, and
  new British Columbia cells wait behind it.
- Bad, because finer bands add polygons: more cells may be split into quarters, and more quarters may
  leave out `t0-2m`. Measured after the rebuild in `docs/measurements.md`.
- Neutral: the deploy check is wider than any one cell needs until a later change narrows it.

## More Information

Change `b-bands-tier-0`. Recipe 1 had no ADR of its own (the v10 watch-tested design).
