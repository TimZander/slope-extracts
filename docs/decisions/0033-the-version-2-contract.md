---
status: proposed
date: 2026-11-26
decision-makers: the owner (grid-v2 open question 1, confirmed from the app's side)
---
# The version 2 contract: `manifest.json` version 2, `slope-tile` indexes, `slope-overview` version 2

## Context and Problem Statement

The grid-v2 draft assumed the names and shapes of the new files the app reads. The app's side asked for
masks and `indexBytes` (ADR 0032), then confirmed the rest.

## Considered Options

- The draft's names: `manifest.json` (`slope-extract` version 2), `tiles/<tile>/index.json`
  (`slope-tile` version 1), `tiles/<tile>/overview.json.gz` (`slope-overview` version 2)
- A new top-level name (`index.json`) beside a version 1 `manifest.json` (moot once the switch is at once,
  ADR 0030)

## Decision Outcome

Chosen option: the draft's names, as the spec states them, with ADR 0032's tile entries. A built cell's
entry keeps version 1's form; empty and left-out layers are told apart by `tiers` (ADR 0031).

### Consequences

- Good, because the app has confirmed it reads exactly this.
- Bad, because any later change to these names is a change on both sides again.
