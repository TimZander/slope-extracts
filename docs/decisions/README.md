# Decisions

Architecture and process decisions, one per file, as [MADR 4.0](https://adr.github.io/madr/)
records: `NNNN-short-title.md`, numbered in order. Copy [`template.md`](template.md) to start
one. A superseded record stays, with its status set to `superseded by NNNN`.

| No. | Decision | Status |
|---|---|---|
| [0001](0001-slope-cells-precomputed-here.md) | Slope cells are precomputed per 0.25° cell here; the app compiles them | accepted |
| [0002](0002-cells-as-gzip-json-of-delta-map-units.md) | A cell is three gzip JSON layer files of delta-coded 24-bit map units | accepted |
| [0003](0003-direct-upload-with-the-token-in-an-environment.md) | Pages Direct Upload from one step holding the token; its account-wide reach is the owner's call | superseded by 0023 |
| [0004](0004-python-with-hash-pinned-wheels.md) | Python; build jobs install hash-pinned wheels; plan and deploy install nothing | accepted |
| [0005](0005-newest-lidar-survey-wins.md) | Where lidar surveys overlap, the newest publication wins; 10 m fills gaps | accepted |
| [0006](0006-incremental-runs-48-cells-backfill-then-yearly.md) | At most 48 missing, stale or year-old cells per run; 3-hourly backfill, then June only | accepted |
| [0007](0007-no-workflow-inputs-and-least-privilege-jobs.md) | No workflow input, every job read-only, the token only where nothing outside steers | accepted |
| [0008](0008-nothing-runs-until-building-is-turned-on.md) | Nothing runs until the owner sets `BUILD_ENABLED` to `true` | accepted |
| [0009](0009-a-first-deploy-switch-for-a-placeholder-site.md) | A one-run `FIRST_DEPLOY` switch lets the first deploy replace a placeholder site with no `404.html` | accepted |
| [0010](0010-build-all-of-colorado.md) | Build all of Colorado: drop the pilot's `only` list | accepted |
| [0011](0011-a-region-overview-of-tier-4-written-by-the-deploy-job.md) | A per-region overview of every built cell's tier 4, written by the deploy job | accepted |
| [0012](0012-update-sdd-to-0-4-4.md) | Update sdd from 0.3.2 to 0.4.4 | accepted |
| [0013](0013-leave-out-an-oversize-t0-2m-layer.md) | Leave an oversize `t0-2m` layer out of its cell (marked `bytes` 0); split dense cells later (#10); limits not raised | superseded by 0014 |
| [0014](0014-split-dense-cells-with-the-skip-as-fallback.md) | A cell too large to publish whole is split into four quarters; leaving out `t0-2m` is the fallback | accepted |
| [0015](0015-quartered-cells-listed-apart-in-the-manifest.md) | The manifest lists split cells in a region map `quartered`, apart from `cells`; version stays 1 | accepted |
| [0016](0016-each-quarter-carries-its-own-layers.md) | Each quarter of a split cell carries its own `layers` in the manifest | accepted |
| [0017](0017-a-quarter-file-names-its-cell-and-quarter.md) | A quarter file keeps `cell` as its parent's id and adds `quarter`; slope-cell stays version 1 | accepted |
| [0018](0018-a-split-cell-quarters-all-three-layers.md) | A split cell quarters all three layers, not only the oversize one | accepted |
| [0019](0019-quarters-are-cut-from-the-cells-polygons.md) | A split cell's quarters are cut from its finished polygons, not built from the DEM | accepted |
| [0020](0020-whole-cells-with-a-layer-left-out-are-rebuilt.md) | The plan rebuilds a whole cell the live manifest lists with a layer left out | accepted |
| [0021](0021-every-region-has-quartered.md) | Every region has `quartered`, `{}` when it has no split cell | accepted |
| [0022](0022-a-quarter-holds-exactly-layers.md) | A quarter object in the manifest holds exactly `layers` | accepted |
| [0023](0023-deploy-from-a-manifest-of-hashes.md) | Deploy from a manifest of file hashes, uploading only what Cloudflare lacks | accepted |
| [0024](0024-hashes-in-a-side-file.md) | The files' hashes live in a side file, `hashes.json`, not in `manifest.json` | accepted |
| [0025](0025-the-token-reaches-two-curl-calls-only.md) | The Cloudflare token reaches only two curl calls; the upload token is masked and passed in a file | accepted |
| [0026](0026-wrangler-replaced-by-blake3-wasm.md) | Wrangler is replaced by its hashing package, `blake3-wasm` 2.1.5 | accepted |
| [0027](0027-the-purpose-edited-in-place.md) | The spec's Purpose is edited in place for the deploy credential's two calls | accepted |
| [0028](0028-areas-are-hand-drawn-boxes.md) | Areas are lists of hand-drawn boxes, not outlines | proposed |
| [0029](0029-tiles-of-two-degrees.md) | The grid is indexed by 2-degree tiles of 64 cells | proposed |
| [0030](0030-switch-to-manifest-version-2-at-once.md) | The site switches to manifest version 2 at once | proposed |
| [0031](0031-no-file-for-an-empty-layer.md) | A layer with no polygons has no file | proposed |
| [0032](0032-tile-entries-carry-cell-masks.md) | A tile's manifest entry carries cell masks; the index's size is `indexBytes` | proposed |
| [0033](0033-the-version-2-contract.md) | The version 2 contract: `manifest.json` version 2, `slope-tile` indexes, `slope-overview` version 2 | proposed |
| [0034](0034-check-the-live-site-once-deployed.md) | The deploy job checks the live site once deployed; a rollback stays manual | proposed |
| [0036](0036-no-lidar-no-data-in-canada.md) | Where Canada has no lidar, a cell is left empty: no 30 m fill | accepted |
| [0037](0037-an-area-names-its-elevation-source.md) | An area names its elevation source; hrdem cells read NRCan's 1 m mosaic, gated by its catalogue | accepted |
