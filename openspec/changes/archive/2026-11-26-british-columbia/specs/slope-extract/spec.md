## ADDED Requirements

### Requirement: Elevation in an hrdem area comes from NRCan lidar only

A cell of an `hrdem` area SHALL read the HRDEM 1 m mosaic's DTM tiles that NRCan's STAC catalogue lists
for its buffered frame, as a 2 m mosaic, and no other elevation: a pixel no lidar covers SHALL have none.
Only URLs `https://canelevation-dem.s3.ca-central-1.amazonaws.com/hrdem-mosaic-1m/<i>_<j>-mosaic-1m-dtm.tif`
SHALL be read. The entry SHALL record `dem10m` 0 and, as `projects`, the lidar projects of every page of
the catalogue's answer that meet the frame and have a valid id.

#### Scenario: A cell partly covered by lidar

- **WHEN** lidar of project `BC-Example_2019-1m` covers 30% of an `hrdem` cell's frame
- **THEN** its entry's `sources` are `lidar` 0.3, `dem10m` 0 and `none` 0.7, its `projects` are
  `["BC-Example_2019-1m"]`, and its polygons lie only where the lidar is

#### Scenario: An untrusted URL in the catalogue's answer

- **WHEN** the catalogue lists a mosaic tile whose DTM is on another host, or is its `-dsm.tif`
- **THEN** that tile is not read

#### Scenario: A project id that isn't a plain name

- **WHEN** the catalogue lists a project whose id holds `/` or a space
- **THEN** it is not recorded, and doesn't count as a project meeting the frame

### Requirement: The catalogue must answer before a cell is built empty

An `hrdem` cell's build SHALL fail, keeping its previous files, when the catalogue lists no mosaic tile
with a trusted DTM URL for its frame (the mosaic covers all of Canada, so an empty answer is a failure),
when a catalogue request fails or answers in over 20 pages or 8 MiB, or, before it is built empty, when
the projects search over a place known to have lidar (Vancouver) finds none.

#### Scenario: An empty answer

- **WHEN** the catalogue answers with no mosaic tile for an `hrdem` cell's frame
- **THEN** the cell fails, keeps its previous files, and is planned again by the next run

#### Scenario: The projects search answers empty everywhere

- **WHEN** the catalogue lists mosaic tiles, but its projects search finds none for a cell's frame and none over Vancouver
- **THEN** the cell fails and keeps its previous files, rather than being built empty

### Requirement: An hrdem cell with no lidar project is built empty without reading elevation

When the catalogue lists mosaic tiles but no lidar project meeting an `hrdem` cell's buffered frame,
the cell SHALL be built with no raster read: its entry's `sources` SHALL be `lidar` 0, `dem10m` 0 and `none` 1, its
`projects` empty, and every layer empty, so it has no file.

#### Scenario: A cell in the far north

- **WHEN** the catalogue lists a mosaic tile but no lidar project meeting an `hrdem` cell's frame
- **THEN** no mosaic GeoTIFF is read, and the cell's entry lists all three layers as `bytes` 0 with no tiers, and the site holds no file for it

### Requirement: A cell has one elevation source

A cell's source SHALL be the `source` of the areas covering it, and a cell no area covers SHALL fail
its build. An areas list in which areas of two sources cover one cell SHALL fail the plan job.

#### Scenario: A cell two sources cover

- **WHEN** a `3dep` area and an `hrdem` area both cover cell `196_-470`
- **THEN** the plan job fails and no cell is built

#### Scenario: A cell no area covers

- **WHEN** a build job is given cell `0_0`, which no area covers
- **THEN** that cell fails and nothing is read for it

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
each source's share of the frame and the lidar projects meeting it.

#### Scenario: An untrusted URL in the API's answer

- **WHEN** the API lists a tile on another host
- **THEN** that tile is not read

#### Scenario: Overlapping surveys

- **WHEN** a 2016 and a 2023 survey cover the same tile
- **THEN** the 2023 survey's tile is read first

### Requirement: The site carries its sources notice

`LICENSE.txt` SHALL name USGS 3DEP (public domain) and NRCan's HRDEM, with the Open Government Licence –
Canada's statement "Contains information licensed under the Open Government Licence – Canada." and a
link to it, list every lidar project the built cells list, in one list, and link this repository. The manifest's
`attribution` SHALL credit both sources.

#### Scenario: The pilot's notice

- **WHEN** the Dillon cell is built from three lidar projects
- **THEN** `LICENSE.txt` lists those three projects

#### Scenario: A split cell's projects

- **WHEN** the only built cell is split and was built from two lidar projects
- **THEN** `LICENSE.txt` lists those two projects

#### Scenario: A Canadian cell's credit

- **WHEN** a built cell of an `hrdem` area used project `BC-Example_2019-1m`
- **THEN** `LICENSE.txt` holds the Open Government Licence – Canada's statement and lists that project,
  and `manifest.json`'s `attribution` names both USGS 3DEP and NRCan

### Requirement: A built cell's entry gives its build and its layers

A whole cell's entry in a tile index SHALL hold exactly `recipe`, `built` (YYYY-MM-DD), `sources` (the
`lidar`, `dem10m` and `none` fractions), `projects` (the lidar projects meeting its frame, ids of 1 to 100 letters, digits, `_` and `-`) and `layers`: for each of
`t0-3m`, `t0-2m` and `t1-4`, its `bytes` and, per tier, its `polygons` and `points`. A split cell's
entry SHALL hold the same with `quarters` in place of `layers`.

#### Scenario: A whole cell's entry

- **WHEN** cell `158_-425` is built whole from one lidar project
- **THEN** its tile index's `cells` maps it to an object of exactly `recipe`, `built`, `sources`, `projects` and `layers`, `layers` holding all three layers

#### Scenario: A Canadian project id

- **WHEN** an `hrdem` cell's entry lists project `BC-Example_2019-1m`
- **THEN** the deploy job and the live tile-index check accept it
