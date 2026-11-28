# Design: catalogue-fail-fast

## Context

In runs 25, 119, 133 and 146, every catalogue request of one build job timed out (`urlopen error timed
out`), cell after cell, while the run's other jobs reached `datacube.services.geo.ca` normally. A job
whose path to the catalogue is broken stays broken for its lifetime; the next run's jobs are new
machines.

## Decisions

1. **Per job, remembered in the process.** A build job is one `build_cell` process; after one request
   has exhausted its retries, later requests in that process raise at once. The next run starts fresh.
2. **Only a catalogue that never answers.** The latch trips when all 4 tries of one request end in a
   timeout or a connection error, the failure seen in the four runs. An answer that arrives but can't be
   used (over 8 MiB, no `features`, a next page off the catalogue's host, over 20 pages, no trusted
   mosaic tile, an empty Vancouver probe) belongs to that request or cell, not to the job's path, so it
   fails only its own cell (spec review D1, D2).
3. **Only the catalogue.** The mosaic GeoTIFFs are read from S3, and 3DEP from TNM; neither is affected.

## Open questions

None.

## Risks / Trade-offs

- [A short blip ends a job's catalogue use for its remaining cells] → those cells are planned again by a
  later run, minutes later; nothing is lost.

## Review rounds

- Spec review, round 1 (2026-11-28): no blocker; 3 should-fix taken (only a catalogue that never
  answers trips the latch, not an answer that can't be used; an ADR task), consider items taken (the 4
  tries in the rule, a scenario for an unusable answer, the skipped cells' message and `failed.json`,
  tests reset the latch).
