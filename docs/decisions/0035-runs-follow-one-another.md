---
status: accepted
date: 2026-11-26
decision-makers: the owner ("keep the build pipeline running as soon as one finishes"); Claude (the 15-minute schedule, reads past the CDN cache)
---
# Runs follow one another: a 15-minute schedule, one run at a time, reading past the CDN's cache

## Context and Problem Statement

A run builds at most 48 cells and takes 25 to 60 minutes, but the workflow started every 3 hours
(ADR 0006), so most of each 3 hours built nothing. The owner asked to start the next run as soon as one
finishes. Runs that close together read the live site seconds after a deploy, inside Cloudflare's edge
cache (5 minutes for the manifest, a day for cell files): seen, an old path answered from the cache
after its deployment had none.

## Considered Options

- A run that triggers the next one (a `workflow_run` trigger, or dispatching with an `actions: write` token)
- A 15-minute schedule with the existing one-at-a-time concurrency group
- Keep every 3 hours

## Decision Outcome

Chosen option: "a 15-minute schedule", because the concurrency group already keeps one run waiting
while one runs, so the next starts as soon as the last ends, without a new trigger or a write token
(against "Nothing a pull request, a fork or a caller can steer runs the build workflow"). Every read of
the live site by the plan and deploy jobs carries a query string of its own, so the edge cache never
answers it. ADR 0006's schedule (every 3 hours, and June only after the backfill, never set) is
superseded; its batch size and 300-day refresh stand.

### Consequences

- Good, because a backfill runs about 8 times faster: roughly 40 cells an hour instead of 16.
- Good, because the plan and deploy always see the live deployment, never a cached file.
- Bad, because a cell that always fails turns a run red about every hour until it is fixed
  (`BUILD_ENABLED=false` pauses the runs).
- Bad, because an idle pipeline runs a plan-only job four times an hour (free on a public repository).
