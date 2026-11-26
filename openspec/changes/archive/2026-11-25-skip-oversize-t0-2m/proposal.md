# Proposal: skip-oversize-t0-2m

## Why

The scheduled build has failed three runs in a row and nothing has deployed since. Two very steep
Colorado cells build a `t0-2m` layer that is too big: one cell's file is about 25 MB gzip (over the
20 MiB per-file limit, so the build job fails the cell), and another's unpacks to more than 64 MiB (so
the deploy job refuses the whole run). One oversize file in one cell blocks every other cell.

The limits can't be raised: Cloudflare Pages caps a file at 25 MiB. The owner chose (2026-11-25) to
publish such a cell without its `t0-2m` file now, and to split dense cells into quarter cells later
(issue #10).

## What Changes

- When a cell's `t0-2m` file would be over 20 MiB gzip or 64 MiB of JSON, the build job writes the cell
  without that one file, logs a warning naming the cell and the layer, and the cell counts as built.
  `t0-3m` and `t1-4` are written as before; an oversize `t0-3m` or `t1-4` still fails the cell.
- The cell's entry keeps its `t0-2m` key, marked left out: `bytes` 0 and tier `0` with 0 polygons and
  0 points. A real layer file is never 0 bytes, so a reader can tell the layer is absent without
  requesting it, and a reader that requires every layer key still finds one.
- The deploy job accepts a cell folder without `t0-2m` only when its entry marks it left out, publishes
  no file for it, and reads no file back for it from the live site. Everything else stays as strict.
- No limit changes; no recipe bump (no existing cell changes).

## Capabilities

### Modified Capabilities

- `slope-extract`: an oversize `t0-2m` layer is left out of its cell and marked so in the manifest.

## Impact

- `slope_extracts/build_cell.py`, `cellfile.py`, `site.py` (entry check, file list), `publish.py`
  (artifact check, read-back), tests.
- The manifest's readers: a cell's `t0-2m` may have `bytes` 0 and no file. The manifest stays valid in
  the same shape (every layer key, tier `0` counted).
