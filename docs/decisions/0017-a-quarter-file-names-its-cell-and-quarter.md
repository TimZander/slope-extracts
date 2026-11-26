---
status: accepted
date: 2026-11-26
decision-makers: the owner (2026-11-26, from the options Claude put; the recommended one)
---
# A quarter file keeps `cell` as its parent's id and adds `quarter`; slope-cell stays version 1

## Context and Problem Statement

A few very steep cells build a layer file too large to publish: over 20 MiB of gzip or 64 MiB of JSON.
Cloudflare Pages caps a file at 25 MiB, so the limits stay. ADR 0013 left such a cell's `t0-2m` out as
a stop-gap; issue #10 asked to split such a cell into four 0.125° quarters instead (change
split-dense-cells). A cell file has `cell`, and the deploy job checks every point lies in that cell. What identifies a
quarter's file, at `<region>/<cell>/<quarter>/<layer>.json.gz`?

## Considered Options

- `cell` stays the parent cell's id; a new key `quarter` (`<qrow>_<qcol>`, floor(lat × 8) and
  floor(lon × 8)) only in quarter files; version 1
- `cell` holds the quarter's id, no new key
- A slope-cell version 2 for quarter files

## Decision Outcome

Chosen option: "`cell` plus `quarter`", because whole-cell files don't change at all, and a quarter
file names both its cell and its quarter, so the deploy job checks its points against the quarter's
bounds. Rejected: `cell` holding the quarter's id (a quarter id looks like a cell id, so only the path
would tell the grid); a version 2 (readers would accept two versions for one extra key).

### Consequences

- Good, because readers of whole cells see no change.
- Bad, because a reader of quarter files must allow the one extra key.
