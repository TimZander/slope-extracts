---
status: proposed
date: 2026-11-26
decision-makers: the owner
---
# The deploy job checks the live site once deployed, and a rollback stays manual

## Context and Problem Statement

The first run after grid-v2 merges moves every live cell onto the grid and switches the manifest to
version 2; a revert does not undo it. The owner wanted to be confident without watching the run by
hand. The tests use a fake site, and a dry run checks the files before they are deployed, not what the
live site then serves.

## Considered Options

- Watch the first run by hand and look at the live site
- A read-only check of the live site as the deploy job's last step, failing the run when it is wrong
- That check, rolling back to the previous deployment by itself when it fails
- Deploy to a preview first, check it, then promote it

## Decision Outcome

Chosen option: "a read-only check as the last step", because it needs no credential (the site is
public), runs the plan job's own checks on what is live, and turns a broken deployment into a red run
with GitHub's notice. A rollback by the job, or a promotion from a preview, would give the Cloudflare
token a third call, against ADR 0025's rule that it reaches the two curl calls only; a rollback in the
Cloudflare dashboard takes seconds, and the failing run says to do it.

### Consequences

- Good, because a broken deployment is found within minutes of the run, on every run, not only the first.
- Good, because the step holds no secret and reads only paths the manifest's checked ids give.
- Bad, because a broken deployment stays live until the owner rolls it back.
- Bad, because a run takes up to a minute more (one manifest read every 20 s until it is live, then 12
  tile indexes and a cell file per tile).
