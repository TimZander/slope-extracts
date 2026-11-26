# Design: split-dense-cells

## Context

- See proposal.md for why. Run 45748636703 (2026-11-26, the stop-gap's first run) published both known
  cells without `t0-2m`:
  - `150_-431`: `t0-2m` 25,061,558 bytes of gzip and 104,510,741 bytes of JSON; `t0-3m` 13.78 MB,
    `t1-4` 1.47 MB.
  - `151_-431`: `t0-2m` 85,357,762 bytes of JSON; `t0-3m` 11.32 MB, `t1-4` 1.12 MB.
- A quarter of those cells' `t0-2m` would average about 26 MB and 21 MB of JSON, well under 64 MiB,
  unless one quarter holds most of the cell's steep ground.
- Limits: 20 MiB of gzip per file, 64 MiB of JSON per cell file (the deploy job; the build job checks
  both since the stop-gap). Cloudflare Pages caps a file at 25 MiB.
- Every reader of the manifest reads a region's `cells` and fetches `<region>/<cell>/<layer>.json.gz`
  for each; a cell missing from `cells` reads as not yet built.

## Goals / Non-Goals

**Goals:** no layer dropped for size where a quarter fits; one oversize file never blocks the deploy;
readers that don't know quarters keep working on every whole cell.

**Non-Goals:** more than one level of splitting; splitting only some layers; changing the limits, the
recipe or any whole cell's bytes; changing the build workflow file.

## Decisions

### The owner's (2026-11-26)

1. **A quartered cell is listed in a new region map, `quartered`, not in `cells`;** the manifest stays
   `version` 1. A reader that knows only `cells` sees the cell as not yet built: a gap, never a 404.
   Rejected: keeping it in `cells` with a `split` list as osm-extracts does (existing readers would
   request whole-cell files that don't exist); a `quarters` key on a `cells` entry (the same 404s, and
   a strict reader may reject the entry); a version bump (every existing reader would reject the whole
   manifest, unsplit cells included).
2. **Each quarter carries full `layers`** (per layer `bytes`, per tier `polygons` and `points`), as a
   whole cell does; `recipe`, `built`, `sources` and `projects` are given once per cell. The deploy job
   needs each quarter file's size to check what it reads back. Rejected: per-quarter bytes only.
3. **A quarter file keeps `cell` as the parent's id and adds `quarter`;** slope-cell stays version 1.
   A whole cell's file is unchanged. Rejected: `cell` holding the quarter's id (a quarter id looks like
   a cell id), a slope-cell version 2.
4. **All three layers are quartered** when any one is over a limit, so a cell is in one form, whole or
   quartered. Rejected: quartering only the oversize layer (a reader would handle a mix per cell).

### Claude's

5. **The split replaces the skip; the skip stays as the fallback** (the owner asked Claude to decide
   this and say so here; ADR 0014). A cell over a limit is quartered rather than losing its `t0-2m`. If a quarter's `t0-2m` is still over a limit, that quarter is
   written without it, with the stop-gap's marker, so one file still can't block the deploy. A
   quarter's `t0-3m` or `t1-4` over a limit fails the cell, as a whole cell's did. Rejected: the split
   alone, failing a cell whose quarter is still too large (a dense enough cell would block its job
   again); splitting again into sixteenths (a second level for a case not yet seen).
6. **Quarters are cut from the whole cell's polygons** and **7. a whole cell with a layer left out is
   planned again**: open questions 1 and 2 below, since answered by the owner.
8. **No recipe bump:** no number in `recipe.py` changes, and a cell under the limits builds to the same
   bytes.
9. **The artifact's `entry.json` of a split cell** has the manifest entry's form plus `cell`, and the
   cell's folder holds only `entry.json` and the four quarter folders.
10. **The deploy job still accepts a whole cell with `t0-2m` left out**, in an artifact as in the live
    manifest: the build job no longer writes one, but the deploy job's checks don't change for whole
    cells, and the live manifest holds two such cells until they are rebuilt. A whole cell's marker
    can't get an oversize file published.
11. **Clipping runs in the build job only.** The quarter cut uses shapely, which only the build job
    installs; the code the plan and deploy jobs run (`site.py`, `publish.py`, `grid.py`, `recipe.py`,
    `cellfile.py`, `overview.py`) stays standard library only, so the deploy job, which holds the
    write token, imports no third-party code.
12. **The cost of a split.** Each layer is encoded and gzipped whole first, to judge the limits, and
    those bytes are dropped once the cell is found to split; nothing whole-cell reaches the disk. Only
    the polygons whose bounding box crosses a quarter line are clipped; the rest are sorted into their
    quarter by their box. A split adds one more encode and gzip of the same polygons, in four parts:
    for a `t0-2m` of 100 MB of JSON, roughly a minute, against a cell's 15 to 17 minutes (run
    45748636703), and memory for one layer's polygons twice at most, well within a runner's.
