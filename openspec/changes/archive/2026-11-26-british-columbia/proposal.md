# Proposal: british-columbia

## Why

The owner asked (2026-11-26) to add British Columbia before more U.S. states. BC is outside USGS 3DEP.
Its lidar is published by Natural Resources Canada as the HRDEM 1 m mosaic (NRCan's catalogue, Open
Government Licence – Canada), which also holds BC's provincial lidar projects. Measured against the
mosaic's own coverage footprints, lidar covers about 8% of BC: 24 of 2,338 cells fully, 455 partly,
1,859 not at all, almost none north of 57° N. The owner decided (2026-11-26): where there is no lidar,
leave the cell empty, with no coarser fallback.

## What Changes

- **An area names its elevation source**: `areas.json` areas get `source`, `3dep` (as Colorado) or
  `hrdem`. A cell has one source; a list in which areas of two sources cover one cell is refused.
- **An `hrdem` cell reads the HRDEM 1 m mosaic's DTM only**, found through NRCan's STAC catalogue, as
  the 2 m mosaic the recipe already uses. A pixel with no lidar has no elevation and is in no class;
  there is no 10 m or 30 m fill (owner).
- **An `hrdem` cell with no lidar project is built empty without reading elevation**: when the
  catalogue lists no lidar project meeting the cell's frame, its entry says `none` 1 and every layer is
  empty, so it has no file.
- **The credit**: `LICENSE.txt` and the manifest's `attribution` credit NRCan's HRDEM under the Open
  Government Licence – Canada beside USGS 3DEP.
- **British Columbia**: a `british-columbia` area of 48 boxes following the province's outline at the
  cell grid, 2,338 cells, after Colorado.
- **Project ids** may hold `-` (NRCan's do); `projects` is defined, for both sources, as the lidar
  projects meeting the cell's frame, and the entry check widens to match.
- The cells' UTM frames accept NAD83 zones 7 to 19 (BC is zones 7 to 11).

## Impact

- `slope_extracts/sources.py` (the HRDEM source), `build_cell.py` (the source per cell, the empty
  build), `grid.py` (UTM zones), `site.py` (areas' `source`, the credit), `areas.json`, their tests.
- The site: about 75 more tiles and about 1,400 more cell files (only cells with lidar have files),
  well under the 19,000-file limit. About 49 runs to build BC.
- The manifest's form is unchanged: `source` stays in `areas.json`. Its `attribution` text changes. A
  built `hrdem` cell with `sources.none` 1 has empty layers: the reader draws nothing there, and may
  want to say why (its decision).
