# Design: catalogue-fail-fast

## Context

In runs 25, 119, 133 and 146, every catalogue request of one build job timed out (`urlopen error timed
out`), cell after cell, while the run's other jobs reached `datacube.services.geo.ca` normally. A job
whose path to the catalogue is broken stays broken for its lifetime; the next run's jobs are new
machines.

## Decisions

1. **Per job, remembered in the process.** A build job is one `build_cell` process; after one request
   has exhausted its retries, later requests in that process raise at once. The next run starts fresh.
2. **Any exhausted request, not only timeouts.** A request that fails four times (timeouts, connection
   errors, unreadable answers) means the catalogue can't be relied on for this job; the cells would fail
   anyway, only later.
3. **Only the catalogue.** The mosaic GeoTIFFs are read from S3, and 3DEP from TNM; neither is affected.

## Open questions

None.

## Risks / Trade-offs

- [A short blip ends a job's catalogue use for its remaining cells] → those cells are planned again by a
  later run, minutes later; nothing is lost.
