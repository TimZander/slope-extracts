---
status: proposed
date: 2026-11-26
decision-makers: the owner (from the app's side, on grid-v2's draft contract); Claude (the bit order and hex form)
---
# A tile's manifest entry carries cell masks; the index's size is `indexBytes`

## Context and Problem Statement

The grid-v2 draft gave each tile in `manifest.json` only `covered` and `built` counts. The app plans from
the manifest alone, with no waiting: whether a view or a build is too large, has no data, or is outside
coverage; a build's 16-cell limit; refusing a box of over 10,000 cells, which can touch about 156 tiles.
With counts alone it can answer only to the tile, or must read every touched tile's index first.

## Considered Options

- Masks per tile: `coveredMask` and `builtMask`, 64 bits as 16 hex digits
- Counts only, as drafted
- Every cell listed in the manifest (back to a manifest that grows with the site)

## Decision Outcome

Chosen option: "masks per tile". Bit (row − 8 × trow) × 8 + (col − 8 × tcol) is set for each covered
(or built) cell, a split cell one bit; the 64-bit value is written as 16 lowercase hex digits, most
significant first, so bit 0 is the last digit's lowest bit. The offset is taken from the tile's first
row and column, not `row mod 8`, which some languages give as negative for negative rows. Also:
`index` is renamed `indexBytes` (a byte count, the app's cap for that read); `covered` and `built`
count a split cell once; `areas` keep `areas.json`'s order, which the app uses to name them, and their
boxes are only descriptive.

### Consequences

- Good, because the app decides by cell from the manifest, and reads tile indexes only for tiles with a
  built cell in view: one or two for a normal build, at most 16.
- Good, because a mask is about 40 bytes per tile.
- Bad, because the manifest and each tile index must agree, which the plan and deploy jobs check.
