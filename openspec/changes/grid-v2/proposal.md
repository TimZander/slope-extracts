# Proposal: grid-v2

## Why

Cells are stored and listed by region (`<region>/<cell>/…`, one manifest entry per region), a layout
inherited from osm-extracts, whose regions follow its per-state source files. The elevation data here
is seamless, so a region is arbitrary, and it costs:

- a cell on a shared border is built and stored once per region (64 cells for Wyoming, Utah and Idaho);
- a region is one rectangle, so Idaho's box is 38% outside Idaho and British Columbia's about half;
- each region's overview and the one manifest grow with the region: British Columbia's overview would
  likely pass its 20 MiB cap, and the manifest the plan job's 4 MiB at about 4,000 cells;
- every cell writes three files, even on the plains, where most layers hold nothing.

The owner asked (2026-11-26) whether the site should be organised by the coordinate grid instead, and
answered the draft's open questions the same day.

## What Changes

- **Areas replace regions** (owner): `areas.json` lists named areas, each one or more hand-drawn boxes,
  so an area can follow an outline. The coverage is every cell an area covers; each cell is built and
  stored once.
- **Cells live on the grid**: `cells/<cell>/<layer>.json.gz`, quarters under them.
- **2° tiles index the grid** (owner): 64 cells each, with `tiles/<tile>/index.json` (its cells' entries)
  and `tiles/<tile>/overview.json.gz` (their tier 4). No tile file grows with an area.
- **`manifest.json` becomes version 2**, listing tiles and areas, **at once** (owner): no v1 manifest or
  region paths stay. The reader must read version 2 before this merges.
- **A layer with no polygons has no file** (owner): its entry says `bytes` 0, `tiers` `{}`.
- The first run moves every built cell to its `cells/` path by its existing hash: nothing is rebuilt
  or uploaded, and only `t1-4` files are read back, as every run.

## Capabilities

### Modified Capabilities

- `slope-extract`: cells stored once on the grid, indexed by 2° tiles, covered by areas; manifest
  version 2; no file for an empty layer.

## Impact

- `regions.json` → `areas.json`; `slope_extracts/site.py`, `publish.py`, `overview.py`, `grid.py`,
  `build_cell.py` (job items, empty layers); `deploy/pages.mjs` (the hash tie on the manifest and tile
  indexes); `.github/workflows/build.yml` (job items only); tests, README, ADRs.
- **Contract:** a new manifest, tile indexes and overviews, and empty layers without files. The reader's
  matching change, in its own repository, must ship first: until it does, it reads version 2 as unknown.
- **Files:** each cell once, and fewer files for flat cells.
- Supersedes the paused `add-wyoming-utah-idaho` change (border cells are no longer per region); its
  owner decisions on bounds and order carry over as areas.
