# Design: add-wyoming-utah-idaho

## Context

- See proposal.md for why. A region's coverage is every 0.25° cell its bounding box touches. The plan
  takes, region by region in list order, the cells to build, at most 48 per run, in jobs of 3.
- A build job writes each cell to `<out>/<cell>/`, by cell id alone, and the deploy job reads an
  artifact's cells into a map keyed by cell id. With one region a cell could never appear twice; with
  two, a job given `wyoming/164_-445` and `utah/164_-445` writes one folder, and the deploy job keeps
  only the second region's copy, so the first is never published and is planned again every run.
- Sizes with the owner's bounds: Colorado 464, Wyoming 464, Utah 420, Idaho 700 cells, 2,048 in all.
  Shared: Colorado–Utah 16 (column −437), Wyoming–Utah 36 (Wyoming's corner of 41–42° N), Wyoming–Idaho
  12 (column −445). Utah and Idaho meet on 42° N, a cell line, so they share none.

## Goals / Non-Goals

**Goals:** the three states built after Colorado; every region's copy of a border cell published.

**Non-Goals:** building a border cell once for both regions; clipping regions to state outlines; a
change to the cell format, the manifest's form or the workflow file.

## Decisions

### The owner's (2026-11-26)

1. **Idaho is its whole bounding box**, 42–49° N, 117.23–111.05° W: 700 cells, the panhandle included.
   About 38% of them lie in Montana, Oregon or Washington and are published under Idaho. Rejected:
   up to 45° N (300 cells, no panhandle or Bitterroots); osm-extracts' southern block (175 cells);
   several rectangles along the outline (more regions, and the outline can't be fetched here).
2. **Utah goes to 42° N**, its north line: 420 cells, Ogden and Logan included, with Wyoming's corner
   (41–42° N, 111.05–109.04° W, 36 cells) covered by both. Rejected: 41° N as osm-extracts' block.
3. **A border cell is built once per region**, as now, and published under each. Rejected: build once
   and publish twice (saves about 64 builds, 1.5 runs, but changes the plan and the deploy job's
   checks).
4. **Order: Colorado, Wyoming, Utah, Idaho.** Cells are built region by region in list order, so
   Wyoming starts once Colorado is done.

### Claude's

5. **The bounds**, inset 0.01° from a state line that lies on a cell line (as Colorado's are), so the
   box doesn't touch a row or column beyond it: Wyoming 41.01 / −111.04 / 44.99 / −104.06 (osm-extracts'
   values), Utah 37.01 / −114.04 / 41.99 / −109.06, Idaho 42.01 / −117.23 / 48.99 / −111.05. Each gives
   the cell counts above; no requirement depends on the exact insets.

## Open Questions

1. **How does the plan keep a job from holding a cell twice?** Assumption: it fills each job with the
   next cells in order, up to 3, and starts a new job when the next cell is already in the current
   one; cells keep their order and every region's copy is still planned, so a job may hold fewer than
   3 and a run at most 48 cells in more jobs. The other way: reorder the cells so copies never meet
   (moves cells out of coverage order).
2. **What does the deploy job do with a job list naming a cell twice?** Assumption: it fails,
   publishing nothing, for one region or two. A build job's folders are named by cell, so the deploy
   job can't tell two copies apart in one artifact. The other way: build into `<region>/<cell>/`
   folders (changes the artifact's layout and its checks).
3. **Does the manifest's reader need a change for a cell listed by two regions?** Assumption: no. Both
   copies are built from the same DEM and recipe, so they're the same polygons; a reader that loads
   one region sees each cell once, and one that loads two neighbouring regions may fetch and draw a
   border cell twice, which for an overlay of filled polygons looks the same. A reader that wants one
   copy can take the first region listing it. The manifest's form doesn't change.

## Risks / Trade-offs

- [The manifest grows to about 2.2 MB; the plan and deploy jobs read at most 4 MiB] → room for this;
  a few more states of this size would need the cap raised, which is a later change.
- [Idaho's box holds about 260 cells outside Idaho] → the owner's choice (decision 1); they cost about
  5 runs and 800 files.
- [64 border cells are built twice] → the owner's choice (decision 3); about 1.5 runs.
- [The backfill takes about 33 more runs, roughly four days after Colorado] → as ADR 0006 planned for
  new coverage; nothing else waits on it.

## Migration Plan

Merge; the next scheduled runs go on with Colorado, then Wyoming, Utah and Idaho. Rollback: revert;
the next deploy writes a manifest without the new regions, and its "fewer cells than live" check then
fails the deploy, so the owner would also need to accept the drop (a separate change).

## Review rounds

- Spec review, round 1 (2026-11-26): 1 blocker (the unchanged "the plan lists a cell twice" read as a
  cell id would refuse every border cell; now modified to "one region's cell"), 2 should-fix (the
  reader and a border cell's two copies, now open question 3; decisions 6 and 7 made open questions 1
  and 2), 1 consider (a job is otherwise filled to 3, now in the requirement).
