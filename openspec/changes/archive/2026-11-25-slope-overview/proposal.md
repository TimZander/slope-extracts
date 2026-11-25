# Proposal: slope-overview

## Why

The app's slope layer can only draw slopes from zoom 9 in: further out a view meets too many cells
(a phone at zoom 8 sees about 2° × 3°, ~100 cells and 40+ MB). The owner wants slopes visible further
out (issue #321). The tier-4 polygons (30°+, 72 m) of a steep cell are small, about 200 polygons and
4,000 points, so one file per region holding every built cell's tier 4 stays a few megabytes.

## What Changes

- Each region with a built cell gets one overview file, `<region>/overview.json.gz`: gzip JSON, format
  `slope-overview` version 1, holding the tier-4 polygons of every built cell in that region, encoded
  like a cell.
- The deploy job writes it from the cell files it is about to publish (already checked), so it needs
  no build job and no new input. It is rebuilt on every deploy, never read back.
- The manifest gives each region its overview's `bytes`, `polygons` and `points`.
- `_headers` caches the overview for an hour.

## Capabilities

### Modified Capabilities

- `slope-extract`: a region overview file, its manifest entry and its cache header (the cell rule narrowed so each path has one).

## Impact

- `slope_extracts/overview.py` (new, standard library only), `publish.py` (assemble), `site.py`
  (manifest, headers, file list), tests.
- garmin-map's slope layer reads the overview in a second change (its own sdd flow): the cell format
  and manifest are a contract with it.
- One more file per region: far under the 19,000-file guard.
