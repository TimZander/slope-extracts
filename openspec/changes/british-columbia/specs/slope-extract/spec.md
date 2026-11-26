## ADDED Requirements

### Requirement: Elevation in an hrdem area comes from NRCan lidar only

A cell of an `hrdem` area SHALL read the HRDEM 1 m mosaic's DTM tiles that NRCan's STAC catalogue lists
for its buffered frame, as a 2 m mosaic, and no other elevation: a pixel no lidar covers SHALL have none.
Only DTM URLs under the mosaic's prefix SHALL be read. The entry SHALL record `dem10m` 0 and, as
`projects`, the catalogue's lidar projects meeting the frame.

#### Scenario: A cell partly covered by lidar

- **WHEN** lidar covers 30% of an `hrdem` cell's frame
- **THEN** its entry's `sources` are `lidar` 0.3, `dem10m` 0 and `none` 0.7, and its polygons lie only where the lidar is

#### Scenario: An untrusted URL in the catalogue's answer

- **WHEN** the catalogue lists a mosaic tile whose DTM is on another host
- **THEN** that tile is not read

### Requirement: An hrdem cell with no lidar project is built empty without reading elevation

When the catalogue lists no lidar project meeting an `hrdem` cell's buffered frame, the cell SHALL be
built with no raster read: its entry's `sources` SHALL be `lidar` 0, `dem10m` 0 and `none` 1, its
`projects` empty, and every layer empty, so it has no file.

#### Scenario: A cell in the far north

- **WHEN** no lidar project meets an `hrdem` cell's frame
- **THEN** no mosaic tile is requested, and the cell's entry lists all three layers as `bytes` 0 with no tiers, and the site holds no file for it

### Requirement: A cell has one elevation source

A cell's source SHALL be the `source` of the areas covering it. An areas list in which areas of two
sources cover one cell SHALL fail the plan job.

#### Scenario: A cell two sources cover

- **WHEN** a `3dep` area and an `hrdem` area both cover cell `196_-470`
- **THEN** the plan job fails and no cell is built

## MODIFIED Requirements

### Requirement: The areas list

The areas list SHALL be one file, `areas.json`, of at least one area, each with exactly `id` (lowercase
letters, digits and single hyphens, unique), `name` (not blank), `source` (`3dep` or `hrdem`) and
`boxes`: a non-empty list of bounds, numeric `south` < `north` (±90) and `west` < `east`
(±180). An area's coverage SHALL be every cell one of its boxes overlaps (an edge on a cell line
overlaps no cell beyond), each once, in row then column order. A list breaking a rule SHALL fail the
plan job.

#### Scenario: Colorado's coverage

- **WHEN** the list holds Colorado, source `3dep`, with one box, 37.01–40.99° N, 109.04–102.06° W
- **THEN** its coverage is the 464 cells of rows 148–163 and columns −437 to −409

#### Scenario: An area of two boxes

- **WHEN** an area has two boxes that overlap in 6 cells, covering 40 and 30 cells
- **THEN** its coverage is 64 cells, each once

#### Scenario: An invalid list

- **WHEN** an area's box has `south` above `north`
- **THEN** the plan job fails and no cell is built

### Requirement: Elevation comes from 3DEP lidar, then the 10 m DEM

A cell of a `3dep` area SHALL read every 3DEP 1 m lidar tile the TNM Access API lists for its buffered frame, as a 2 m
mosaic in which the newest publication wins where surveys overlap. Pixels no lidar covers SHALL take the
1/3 arc-second DEM. Only URLs under the 3DEP staged-products prefix SHALL be read. The entry SHALL record
each source's share of the frame and the lidar projects used.

#### Scenario: An untrusted URL in the API's answer

- **WHEN** the API lists a tile on another host
- **THEN** that tile is not read

#### Scenario: Overlapping surveys

- **WHEN** a 2016 and a 2023 survey cover the same tile
- **THEN** the 2023 survey's tile is read first

### Requirement: The site carries its sources notice

`LICENSE.txt` SHALL name USGS 3DEP (public domain) and NRCan's HRDEM, with the Open Government Licence –
Canada's statement "Contains information licensed under the Open Government Licence – Canada." and a
link to it, list every lidar project the built cells used, and link this repository. The manifest's
`attribution` SHALL credit both sources.

#### Scenario: The pilot's notice

- **WHEN** the Dillon cell is built from three lidar projects
- **THEN** `LICENSE.txt` lists those three projects

#### Scenario: A split cell's projects

- **WHEN** the only built cell is split and was built from two lidar projects
- **THEN** `LICENSE.txt` lists those two projects

#### Scenario: A Canadian cell's credit

- **WHEN** a built cell of an `hrdem` area used project `BC-Example_2019-1m`
- **THEN** `LICENSE.txt` lists that project under the Open Government Licence – Canada's statement, and
  `manifest.json`'s `attribution` names both USGS 3DEP and NRCan
