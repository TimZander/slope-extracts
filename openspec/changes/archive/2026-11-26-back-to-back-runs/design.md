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

4. **Reads past the CDN's cache.** The site's own cache rules let Cloudflare's edge keep
   `manifest.json`, `hashes.json` and tile indexes for 5 minutes and cell files for a day (seen: an old
   path answered from the edge cache with `cf-cache-status: HIT` after its deployment had none, and the
   same path with a query string answered 404, `BYPASS`). Runs 3 hours apart rarely met that window;
   back-to-back runs read the site seconds after a deploy. A stale manifest would make the plan rebuild
   the cells just built, and a stale `hashes.json` or re-read cell would fail the deploy's hash checks.
   Every pipeline read therefore carries a query string of its own; the app's reads are untouched.

## Open questions

1. **The schedule after the backfill.** ADR 0006 planned a June-only schedule once the backfill is
   done; it was never set (the cron has stayed every 3 hours). Assumption: every 15 minutes all year,
   so the yearly refresh happens as each cell turns 300 days old rather than in June. A slower
   schedule is a later change if the owner wants one.
2. **A cell that always fails.** It stays missing, so every run plans it again (ADR 0013): with runs
   back to back, a red run and a failure notice about every hour until it is fixed. Assumption:
   accepted, as faster notice; `BUILD_ENABLED=false` pauses the runs.

## Risks / Trade-offs

- [A waiting run is replaced by a newer one] → GitHub lists it as cancelled; it never ran, so nothing is
  lost, and a cancelled run sends no failure notice.
- [A run started by hand while one runs] → it waits like a scheduled one, and the next scheduled run
  replaces it within 15 minutes; the workflow takes no inputs, so the run that starts does the same work.
- [More deploys] → each run that built cells deploys once, as now; Cloudflare's Direct Upload sets no
  deployment limit that this pace reaches.

## Review rounds

- Spec review, round 1 (2026-11-26): no blocker; 4 should-fix, all taken (the newest waiting run starts,
  older ones are dropped; reads past the CDN cache, with what was seen; the schedule after the backfill
  and a cell that always fails as open questions with their assumptions), 3 consider, taken.
- Security review (2026-11-26): no finding. The cron adds no input, trigger, permission or secret. The
  query string is random (`secrets.token_hex`, `crypto.randomBytes`), never from the live site, and is
  appended after a path built from checked ids, so it can't change which file is read or where its
  bytes go; the size and hash checks are unchanged. Attack check: a real read of a path the edge still
  cached (an old version 1 cell) answered 404 with the query string, the live deployment's answer.
- Conformance review, round 1 (2026-11-26): no hard fail; every guard broken on purpose was caught. 3
  soft fails: the schedule test no longer requires the off-quarter minutes (decision 2, not the rule);
  a run started by hand is noted under the risks; a fake CDN driving the plan end to end was not added
  (the plan's reads go through `http_get`, which a test checks, and a real read past the edge cache was
  seen to answer from the live deployment).
