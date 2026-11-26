# Design: grid-v2

**A draft for the owner's decision (2026-11-26).** Nothing is built until the open questions below are
answered; the spec proceeds on the assumption each gives.

## Context

- See proposal.md. Today: `regions.json` (one box per region), `<region>/<cell>/…`, one `manifest.json`
  (version 1) holding every region's coverage and cells, one `<region>/overview.json.gz` per region.
- Sizes measured or estimated on 2026-11-26: a manifest entry is about 1 KB; Colorado is 464 cells;
  Colorado, Wyoming, Utah and Idaho as boxes are 2,048 cells, 64 of them shared; British Columbia's box
  is 4,747 cells (UTM zones 7–11), about 2,400 of them in the province.
- Pages caps a deployment at 20,000 files (the site's guard is 19,000) and a file at 25 MiB.
- The deploy builds the deployment from file hashes (ADR 0023): a file published at a second path with
  the same bytes is never uploaded again.

## Goals / Non-Goals

**Goals:** each cell once; areas of any shape; no tile file whose size grows with an area (the v1
manifest and overviews still do while they last); the current reader keeps working until it moves.

**Non-Goals:** British Columbia's elevation source; skipping files for empty layers; changing the cell
format; removing the v1 manifest (a later change, once the reader reads the index).

## Decisions (Claude's, each resting on an open question below)

1. **Cell ids, quarters and the recipe don't change**; only where files live and how they are listed.
2. **`index.json`** is the version 2 manifest, beside the v1 `manifest.json`, so a reader that knows
   only v1 is untouched.
3. **`_headers`** names each area instead of today's `/:region/:cell/*`, which would also match
   `/cells/<cell>/…` and `/tiles/<tile>/index.json`: `/cells/*` (a day), `/tiles/:tile/index.json`
   (five minutes), `/tiles/:tile/overview.json.gz` (an hour), and per area `/<area>/:cell/*` (a day)
   and `/<area>/overview.json.gz` (an hour). An area can't be called `cells` or `tiles`.
4. **The plan reads `index.json`, then each listed tile's index** (a few hundred small reads at four
   states). With no `index.json`, it reads the v1 manifest's cells as built (open question 6).
5. **Build jobs get plain cell ids** (`158_-425`, no region), so a job can't be given one cell twice
   under two names.
6. **The deploy's read-back stays as ADR 0023 has it**, by path. On the first run the `cells/` paths
   aren't on the site yet, so every built cell is read back from its first area's v1 path, checked, and
   published at both ("The first run moves the cells onto the grid"): about 15 minutes at 464 cells,
   once; later runs take kept files by hash.
7. **The v1 copies are written from the same bytes** as the `cells/` files, and hashed once.
8. **The live index replaces the live manifest** in every rule that reads the live site ("Rules that
   read the live manifest read the index"), with the v1 manifest only before the first run; the plan
   and deploy must agree on which they read.
9. **A cell's copies share its hash** ("A cell's copies share its hash"): an area that newly covers a
   built cell gets its v1 copies by the hash of the `cells/` files, with nothing read or uploaded.
10. **Shrinking an area** drops its cells from the index, which the "fewer cells" guard refuses; that
    needs a change of its own, as dropping a region does today.
## Open Questions (for the owner)

1. **What is an area?** Assumption: a list of boxes, drawn by hand (Idaho as three or four boxes
   following its outline). Other ways: an outline polygon from a public-domain boundary set (exact,
   but needs the data and a point-in-polygon test in the plan job); one box per area as today.
2. **How large is a tile?** Assumption: 2° × 2° (64 cells; Colorado spans 12 tiles). Smaller tiles
   (1°, 16 cells) mean more, smaller files for the reader to fetch; larger (4°, 256 cells) fewer but
   bigger overviews, near the cap for dense mountain ranges.
3. **How does the reader move over?** Assumption: both layouts are published until the app reads
   `index.json`, then a later change drops v1. Other ways: switch at once (the app must ship first, or
   miss cells until it does); v2 on another Pages project or host.
4. **The index's form.** Assumption: `index.json` as `slope-extract` version 2 (tiles and areas), tile
   indexes as `slope-tile` version 1 with v1-form cell entries, tile overviews as `slope-overview`
   version 2 (`tile` in place of `region`). Any of these names and keys is the reader's contract.
5. **Order of building.** Assumption: areas in list order, each area's cells in row then column
   order, a shared cell when its first area reaches it. Another way: steep tiles first, by a stored
   ranking.
6. **The first run.** Assumption: the v1 manifest's built cells count as built, so the change rebuilds
   nothing; their `cells/` copies are made from the v1 files read back.
7. **Empty layers.** Assumption: out of scope; every cell still writes its three files. Skipping files
   for layers with no polygons (plains, ocean) would cut the file count before large areas and is a
   contract change of its own.
8. **Is a region's `only` list kept?** Assumption: dropped. It held the four-cell pilot and has been
   unused since ADR 0010; an area of one small box does the same.
9. **A v1 region from an area of several boxes** gets the boxes' outer edges as `bounds`, with a
   coverage smaller than those bounds cover. Assumption: the reader uses `coverage`, not `bounds`, to
   know which cells exist. If it relies on bounds, areas should be one box each while v1 lasts.

## Risks / Trade-offs

- [Two layouts double the cell files while both are published] → about 2,800 at Colorado's size; the
  v1 copies must go before British Columbia (open question 3).
- [The plan job makes one read per tile] → small files; the tile count grows slowly (12 for Colorado).
- [A new contract for the reader] → v1 stays until it moves; the shapes are open question 4.

## Migration Plan

Merge; the first run reads the v1 manifest, republishes every built cell at `cells/` (no upload: same
hashes), writes the tile indexes and overviews and `index.json`, and keeps the v1 files. Rollback:
revert; the v1 manifest and files are still whole.

## Review rounds

- Spec review, round 1 (2026-11-26): 4 blockers (a border cell's v1 copies against "one set of files";
  the `hashes.json` scenario's file list; the first run reading `cells/` paths that don't exist yet;
  header rules that overlapped), 7 should-fix (reserved area ids, split cells in the counts, the live
  index's checks and sizes, the tile overview's cap, which live file the old rules mean, the dropped
  `only` list, v1 bounds from several boxes), 4 consider (wording taken; the failed-cell and file-count
  scenarios left, their rules still hold). All blockers and should-fix taken.
- Spec review, round 2 (2026-11-26): 1 blocker (a newly covering area's v1 copies would be read back and
  404; now "A cell's copies share its hash"), 4 should-fix (which files the old rules read, the plan
  and deploy reading different files, which v1 path the first run reads, cells no area covers any
  more), 4 consider (the index's count keys renamed `covered` and `built`, wording, tasks, numbering).
  All taken.
