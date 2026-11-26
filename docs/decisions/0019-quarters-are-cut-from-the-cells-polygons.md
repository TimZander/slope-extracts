---
status: accepted
date: 2026-11-26
decision-makers: the owner (split-dense-cells open question 1, 2026-11-26: the assumption the change proceeded on)
---
# A split cell's quarters are cut from its finished polygons, not built from the DEM

## Context and Problem Statement

A few very steep cells build a layer file too large to publish: over 20 MiB of gzip or 64 MiB of JSON.
Cloudflare Pages caps a file at 25 MiB, so the limits stay. ADR 0013 left such a cell's `t0-2m` out as
a stop-gap; issue #10 asked to split such a cell into four 0.125° quarters instead (change
split-dense-cells). How are a split cell's quarters made?

## Considered Options

- Build the cell once, as now, and clip its finished polygons to each quarter's box in map units
- Build each quarter from its own buffered DEM frame

## Decision Outcome

Chosen option: "cut from the cell". The polygons, already sieved, simplified and filtered by area, are
clipped to each quarter in map units: a polygon inside one quarter goes there unchanged, one across a
quarter line is cut, each piece a polygon in the cell's order, its new points rounded to map units. A
split cell holds exactly what it would hold whole. The clipping uses shapely and runs only in the build
job; the plan and deploy code stays standard library only. Rejected: a DEM build per quarter (four
times the reads, and the area filter would judge pieces of polygons, so quarter edges would differ from
cell edges).

### Consequences

- Good, because a split adds only an encode and gzip of the same polygons, about a minute against a
  cell's 15 to 17.
- Bad, because rounding at a quarter line can drop a sliver piece of under 3 points, as at a cell edge.
