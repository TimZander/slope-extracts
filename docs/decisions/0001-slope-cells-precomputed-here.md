---
status: accepted
date: 2026-11-23
decision-makers: the owner (precomputed cells, a public sibling of osm-extracts, Colorado first); Claude (relayed by the coordinator session)
---
# Slope cells are precomputed per 0.25° cell in this public repository; the app compiles them

## Context and Problem Statement

garmin-map's slope shading (watch-tested 2026-11-23) needs slope classes from USGS 3DEP lidar.
Building one 0.25° cell takes ~8 minutes, 6 GB of memory and a few hundred MB of download, too heavy
for a phone. Someone has to compute the classes, somewhere the app can read them.

## Considered Options

- Precompute per cell in a public repository's GitHub Actions and serve a static Pages site, as
  TimZander/osm-extracts does
- Fetch the lidar and compute in the browser
- Precompute inside garmin-map (private, paid runner minutes)

## Decision Outcome

Chosen option: "precompute here", the owner's decision. Public-repository runners are free, a static
site costs nothing to read, and phones are the main platform. The owner ruled out direct lidar fetch in
the app ("No direct lidar fetch in the PWA").

Coverage is all of Colorado for now. Other areas are a later feature ("on-demand slope cells": a relay
asks this pipeline for a cell, built once for everyone). It is not designed here, but nothing in this
repository may rule it out. US-wide coverage and British Columbia are out of scope.

### Consequences

- Good, because the app downloads ~5 MB per steep cell and compiles it with its in-browser mkgmap.
- Good, because this repository's spec (`slope-extract`) states the format it writes. garmin-map's
  `slope-layer` states what it accepts.
- Bad, because the site holds Colorado only until on-demand cells exist.
