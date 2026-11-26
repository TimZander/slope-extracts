## ADDED Requirements

### Requirement: The areas list

The areas list SHALL be one file, `areas.json`, of at least one area, each with exactly `id` (lowercase
letters, digits and single hyphens, unique), `name` (not blank) and `boxes`: a non-empty list of bounds,
each numeric `south` < `north` within ±90 and `west` < `east` within ±180. An area's coverage SHALL be
every cell one of its boxes touches, each once, in row then column order. A list breaking a rule SHALL
fail the plan job.

#### Scenario: Colorado's coverage

- **WHEN** the list holds Colorado with one box, 37.01–40.99° N, 109.04–102.06° W
- **THEN** its coverage is the 464 cells of rows 148–163 and columns −437 to −409

#### Scenario: An area of two boxes

- **WHEN** an area has two boxes that overlap in 6 cells, covering 40 and 30 cells
- **THEN** its coverage is 64 cells, each once

#### Scenario: An invalid list

- **WHEN** an area's box has `south` above `north`
- **THEN** the plan job fails and no cell is built

### Requirement: A cell is built and stored once, whatever covers it

The site's coverage SHALL be every cell some area covers. A cell SHALL be planned, built, published and
indexed once, at its own path, however many areas cover it.

#### Scenario: A border cell

- **WHEN** areas `colorado` and `utah` both cover cell `152_-437`, and it isn't built
- **THEN** the run plans it once, and the site holds one set of its files, under `cells/152_-437/`, and one index entry for it

### Requirement: Cells are indexed by 2-degree tiles

A tile SHALL be `<trow>_<tcol>` with trow = floor(latitude / 2) and tcol = floor(longitude / 2): 2° square,
64 cells. Each tile holding a covered cell SHALL have `tiles/<tile>/index.json` with exactly `format`
`slope-tile`, `version` 1, `tile`, `coverage` (its covered cells, in row then column order), and `cells`
and `quartered`, mapping its built cells to entries of the form a v1 manifest gives them.

#### Scenario: A cell's tile

- **WHEN** cell `158_-425` is built
- **THEN** it is listed in `tiles/19_-54/index.json`, the tile of 38–40° N, 108–106° W, whose coverage holds at most 64 cells

#### Scenario: A tile with nothing covered

- **WHEN** no area covers any cell of tile `20_-60`
- **THEN** the site holds no `tiles/20_-60/` files and the index lists no such tile

### Requirement: Each tile has an overview of its built cells' tier 4

A tile with a built cell SHALL have `tiles/<tile>/overview.json.gz`: gzip JSON with exactly `format`
`slope-overview`, `version` 2, `tile`, and `tiers` holding only tier `4`, class `30`: the tier-4 polygons
of the tile's built cells, in row then column order, a split cell's quarters by qrow then qcol, each
file's polygons in order. The deploy job SHALL write it from the `t1-4` files it publishes.

#### Scenario: A tile's overview

- **WHEN** a tile has two built cells with 3 and 5 tier-4 polygons
- **THEN** its overview holds 8 polygons in class `30` of tier `4`, the first cell's 3 first

### Requirement: The index lists tiles and areas

`index.json` SHALL hold exactly `format` `slope-extract`, `version` 2, `attribution`, `cellFormat`,
`layers`, `tiles`, mapping each tile with a covered cell to its `coverage` and `cells` counts, its
`index` bytes and, when it has one, its `overview` entry (`bytes`, `polygons`, `points`); and `areas`,
each with `id`, `name`, `boxes` and `tiles`: the tiles holding cells it covers.

#### Scenario: Colorado's index

- **WHEN** only Colorado is listed and 10 of its cells are built
- **THEN** `index.json`'s `areas` holds Colorado with its box and its 12 tiles, and the counts of `cells` across `tiles` sum to 10

### Requirement: The v1 manifest stays until the app reads the index

Until a later change removes it, the site SHALL also hold the v1 `manifest.json` and each area's v1
files: the area as a region, its `bounds` its boxes' outer edges, its coverage and built cells, each
built cell's files at `<area>/<cell>/…` (the bytes of its `cells/` files) and the area's v1 overview.

#### Scenario: Colorado's readers

- **WHEN** a run publishes after this change
- **THEN** `manifest.json` is still version 1 with region `colorado`, and `colorado/158_-425/t1-4.json.gz` holds the same bytes as `cells/158_-425/t1-4.json.gz`

## MODIFIED Requirements

### Requirement: A cell is three gzip JSON layer files

A cell SHALL be published as `cells/<cell>/t0-3m.json.gz`, `t0-2m.json.gz` (unless left out) and
`t1-4.json.gz`: gzip JSON with `format` `slope-cell`, `version` 1, `cell`, `layer`, and `tiers` mapping a
tier to its classes. A class SHALL map to polygons, each a list of rings, outer first. A ring SHALL be
integers: its first point in 24-bit map units (lat, lon), then each next point's difference, at least 3
points, closed implicitly. A split cell's files SHALL be its quarters'.

#### Scenario: A ring

- **WHEN** a ring has points (100, 200), (103, 199), (101, 190) in map units
- **THEN** it is written `[100, 200, 3, -1, -2, -9]`

#### Scenario: The same cell builds to the same bytes

- **WHEN** a cell is built twice from the same DEM
- **THEN** its files are byte for byte the same

