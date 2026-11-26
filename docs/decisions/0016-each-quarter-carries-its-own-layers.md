---
status: accepted
date: 2026-11-26
decision-makers: the owner (2026-11-26, from the options Claude put; the recommended one)
---
# Each quarter of a split cell carries its own `layers` in the manifest

## Context and Problem Statement

A few very steep cells build a layer file too large to publish: over 20 MiB of gzip or 64 MiB of JSON.
Cloudflare Pages caps a file at 25 MiB, so the limits stay. ADR 0013 left such a cell's `t0-2m` out as
a stop-gap; issue #10 asked to split such a cell into four 0.125° quarters instead (change
split-dense-cells). What does a `quartered` entry give per quarter? The deploy job checks every file it reads back
from the live site against a size from the manifest, so each quarter file needs one.

## Considered Options

- Each quarter has full `layers`, as a whole cell has: per layer `bytes`, per tier `polygons` and `points`
- Each quarter has per-layer `bytes` only; counts once for the whole cell

## Decision Outcome

Chosen option: "full per-quarter layers", with `recipe`, `built`, `sources` and `projects` once
per cell: `{"recipe", "built", "sources", "projects", "quarters": {"<quarter>": {"layers": ...}}}`.
A reader can budget each quarter as it budgets a cell, and the same checks serve both. Rejected: bytes
only (a reader can't tell which quarter is heavy, and a second form to check).

### Consequences

- Good, because a quarter's entry is read and checked exactly as a whole cell's layers.
- Bad, because a split cell's entry is about four times a whole cell's.
