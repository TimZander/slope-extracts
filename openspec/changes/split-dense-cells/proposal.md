# Proposal: split-dense-cells

## Why

Some very steep cells build a layer file too large to publish: over 20 MiB of gzip, or over 64 MiB of
JSON unpacked. Cloudflare Pages caps a file at 25 MiB, so the limits can't be raised. The stop-gap
(skip-oversize-t0-2m, ADR 0013) publishes such a cell without its `t0-2m` file, so those cells have
lost their 2 m bands. In Colorado (November 2026), `150_-431`'s `t0-2m` was about 25 MB of gzip and
`151_-431`'s unpacked to more than 64 MiB. Issue #10 asks for the lasting fix: publish such a cell as
four 0.125° quarter cells, as osm-extracts does for its dense cells.

## What Changes

- When any layer file of a cell would be over 20 MiB of gzip or 64 MiB of JSON, the build job writes
  the whole cell, all three layers, as its four 0.125° quarters, at
  `<region>/<cell>/<quarter>/<layer>.json.gz` with quarter `<qrow>_<qcol>` = floor(lat × 8) and
  floor(lon × 8). Each quarter holds the cell's polygons clipped to the quarter.
- A quarter file is a slope-cell version 1 file with one more key, `quarter`; `cell` stays the parent
  cell's id. Whole-cell files don't change.
- The manifest lists a quartered cell in a new region key, `quartered`, not in `cells`. Its entry keeps
  `recipe`, `built`, `sources` and `projects` once, and gives each of the four quarters its own
  `layers`, counted as a whole cell's are. Manifest `version` stays 1. A reader that knows only
  `cells` sees a quartered cell as not yet built and keeps working on every other cell.
- The stop-gap becomes the fallback: a quarter whose `t0-2m` is still over a limit is left out of that
  quarter with the same marker. A quarter's `t0-3m` or `t1-4` over a limit fails the cell.
- A whole cell the live manifest lists with its `t0-2m` left out is planned again, so the stop-gap's
  cells are rebuilt as quarters.
- The deploy job checks quarter files and entries as strictly as whole cells, reads quartered cells
  back from the live site, and writes the overview with quartered cells' tier 4.
- No limit changes, no recipe bump: a cell under the limits builds to the same bytes as before.

## Capabilities

### Modified Capabilities

- `slope-extract`: a cell whose layer file would be over a limit is published as four quarter cells,
  listed under the manifest's `quartered`.

## Impact

- `slope_extracts/build_cell.py`, `grid.py`, `cellfile.py`, `site.py`, `publish.py`, `overview.py`,
  tests, README.
- The manifest's and cell files' readers: a new region key `quartered`, and quarter files with a
  `quarter` key. Readers that ignore `quartered` keep working on unsplit cells and miss only the
  quartered ones. Owner's decisions, 2026-11-26. The manifest's reader needs its own matching change to
  read `quartered` and quarter files; that change belongs to the reader's repository, not this one.
- The build workflow file doesn't change.