13. **The overview reads a split cell's four `t1-4` quarters** in place of its one `t1-4` file, ordered
    qrow then qcol, south-west first, as cells are ordered.

## Open Questions

All four answered by the owner on 2026-11-26, each as the assumption below (ADRs 0019 to 0022).

1. **Are quarters cut from the whole cell's polygons, or built from the DEM?** Assumption: cut. The
   cell is built once, as now; its polygons, already sieved, simplified and filtered by area, are
   clipped to each quarter's box in map units, each cut piece a polygon in the whole cell's order, and
   the new points on a quarter's edge rounded to map units. So a split cell holds exactly what it would
   whole, cut along the quarter lines. The other way: build each quarter from its own buffered DEM
   frame (four times the DEM reads, and the area filter would judge pieces of a polygon, not the
   polygon, so a quarter's edge would differ from the cell's other edges).
2. **Is a whole cell the live manifest lists with a layer left out planned again?** Assumption: yes, so
   the stop-gap's two cells are rebuilt as quarters on the next run without a recipe bump, which would
   rebuild all 464. A quartered cell with a quarter's layer left out is not planned again: it would
   build the same way each run. Without this rule the two cells stay whole without `t0-2m` until the
   yearly refresh.
3. **Is `quartered` always present, or only when a region has a split cell?** Assumption: always
   present, `{}` when empty, as osm-extracts always writes `split`, so a reader that knows quarters
   never has to test for the key. A live manifest without it (every manifest before this change) is read
   as having none. Either way an old reader ignores it.
4. **Does a quarter object hold anything but `layers`?** Assumption: exactly `layers`, so a later
   per-quarter field is an addition, not a change.

## Risks / Trade-offs

- [A reader that knows only `cells` shows no slope at all for a quartered cell, where the stop-gap gave
  it `t0-3m` and `t1-4`] → that is the owner's chosen trade (decision 1) for never serving a 404; the
  reader gains them once it reads `quartered`. Today that is two cells.
- [When a whole cell becomes split, its whole-cell files leave the site in the same deploy; a reader
  holding a manifest up to 5 minutes old (its cache time) gets 404s for that cell] → the same as any
  file a deploy drops today; the cell reappears from the new manifest.
- [A split cell is 12 files, not 3] → only cells over a limit split; the site is far from its 19,000.
- [Cutting rings at the quarter lines and rounding the new points could make a sliver ring of under 3
  points] → such a ring is dropped, as at the cell's edge today.
- [One quarter could hold most of a cell's steep ground and still be over 64 MiB in `t0-3m` or `t1-4`]
  → that cell fails and keeps its previous files, as before this change, and its job ends red so it is
  seen; no such cell is known.

## Migration Plan

Merge; the next scheduled run plans `150_-431` and `151_-431` (whole, `t0-2m` left out) again, builds
them as quarters, and the manifest moves them from `cells` to `quartered`. Rollback: revert; the next
run reads the `quartered` cells as not built (the old code doesn't know the key) and rebuilds them
whole with `t0-2m` left out.

## Review rounds

- Spec review, round 1 (2026-11-26): 1 blocker (the unchanged deploy-checks requirement refused every
  split cell; now modified), 6 should-fix (the quarter check's tolerance, the split entry's form, a
  whole cell's marker in an artifact, the marker's rules in quarters, decisions 6 and 7 made open
  questions, the reader's follow-up), 6 consider (ADR tasks, polygon order, a quarter object's keys,
  the read-back scenario's premise, quartered back to whole: all taken; renaming "An oversize 2 m layer
  is left out of its cell", which now applies to quarters, not taken: a REMOVED plus ADDED for a name).
- Spec review, round 2 (2026-11-26): 0 blockers, 6 should-fix (clipping kept out of the deploy job's
  code, a linked quarter folder, exact entry forms in the live manifest, the split's cost, the licence
  and file-count scenarios), 3 consider (the proposal now names "fits whole again"; the whole-cell
  marker scenario and the repeated 24 MB input left as they are). No round 3: no blocker.
- Conformance review, round 1 (2026-11-26): 0 hard fails, 5 soft fails. Four were test gaps (the gzip
  limit's boundary, a whole cell's `t0-3m` splitting, an empty quarter's files, a deploy over a manifest
  without `quartered`), fixed in tests; one was the order of a quartered entry's quarters, which the
  code required and the spec didn't state, now in the spec.
