# Design: british-columbia

## Context

Measured 2026-11-26 against the HRDEM 1 m mosaic's `coverage.gpkg` footprints (DTM layer, EPSG:3979),
per 0.25° cell whose centre lies in a rough BC outline:

| Latitude | Cells | Lidar ≥ 95% | Partial | None | Mean |
|---|---|---|---|---|---|
| 48–51° N | 448 | 13 | 260 | 175 | 24% |
| 51–54° N | 665 | 7 | 97 | 561 | 6% |
| 54–57° N | 534 | 4 | 98 | 432 | 7% |
| 57–60° N | 691 | 0 | 0 | 691 | 0% |
| All | 2,338 | 24 | 455 | 1,859 | 8% |

NRCan's STAC API (`datacube.services.geo.ca/stac/api`) lists the mosaic as 500 km tiles
(`hrdem-mosaic-1m`, items `<i>_<j>-mosaic-1m`, assets `dtm` as cloud-optimised GeoTIFF on
`canelevation-dem.s3.ca-central-1.amazonaws.com/hrdem-mosaic-1m/`), and the lidar projects behind it
(`hrdem-lidar`, e.g. `BC-BC_East_Kootenay_UTM11_2015-1m`). All under the Open Government Licence –
Canada 2.0.

## Decisions

1. **No lidar, no data** (owner, 2026-11-26). No 30 m (MRDEM-30) or 20 m (CDEM) fill: at 30 m, steep
   terrain is smoothed and much 30°+ terrain would read as gentler. A pixel with no lidar is `none`.
2. **An area names its source.** `source` per area, not a rule by latitude: the 49° N border is a cell
   line, but the Alaska and Yukon borders aren't, and an explicit source keeps each cell's source a
   choice made in `areas.json`. A cell two sources cover is refused rather than mixed.
3. **The 1 m mosaic, not each project.** NRCan's mosaic already orders overlapping projects; reading
   it is one or two COGs per cell, read at 2 m from their overviews like the 3DEP tiles.
4. **The catalogue's projects gate the read.** For 40 sampled cells with lidar, a STAC search of
   `hrdem-lidar` over the cell's box found at least one project in every one; for 25 cells without,
   it found one in 8. So no project means no lidar, and such a cell is built empty with no raster read
   (most of BC's 1,859 empty cells). A project that turns out to hold no pixel only costs the read.
5. **Untrusted answers.** Only DTM URLs matching
   `https://canelevation-dem.s3.ca-central-1.amazonaws.com/hrdem-mosaic-1m/<i>_<j>-mosaic-1m-dtm.tif`
   are read; project ids are kept only when they match a plain-name pattern, as 3DEP's are.
6. **UTM zones 7 to 19.** NAD83 / UTM zones 7 to 11 exist (EPSG:26907–26911); the check widens.
7. **No recipe change.** Colorado's cells are untouched; `RECIPE` stays.

## Open questions

1. **BC's outline.** Assumption: 48 boxes, one per run of cells whose centre lies in a rough outline of
   the province, rows merged where equal (2,338 cells). They include slivers of Alberta (which has
   HRDEM lidar), and of Yukon and Alaska (almost none: built empty).
2. **The credit's wording.** Assumption: `attribution` reads "Elevation: USGS 3D Elevation Program
   (3DEP), public domain; NRCan HRDEM, contains information licensed under the Open Government Licence
   – Canada", and `LICENSE.txt` carries the licence's own statement and link.
3. **What the reader says for an empty BC cell.** The manifest already tells it (`sources.none` 1,
   empty layers); whether the app says "no lidar here" is the app's decision. Assumption: no change to
   the contract.

## Risks / Trade-offs

- [The catalogue is down during a build] → the cell fails and keeps its previous files, as a TNM
  outage does; the next run tries again.
- [NRCan adds lidar later] → an empty cell is rebuilt after 300 days like any other, and picks it up.
- [The run time] → 2,338 cells at 48 a run is about 49 runs; empty cells without a project take seconds.
