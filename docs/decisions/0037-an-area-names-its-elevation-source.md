---
status: accepted
date: 2026-11-26
decision-makers: Claude (the area's source, the mosaic, the catalogue gate), within the owner's ADR 0036
---
# An area names its elevation source; hrdem cells read NRCan's 1 m mosaic, gated by its catalogue

## Context and Problem Statement

BC is outside USGS 3DEP. NRCan publishes the HRDEM 1 m mosaic as 500 km cloud-optimised GeoTIFF tiles,
and the lidar projects behind it, in a STAC catalogue. Each cell must know which source to read, and
reading a mosaic tile for one of BC's 1,859 cells without lidar wastes most of a build.

## Considered Options

- The source by place (south of 49° N is 3DEP), or an explicit `source` per area
- Each lidar project's own GeoTIFFs, or the 1 m mosaic NRCan builds from them
- Read every cell's mosaic window, or ask the catalogue first whether any project meets the frame

## Decision Outcome

Chosen options:
- **`source` per area** (`3dep` or `hrdem`), with one source per cell, because the Alaska and Yukon
  borders and the Strait of Juan de Fuca aren't cell lines; a cell two sources cover is refused.
- **The 1 m mosaic**, because NRCan already orders overlapping projects; a cell reads one or two COGs.
- **The catalogue gate**, because for 40 sampled cells with lidar, a search of `hrdem-lidar` over the
  cell found a project in every one; with no project, the cell is built empty without a raster read.
  An empty mosaic answer fails the cell instead (the mosaic covers all of Canada: checked for all of
  BC's 172 edge cells), so an outage can't empty a good cell.

Only DTM URLs of the exact mosaic form are read, and project ids are 1 to 100 letters, digits, `_` and
`-` (NRCan's hold hyphens; the entry check widens to match, which the reader ignores).

### Consequences

- Good, because most empty BC cells take seconds.
- Bad, because the San Juan Islands' cells shared with BC show no slope on their U.S. side.
- Bad, because the build depends on NRCan's catalogue as well as TNM; an outage fails the cell, which
  keeps its previous files.
