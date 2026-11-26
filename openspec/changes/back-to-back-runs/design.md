# Design: back-to-back-runs

## Context

The build workflow already has `concurrency: { group: slope-extract, cancel-in-progress: false }`:
GitHub runs one run of the group at a time and keeps at most one waiting; a newer waiting run replaces
an older waiting one, and a running one is never cancelled.

## Decisions

1. **A 15-minute schedule, not a self-triggering run.** A run that starts the next one itself would need
   a `workflow_run` trigger or a token with `actions: write`, against "Nothing a pull request, a fork or a
   caller can steer runs the build workflow". A frequent schedule plus the existing concurrency group
   keeps one run waiting while one runs, so the next starts as soon as the last ends; at most 15 minutes
   pass between runs when the pipeline is idle.
2. **Minutes 7, 22, 37 and 52.** Not on the hour or the quarter, where GitHub's scheduler is busiest and
   delays runs.
3. **The same schedule after the backfill.** A run with nothing to build is the plan job alone, about a
   minute, and this public repository's Actions minutes are free; a slower schedule once the backfill is
   done is a later change if it is ever wanted.

## Open questions

None: the owner asked for back-to-back runs.

## Risks / Trade-offs

- [A waiting run is replaced by a newer one] → GitHub lists it as cancelled; it never ran, so nothing is
  lost, and a cancelled run sends no failure notice.
- [More deploys] → each run that built cells deploys once, as now; Cloudflare's Direct Upload sets no
  deployment limit that this pace reaches.
