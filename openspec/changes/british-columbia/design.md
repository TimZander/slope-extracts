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
   are read. Project ids are kept only when they are letters, digits, `_` and `-` (NRCan's hold
   hyphens: `BC-BC_East_Kootenay_UTM11_2015-1m`); one that isn't is dropped and doesn't open the gate.
   The entry check (deploy job, live tile indexes) widens to the same pattern; the app's reader ignores
   `projects`, so this is no contract change.
6. **An empty answer is a failure, not "no lidar".** The mosaic's tiles cover all of Canada (checked
   2026-11-26: a tile for each of BC's 172 edge cells, the far north and the Alaska, Yukon and Victoria
   edges included), so the
   mosaic search runs for every `hrdem` cell and must list a tile; only then does an empty project list
   mean no lidar. A 200 answer with nothing (an outage, an API change) fails the cell, which keeps its
   files, instead of emptying a good cell for 300 days.
7. **`projects` are the projects meeting the frame**, for both sources (as 3DEP's always were: every
   tile touching the frame), from every page of the catalogue's answer (its `next` links, at most 20
   pages). A project the mosaic's order hides still appears in `LICENSE.txt`'s one
   list; crediting a source that may not show is the safe side of the licence.
8. **UTM zones 7 to 19.** NAD83 / UTM zones 7 to 11 exist (EPSG:26907–26911); the check widens.
9. **No recipe change.** Colorado's cells are untouched; `RECIPE` stays.

## Open questions

1. **BC's outline.** Assumption: 48 boxes, one per run of cells whose centre lies in a rough outline of
   the province, rows merged where equal (2,338 cells). They include slivers of Alberta (which has
   HRDEM lidar), and of Yukon and Alaska (almost none: built empty). South of 49° N, around Victoria,
   the border runs through cells shared with Washington (the San Juan Islands): as `hrdem` cells their
   Washington land has no slope, and a later Washington area couldn't cover them (one source per
   cell). Mixing sources in a cell is a later change if wanted.
2. **The credit's wording.** Assumption: `attribution` reads "Elevation: USGS 3D Elevation Program
   (3DEP), public domain; NRCan HRDEM, contains information licensed under the Open Government Licence
   – Canada", and `LICENSE.txt` carries the licence's own statement and link.
3. **What the reader says for an empty BC cell.** The manifest already tells it (`sources.none` 1,
   empty layers); whether the app says "no lidar here" is the app's decision. Assumption: no change to
   the contract.

## Notes

- The spec's Purpose still names USGS 3DEP only; a delta can't change it. The archive of this change,
  or a later edit through a change, updates it.

## Risks / Trade-offs

- [The catalogue is down during a build] → the cell fails and keeps its previous files, as a TNM
  outage does; the next run tries again.
- [NRCan adds lidar later] → an empty cell is rebuilt after 300 days like any other, and picks it up.
- [The run time] → 2,338 cells at 48 a run is about 49 runs; empty cells without a project take seconds.

## Review rounds

- Spec review, round 1 (2026-11-26): 2 blockers, both fixed. NRCan's project ids hold hyphens, which
  the 3DEP pattern and the deploy's entry check refuse (now letters, digits, `_` and `-`, with the
  entry check widened). 5 should-fix, taken: one project list in `LICENSE.txt`; the gate counts only
  kept ids; an empty catalogue answer fails the cell; the Washington cells by Victoria as part of open
  question 1; `projects` are those meeting the frame. Consider items taken where they touch the spec.
- Spec review, round 2 (2026-11-26): no blocker; 6 should-fix, taken: the 3DEP requirement also says
  "meeting" the frame; no trusted DTM URL fails the cell; the exact DTM URL pattern (so a `-dsm.tif` is
  refused); ids of 1 to 100 characters, one rule for the build and the entry check; the mosaic's cover
  of every edge cell measured; tests for an empty answer and a refused id. Paging is followed. Stopped
  here: the round found no blocker.
- Real cells built here from NRCan's live catalogue and mosaic (2026-11-26), each passing the deploy
  job's checks: `230_-522` (Stikine), no project, built empty in 1 s with nothing read; `200_-492`
  (Whistler), 7.5% lidar from 3 projects, 108 s, 0.9 MB of files; `203_-468` (Bugaboos), 54.7% lidar
  from `BC-BC_East_Kootenay_UTM11_2015-1m`, 624 s, 18 MB of files, whole.
- Security review (2026-11-26): no finding. The build job holds no secret and reads only DTM URLs of
  the exact mosaic form (another host, the `-dsm.tif` and a `../` path are refused, each tested); the
  catalogue's next links must stay on its host, at most 20 pages, answers capped at 8 MB; only plain
  project ids are kept; the deploy job checks every cell file as before; the workflow is unchanged.
- Conformance review, round 1 (2026-11-26): no hard fail; every gate broken on purpose was caught. 6
  soft fails, taken: a projects probe over Vancouver (4 projects live) must answer before any cell is
  built empty, once per job, so an empty projects answer can't empty BC's lidar cells for 300 days;
  a cell no area covers fails its build instead of defaulting to 3DEP; the 20-page and 8 MiB limits are
  in the requirement; tests now check that no polygon reaches the half without lidar and that a cell
  whose only project id is refused is built empty. An all-empty entry through the deploy is the flat
  cell's case, tested since grid-v2 (`test_a_flat_cells_layers_have_no_files`).
