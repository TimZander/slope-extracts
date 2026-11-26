# Proposal: grid-v2

## Why

Cells are stored and listed by region (`<region>/<cell>/…`, one manifest entry per region), a layout
inherited from osm-extracts, whose regions follow its per-state source files. The elevation data here
is seamless, so a region is arbitrary, and it costs:

- a cell on a shared border is built and stored once per region (64 cells for Wyoming, Utah and Idaho);
- a region is one rectangle, so Idaho's box is 38% outside Idaho and British Columbia's about half;
- each region's overview and the one manifest grow with the region: British Columbia's overview would
  likely pass its 20 MiB cap, and the manifest the plan job's 4 MiB at about 4,000 cells.

The owner asked (2026-11-26) whether the site should be organised by the coordinate grid instead. This
draft says how, for the owner to decide before anything is built.

## What Changes

- **Areas replace regions.** `areas.json` lists named areas, each one or more boxes, so an area can
  follow an outline. The coverage is every cell an area covers; each cell is built and stored once.
- **Cells live on the grid**: `cells/<cell>/<layer>.json.gz`, quarters under them.
- **Tiles index the grid**: 2° × 2° tiles of 64 cells, each with `tiles/<tile>/index.json` (its cells'
  entries) and `tiles/<tile>/overview.json.gz` (their tier 4). No file grows with an area's size.
- **`index.json`**, manifest version 2, lists the tiles and the areas.
- **The v1 manifest and region paths stay** until the app reads the index: each area is published as
  a v1 region too, at the same bytes. A later change removes them.
- The plan, the build jobs' lists and the deploy work on cells, not region/cell pairs.

## Capabilities

### Modified Capabilities

- `slope-extract`: cells stored once on the grid, indexed by tiles, covered by areas; the v1 manifest
  kept beside it for now.

## Impact

- `regions.json` → `areas.json`; `slope_extracts/site.py`, `publish.py`, `overview.py`, `grid.py`,
  `build_cell.py` (job items), `deploy/pages.mjs` (the hash tie on `index.json` and tile indexes, re-reads from a listed path); `.github/workflows/build.yml` (job
  items only); tests, README, ADRs.
- **Contract:** a new index and tile files for the manifest's reader; the v1 manifest unchanged while
  it lasts. The reader's own change belongs to its repository.
- **Migration:** the first run republishes every cell at its `cells/` path by its v1 files' hashes:
  nothing is rebuilt, read back (but `t1-4`, as every run) or uploaded.
- **Files:** the v1 copies double the cell paths while they last (about 2,800 files at Colorado's
  464 cells); dropping them is the step before adding large areas.
- Supersedes the paused `add-wyoming-utah-idaho` change's fix for border cells (a cell is no longer
  per region); its owner decisions on bounds and order carry over as areas.
