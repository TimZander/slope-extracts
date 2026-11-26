# Design: grid-v2

## Context

- See proposal.md. Today: `regions.json` (one box per region), `<region>/<cell>/…`, one `manifest.json`
  (version 1) with every region's coverage and cells, one `<region>/overview.json.gz` per region.
- Sizes (2026-11-26): a manifest entry is about 1 KB; Colorado is 464 cells over 12 tiles; Colorado,
  Wyoming, Utah and Idaho as boxes are 2,048 cells, 64 shared; British Columbia's box is 4,747 cells,
  about 2,400 in the province.
- Pages caps a deployment at 20,000 files (the site's guard is 19,000) and a file at 25 MiB.
- The deploy builds the deployment from file hashes (ADR 0023): a file at a new path with the same bytes
  needs no upload.

## Goals / Non-Goals

**Goals:** each cell once; areas of any shape; no tile file that grows with an area; no file for an
empty layer.

**Non-Goals:** British Columbia's elevation source; a version 1 manifest beside version 2; changing the
cell file's form or the recipe.

## Decisions

### The owner's (2026-11-26)

1. **An area is a list of hand-drawn boxes** (ADR 0028). Rejected: outline polygons from a boundary data
   set (exact, but outside data and a point-in-polygon test in the plan job); one box per area.
2. **Tiles are 2° × 2°, 64 cells** (ADR 0029). Rejected: 1° (four times the files to fetch zoomed out),
   4° (a dense tile's overview near the cap).
3. **The reader moves at once** (ADR 0030): `manifest.json` becomes version 2 and the region layout goes
   in the same deploy. Rejected: both layouts until the reader moves; version 2 on another project.
4. **A layer with no polygons has no file** (ADR 0031), its entry `bytes` 0 and `tiers` `{}`, in this
   change since the contract changes anyway.

### Claude's

5. **Cell ids, quarters and the recipe don't change**; non-empty files keep their bytes.
6. **`_headers`**: `/cells/*` (a day), `/tiles/:tile/index.json` (five minutes),
   `/tiles/:tile/overview.json.gz` (an hour), `/manifest.json` and `/hashes.json` (five minutes),
   `/LICENSE.txt` (an hour). No rule per area, so none overlaps.
7. **The plan reads `manifest.json`, then each listed tile's index** (12 for Colorado, a few hundred at
   four states), each checked and size-tied to the manifest, under "Waits on Cloudflare are bounded"
   (2-minute timeouts, two retries). The plan job's 10-minute limit is raised to 30, and tile indexes
   are read four at a time, so a few hundred small reads fit.
8. **Build jobs get plain cell ids** (`158_-425`), so a job can't be given one cell twice under two
   names.
9. **The first run reads the version 1 manifest**, keeps its cells by their v1 paths' hashes, reads back
   only `t1-4`, and turns a layer that has a file but no polygon into an empty one (a left-out marker
   stays one). Nothing is rebuilt or uploaded but the run's own cells. While the manifest is version 1,
   a run deploys even with nothing built (the plan says so in an output, and the deploy job's condition
   in `build.yml` reads it), so the move doesn't wait for a stale cell.
10. **The empty marker differs from the left-out one**: left out is `t0-2m` with tier `0` counted at 0;
    empty is any layer with `tiers` `{}`. Both have no file and `bytes` 0.

## Open Questions

1. **The manifest's and tile files' names and keys.** Answered (owner, 2026-11-26, confirmed from the
   app's side; ADRs 0032 and 0033): `manifest.json` `slope-extract` version 2 with tile entries of
   `covered`, `built`, `coveredMask`, `builtMask`, `indexBytes` and `overview`, and areas in
   `areas.json`'s order; `slope-tile` version 1 tile indexes with today's entries; `slope-overview`
   version 2 tile overviews.
2. **Order of building.** Assumption: areas in list order (the order the manifest lists them in), each area's cells in row then column order,
   a shared cell when its first area reaches it.
3. **A region's `only` list.** Assumption: dropped; unused since ADR 0010, and a small box does the same.
4. **Removing or shrinking an area.** Assumption: as removing a region today, the deploy refuses a site
   with fewer cells, so it needs its own change.

## Risks / Trade-offs

- [The reader breaks if this merges first] → the reader's change ships first (decision 3); this PR
  waits on it.
- [The plan makes one read per tile] → small files, and the tile count grows slowly.
- [An empty layer and a left-out layer both have `bytes` 0] → their `tiers` tell them apart (decision 10).

## Migration Plan

The reader's version 2 change ships; this merges; the next run reads the version 1 manifest, deploys
every cell at `cells/` by hash, writes tile indexes, tile overviews and a version 2 manifest, and drops
the region paths. Rollback is not a plain revert: the old code reads a version 2 manifest as invalid and
fails its plan, and empty layers have no v1 file. Going back needs a change that reads version 2 and
writes version 1 (rebuilding empty layers' files), or a rebuild from scratch with the first-deploy
switch; so the reader's version 2 must be proven before this merges.

## Review rounds

- Spec review, rounds 1–3 (2026-11-26), on the first draft (both layouts published): 4, 1 and 1
  blockers, all fixed. The owner's answers then removed the version 1 copies and added empty layers, so
  the delta was rewritten and reviewed again in rounds 4 and 5, with the owner's leave.
- Spec review, round 5 (2026-11-26): 1 blocker (the first run's empty-layer rule caught the left-out
  marker; now excluded), 5 should-fix (the first run's `cells/` paths take their v1 entries; the plan
  builds what a tile's `cells` and `quartered` don't list; a run deploys while the manifest is version
  1; the version 1 manifest's form kept; a re-read's size from its entry), 7 consider (3 taken; scenario
  names of modified requirements kept, as the archive requires).
- Spec review, round 6 (2026-11-26, the app having confirmed the contract): 2 blockers (two rules still
  forbade the version 1 deploy; no task for its `build.yml` part), 3 should-fix (a version 1 run deploys
  even when all its cells fail; the tile indexes named in the hash tie; a file with no polygons is
  invalid), 5 consider (taken: overview counts as a cell tier's, version 1's other keys ignored and a
  cell listed twice taking the first entry, a box edge on a cell line, a flat quarter in the split
  scenario).
- Spec review, round 7 (2026-11-26, with the owner's leave): 1 blocker (round 6's "a file with no
  polygons is invalid" also caught version 1 entries the first run turns empty; now build-job and tile
  index entries only), 1 should-fix (two scenarios now say the manifest is version 2), 4 consider (all
  taken).
- Conformance review, round 1 (2026-11-26): 4 hard fails, all tests the port of the region tests had
  dropped (the plan on a version 1 site, a split cell's left-out quarter, the yearly refresh, live
  split-entry attacks); restored and seen to catch their mutations. 3 soft fails: test citations fixed;
  an area's `tiles` now checked (tile ids the manifest lists, in order); tile-index reads retried twice
  on a network error or 5xx, as decision 7 says.
