# Decisions

Architecture and process decisions, one per file, as [MADR 4.0](https://adr.github.io/madr/)
records: `NNNN-short-title.md`, numbered in order. Copy [`template.md`](template.md) to start
one. A superseded record stays, with its status set to `superseded by NNNN`.

| No. | Decision | Status |
|---|---|---|
| [0001](0001-slope-cells-precomputed-here.md) | Slope cells are precomputed per 0.25° cell here; the app compiles them | accepted |
| [0002](0002-cells-as-gzip-json-of-delta-map-units.md) | A cell is three gzip JSON layer files of delta-coded 24-bit map units | accepted |
| [0003](0003-direct-upload-with-the-token-in-an-environment.md) | Pages Direct Upload from one step holding the token; its account-wide reach is the owner's call | accepted |
| [0004](0004-python-with-hash-pinned-wheels.md) | Python; build jobs install hash-pinned wheels; plan and deploy install nothing | accepted |
| [0005](0005-newest-lidar-survey-wins.md) | Where lidar surveys overlap, the newest publication wins; 10 m fills gaps | accepted |
| [0006](0006-incremental-runs-48-cells-backfill-then-yearly.md) | At most 48 missing, stale or year-old cells per run; 3-hourly backfill, then June only | accepted |
| [0007](0007-no-workflow-inputs-and-least-privilege-jobs.md) | No workflow input, every job read-only, the token only where nothing outside steers | accepted |
| [0008](0008-nothing-runs-until-building-is-turned-on.md) | Nothing runs until the owner sets `BUILD_ENABLED` to `true` | accepted |
| [0009](0009-a-first-deploy-switch-for-a-placeholder-site.md) | A one-run `FIRST_DEPLOY` switch lets the first deploy replace a placeholder site with no `404.html` | accepted |
