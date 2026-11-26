# Proposal: deploy-from-hashes

## Why

Every deploy reads the whole live site back to the runner, checks every file, and hands the folder to
`wrangler pages deploy`. Today that takes about 2.5 s per cell (run 45750906054's deploy: 4 min 7 s to
assemble with about 100 cells read back), and Colorado's cells average 5.5 MB. Adding Wyoming, Utah and
Idaho (2,048 cells) would take about 85 minutes against the deploy job's 90, and 11 to 16 GB against
the runner's 14 GB of disk. The owner chose (2026-11-26) to fix the deploy before adding regions.

Pages builds a deployment from a manifest of path → file hash, and uploads only the hashes it lacks;
wrangler needs every file on disk only to compute those hashes.

## What Changes

- The site holds `hashes.json`: every deployed file's Pages hash (owner: hashes in a side file or the
  manifest, either; Claude chose the side file so `manifest.json`, the reader contract, doesn't change).
- The deploy job reads back only `hashes.json`, the kept cells' `t1-4` files (the overviews need them;
  about 2% of a cell's bytes) and any kept file `hashes.json` doesn't list. It writes only this run's
  files, hashes them, and builds the deployment manifest from those hashes and the live ones.
- It asks Cloudflare which hashes it lacks and uploads only those. A kept file Cloudflare no longer
  holds is read back and uploaded only if its hash matches.
- Wrangler is replaced by its hashing package, `blake3-wasm` 2.1.5 (1 package instead of 105), and a
  small Node script in the repository. The Cloudflare token reaches only two curl calls: one fetches a
  short-lived upload token for the project, one creates the deployment (owner, 2026-11-26). The upload
  token is masked and passed in a private file.
- The first run after this change finds no `hashes.json` and reads the site back once, as today.

## Capabilities

### Modified Capabilities

- `slope-extract`: the deploy builds a Pages deployment from file hashes and uploads only new files.

## Impact

- `slope_extracts/publish.py`, `site.py`; new `deploy/pages.mjs` and its tests; `deploy/package.json`
  and lockfile; `.github/workflows/build.yml` (high-risk: security review and attack tests) and
  `test.yml` (runs the Node tests); CLAUDE.md's token rule; README; docs.
- The deploy uses Cloudflare's Pages upload API as wrangler 3.114.17 does; Cloudflare doesn't document it
  as a public API.
- Readers: no change to `manifest.json` or cell files. One more file, `hashes.json`, on the site.