### Requirement: A quarter file names its cell and its quarter

A quarter's layer SHALL be published as `cells/<cell>/<quarter>/<layer>.json.gz`, in the slope-cell
version 1 form of a whole cell's with exactly one more key, `quarter`, holding the quarter's id; `cell`
SHALL hold the parent cell's id. A whole cell's file SHALL have no `quarter` key.

#### Scenario: A quarter's 2 m layer

- **WHEN** quarter `316_-850` of cell `158_-425` is published
- **THEN** `cells/158_-425/316_-850/t0-2m.json.gz` holds `format` `slope-cell`, `version` 1, `cell`
  `158_-425`, `quarter` `316_-850`, `layer` `t0-2m` and `tiers`

### Requirement: A run builds missing and stale cells, at most 48

The plan job SHALL read the live site's index and tile indexes and choose, the areas in list order and
each area's coverage in order, each covered cell once that the index lists as built nowhere, with
another recipe number, as built more than 300 days ago, or whole with a layer left out, at most 48, in
jobs of 3 cells. With none to build, no build or deploy job SHALL run.

#### Scenario: A stale cell

- **WHEN** a cell was built with recipe 0 and the current recipe is 1
- **THEN** the next run builds it again

#### Scenario: The yearly refresh

- **WHEN** a cell was built 2025-11-01 and the plan runs on 2026-11-23
- **THEN** the run builds it again; on 2026-06-01 it would not have

#### Scenario: Nothing left

- **WHEN** every cell of every area is built with the current recipe
- **THEN** the run ends after the plan job

#### Scenario: A whole cell built without its 2 m layer

- **WHEN** the live index lists a cell in its tile's `cells`, built today with the current recipe, with its `t0-2m` left out
- **THEN** the run builds it again

#### Scenario: A split cell with a quarter's 2 m layer left out

- **WHEN** the live index lists a cell in its tile's `quartered`, built today with the current recipe, with one quarter's `t0-2m` left out
- **THEN** the run doesn't build it

#### Scenario: The first run after this change

- **WHEN** the live site has a v1 manifest and no `index.json`
- **THEN** the plan reads the v1 manifest's built cells as built, and builds none of them again for the change

### Requirement: Deploying adds to the live site

The deploy job SHALL create a deployment of Pages project `slope-extracts` on branch `main` from a
manifest naming every file of the site: every built cell's files, each tile's index and overview,
`index.json`, the v1 manifest and its areas' files, `hashes.json`, `404.html` and `LICENSE.txt`, with
`_headers` beside it. A run that built no cell SHALL deploy nothing.

#### Scenario: A second run

- **WHEN** a run builds one more cell
- **THEN** the deployed site holds both cells' files, and an index and tile indexes listing both

#### Scenario: Nothing built

- **WHEN** every cell of a run failed
- **THEN** nothing is deployed, and the live site stays as it was

### Requirement: The site sets its CORS and cache headers

`_headers` SHALL send `Access-Control-Allow-Origin: *` and `X-Content-Type-Options: nosniff` on every path,
and one `Cache-Control` per path: one day for cell files (`/cells/…`, and each area's v1 `/<area>/<cell>/…`),
an hour for `LICENSE.txt` and overview files, five minutes for `manifest.json`, `index.json`,
`hashes.json` and tile indexes. A missing path SHALL answer from `404.html`.

#### Scenario: Reading the headers file

- **WHEN** `_headers` is read
- **THEN** no path matches two rules that set `Cache-Control`

#### Scenario: The overview's cache

- **WHEN** `_headers` is read
- **THEN** `/colorado/overview.json.gz` and `/tiles/19_-54/overview.json.gz` each match one rule, which caches it for an hour, and
  `/colorado/158_-425/t1-4.json.gz` matches one, which caches it for a day

#### Scenario: A quarter's cache

- **WHEN** `_headers` is read
- **THEN** `/colorado/158_-425/316_-850/t0-2m.json.gz` and `/cells/158_-425/316_-850/t0-2m.json.gz` each match one rule, which caches it for a day

#### Scenario: The hashes' cache

- **WHEN** `_headers` is read
- **THEN** `/hashes.json` matches one rule, which caches it for five minutes

#### Scenario: A tile index's cache

- **WHEN** `_headers` is read
- **THEN** `/tiles/19_-54/index.json` and `/index.json` each match one rule, which caches it for five minutes

### Requirement: The manifest lists each region's coverage and built cells

`manifest.json` SHALL hold `format` `slope-extract`, `version` 1, an attribution, the cell format, the
layer names and each area's `id`, `name`, `bounds`, `coverage`, `cells` and `quartered`, as a region.
Each built whole cell SHALL map to its `recipe`, `built` date, `sources`, `projects`, and per layer its
`bytes` and per tier its `polygons` and `points`. A covered cell not yet built SHALL be in neither
`cells` nor `quartered`.

#### Scenario: A pilot run

- **WHEN** only four cells of Colorado are built, all whole
- **THEN** the manifest lists all 464 cells in Colorado's coverage, those four in its cells, and an empty quartered

## REMOVED Requirements

### Requirement: The regions list

**Reason**: Areas replace regions: a list of boxes per area, and cells stored once on the grid.
**Migration**: "The areas list"; `regions.json` becomes `areas.json`, Colorado's bounds its one box.
