---
status: accepted
date: 2026-11-25
decision-makers: the owner (skip the oversize file now, split dense cells later: "I'm OK with 1 and 2"); Claude (the manifest's marker for a left-out layer, and the build job deciding for both limits)
---
# Leave an oversize `t0-2m` layer out of its cell; split dense cells later

## Context and Problem Statement

Three scheduled runs in a row (2026-11-25) failed and nothing deployed. Two very steep Colorado cells
built a `t0-2m` layer too large to publish: `150_-431`'s was 25,061,558 bytes of gzip, over the 20 MiB
per-file limit, so the build job failed the cell; `151_-431`'s unpacked to more than 64 MiB, so the
deploy job refused the whole run. One oversize file in one cell blocked every other cell.

## Considered Options

- Skip the oversize file: publish the cell without its `t0-2m` and mark the layer absent in the manifest
- Split dense cells into four 0.125° quarter cells, as osm-extracts does for dense cells
- Raise the limits

## Decision Outcome

Chosen option: skip the oversize file, now; splitting dense cells is accepted for later (issue #10).
Raising the limits is rejected: Cloudflare Pages caps a file at 25 MiB, and `150_-431`'s file was
already 25.06 MB.

- Only `t0-2m` is left out (owner). Its bands are also in `t0-3m` at 3 m, so the cell keeps every tier
  and class. An oversize `t0-3m` or `t1-4` still fails its cell.
- The build job decides, for both limits: it has the JSON before gzipping it. The deploy job stays as
  strict as before, so a `t0-2m` file present in an artifact must still pass every check.
- The marker (Claude; the owner left its form open): the layer keeps its key with `bytes` 0 and tier
  `0` counting 0 polygons and 0 points, and the site holds no file. A gzip file is never 0 bytes, so
  `bytes` 0 can't mean anything else. The manifest keeps its shape, so a reader that requires every
  layer key and a tier-0 count still reads it. Rejected: dropping the key (breaks such readers), a new
  key such as `absent` (one more field for every reader and check, redundant with `bytes` 0). Only
  `t0-2m` may carry it, in exactly that form, in an artifact and in the live manifest.
- Assumption: a `t0-3m` or `t1-4` whose JSON is over 64 MiB now fails its cell in the build job, where
  it used to fail the whole deploy. The owner's "still fails as now" is read as "fails its cell".
- Found on the way: a cell that failed after writing a layer left a partial folder, which the deploy
  job refused, so one failed cell blocked the run despite "A failed cell keeps its previous files". The
  build job now removes a failed cell's folder.

### Consequences

- Good, because one oversize 2 m layer no longer blocks the deploy of every other cell.
- Good, because no limit, recipe or existing cell changes, and the manifest's shape is the same.
- Bad, because the cells left out lose their 2 m bands until issue #10 splits them.
- Bad, because a reader that requests every layer of every cell gets a 404 for a left-out `t0-2m`; it
  must check `bytes` first.
