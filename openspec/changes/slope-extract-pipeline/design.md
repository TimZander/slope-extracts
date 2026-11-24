# Design: slope-extract-pipeline

## Context

The 2026-11-23 spike settled the look and detail on
the owner's Enduro 3 and wrote it as one-off Python scripts over the Dillon cell (`158_-425`). This change
turns those scripts into a pipeline: the same classes, per cell, built in CI and published like
TimZander/osm-extracts.

Measured on the pilot (MacBook, 2026-11-23; `docs/measurements.md`):

| Cell 158_-425 (Dillon) | t0-3m | t0-2m | t1-4 |
|---|---|---|---|
| polygons | 157,624 | 318,444 | 8,056 (5,293 / 1,340 / 1,314 / 109) |
| points | 3.08 M | 6.61 M | 0.21 M |
| file (gzip JSON) | 5.0 MB | 9.8 MB | 0.43 MB |
| `.img` with v10 TYP | 4.95 MB | 9.2 MB | (in both) |

Building the cell took 462 s (most of it download), 6.3 GB peak memory. Native mkgmap compiles the 3 m
cell in 8 s and the 2 m one in 16 s. mkgmap on CheerpJ in desktop Chromium takes 67 s for the 3 m cell.

## Decisions

- **Python, not Node.** DEM work needs GDAL, numpy and shapely, all as manylinux wheels. The plan and
  deploy jobs use only the standard library, so they install nothing. Build-job wheels are pinned by
  hash (ADR 0004).
- **The cell file is gzip JSON of delta-coded integers** (ADR 0002). Points are in 24-bit Garmin map units,
  the finest unit mkgmap writes, so quantising loses nothing the watch would show. Gzip JSON is 5.0 MB
  for the Dillon cell at 3 m. A varint binary was 4.5 MB gzipped, about 10 % smaller, but needs its own
  parser in the app. Raw (ungzipped) JSON would be 19 MB at 3 m and ~40 MB at 2 m, over Pages' 25 MiB
  limit, so the files are stored gzipped and the app unpacks them (`DecompressionStream`).
- **Three layers per cell:** `t0-3m`, `t0-2m` and `t1-4`. Either tier 0 pairs with the same tiers 1–4,
  and the app downloads only the tier 0 it uses. 464 Colorado cells × 3 = 1,392 files, far under the
  19,000 guard, so no quarter split is needed. A 2 m tier 0 at twice the Dillon density would still be
  ~20 MB; the 20 MiB per-file guard fails such a cell loudly rather than splitting it (open question 3).
- **The cell holds classes, not styles.** Colours, dot density and type codes are the app's. So the look
  can change without a rebuild, and an on-demand builder only has to produce the same classes.
- **Grid alignment:** a 1 km buffer and origins snapped to 72 m. Neighbouring cells in one UTM zone share
  pixel grids at every tier, and edge polygons are judged on their full extent.
- **Lidar order: newest publication first** (ADR 0005). The spike read 2016 before 2020 by hand. The
  pipeline needs a rule, and the newest survey is the best guess at today's terrain.
- **Incremental runs, at most 48 cells each** (ADR 0006). During the Colorado backfill the schedule
  runs every 3 hours, so all of Colorado takes about 10 runs, roughly 30 hours. Then it switches to every
  3 hours in June only: cells built over 300 days ago are stale, so each is rebuilt about once a year
  (owner: "each region will run once per year or so").
- **Direct Upload, the owner's choice** (ADR 0003). The deploy job reads the live site back, checks every
  file, and uploads the whole folder with `wrangler pages deploy`, which sends only changed files. No
  site data is kept in GitHub. The token lives in the Environment `pages-production` and reaches only
  the wrangler step (ADR 0007).

## Future direction: on-demand cells (not built here)

The owner wants, later, cells outside Colorado built on request: the app asks a relay, the relay starts
this pipeline for those cells, and the result is cached for everyone. This change keeps that open:

- `build_cell` builds a cell from its id alone, with no region.
- The cell file holds only geometry per class.
- The plan already builds "covered and missing" cells, so a request could add cells to a region's list.

Nothing here designs the relay, its abuse limits or its trigger. The owner has concerns not yet discussed.

## Open questions

1. **Git integration or Direct Upload** (answered: Direct Upload, with the token as a secret; ADR 0003).
2. **Site name** (answered: project `slope-extracts` on `slope.timzander.com`).
3. **A cell over 20 MiB.** *Assumption:* it fails loudly, as no split is designed. Splitting `t0-2m` into
   quarters is the fix if a cell ever does.
4. **Colorado cells with no mountains** (~260 of 464). *Assumption:* every covered cell is built the same
   way. Compute is free, and a plains cell's files are small. Skipping them would need a rule for what
   counts as a mountain cell.
5. **Seams between lidar and the 10 m fill.** Where lidar stops, the elevation step can create false
   slopes along the seam. *Assumption:* accepted for now. Colorado's mountains have full lidar coverage
   in the pilot area, and the fill share is recorded per cell.
6. **Re-runs when 3DEP adds surveys** (answered: about yearly; the 300-day rule and a June schedule, ADR 0006).
7. **A separate Cloudflare account for slope-extracts.** A Pages token can't be scoped to one project, so
   a leaked token could deploy any Pages project on the account, maps.timzander.com included.
   - *Assumption:* the owner's account, with the Environment and one-step exposure as the guard.
   - A separate account is the option for real isolation; it is the owner's call (ADR 0003).
