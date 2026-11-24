---
status: accepted
date: 2026-11-23
decision-makers: the owner (set up Cloudflare later); Claude (the switch)
---
# Nothing runs until the owner turns building on

## Context and Problem Statement

The owner wants this repository merged now and its Cloudflare Pages project, domain, token and
GitHub Environment set up later. Merged as it was, the 3-hourly schedule would build up to 48 cells
a run, fail at the deploy job without credentials, and repeat every 3 hours.

## Considered Options

- A repository variable, `BUILD_ENABLED`, that the plan job's `if:` checks.
- Leave the schedule out until setup, and add it in a later PR.
- Let runs fail until setup.

## Decision Outcome

Chosen: the variable. It needs no second PR, it stays in the workflow as a switch to pause the
pipeline, and while it's off every job is skipped, so a run costs nothing and isn't red. A variable is
set by the repository's admins only, so it adds nothing a fork or a caller can steer (ADR 0007).

### Consequences

- Good, because merging before setup is harmless.
- Neutral: the owner sets one more thing, last, as `docs/setup.md` says.
