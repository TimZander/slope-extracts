## ADDED Requirements

### Requirement: The areas list

The areas list SHALL be one file, `areas.json`, of at least one area, each with exactly `id` (lowercase
letters, digits and single hyphens, unique, not `cells` or `tiles`), `name` (not blank) and `boxes`: a list of bounds, at most 40 areas,
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

- **WHEN** an area's box has `south` above `north`, or an area's id is `tiles`
- **THEN** the plan job fails and no cell is built

### Requirement: A cell is built and stored once, whatever covers it

The site's coverage SHALL be every cell some area covers. A cell SHALL be planned, built, published and
indexed once, at its own path, however many areas cover it.

#### Scenario: A border cell

- **WHEN** areas `colorado` and `utah` both cover cell `152_-437`, and it isn't built
- **THEN** the run plans and builds it once, and the site holds its files under `cells/152_-437/`, listed once in its tile's index; its v1 copies, while v1 lasts, are the same bytes under `colorado/` and `utah/`

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
of the tile's built cells in the order of a region's overview. The deploy job SHALL write it from the
`t1-4` files it publishes, and fail before the deployment is created when it would be over a cell
file's limits (20 MiB, 64 MiB of JSON).

#### Scenario: A tile's overview

- **WHEN** a tile has two built cells with 3 and 5 tier-4 polygons
- **THEN** its overview holds 8 polygons in class `30` of tier `4`, the first cell's 3 first

### Requirement: The index lists tiles and areas

`index.json` SHALL hold exactly `format` `slope-extract`, `version` 2, `attribution`, `cellFormat`,
`layers`, `tiles`, mapping each tile with a covered cell to its `covered` and `built` counts (one number each, split cells counted), its
`index` bytes and, when it has one, its `overview` entry (`bytes`, `polygons`, `points`); and `areas`,
each with `id`, `name`, `boxes` and `tiles`: the tiles holding cells it covers.

#### Scenario: Colorado's index

- **WHEN** only Colorado is listed and 10 of its cells are built
- **THEN** `index.json`'s `areas` holds Colorado with its box and its 12 tiles, and the tiles' `built` counts sum to 10

### Requirement: The v1 manifest stays until the app reads the index

Until a later change removes it, the site SHALL also hold the v1 `manifest.json` and each area's v1
files: the area as a region, its `bounds` its boxes' outer edges, its coverage and built cells, each
built cell's files at `<area>/<cell>/…` (the bytes of its `cells/` files) and the area's v1 overview.

#### Scenario: Colorado's readers

- **WHEN** a run publishes after this change
- **THEN** `manifest.json` is still version 1 with region `colorado`, and `colorado/158_-425/t1-4.json.gz` holds the same bytes as `cells/158_-425/t1-4.json.gz`

### Requirement: The live index is checked

The plan and deploy jobs SHALL read `index.json` (at most 4 MiB) and each tile index it lists (at most 4
MiB), and fail when any isn't of its form, a listed tile index answers other than 200, a tile index lists
a cell outside its tile, or its size or counts differ from the index's; a tile's `overview` entry is
used for nothing. The deploy job SHALL fail when it finds an `index.json` and the plan job didn't, or
the other way round.

#### Scenario: A tile index missing

- **WHEN** `index.json` lists tile `19_-54` and `tiles/19_-54/index.json` answers 404
- **THEN** the plan job fails and nothing is built

#### Scenario: The plan and deploy read different files

- **WHEN** the plan job read `index.json`, and in the deploy job `index.json` answers 404 while `manifest.json` answers
- **THEN** the deploy job fails, and no site is published from the v1 manifest

#### Scenario: A cell in the wrong tile

- **WHEN** `tiles/19_-54/index.json` lists cell `150_-431`
- **THEN** the plan job fails with "the live index is not valid"

### Requirement: Rules that read the live manifest read the index

Once the site has `index.json`, the rules that read the live manifest SHALL read it and its tile
indexes instead: the first-deploy switch reads `index.json`; the hashes tie checks `/index.json`'s and
each tile index's entries against the files read; "fewer cells than the live one" counts each cell once.
Before then they read `manifest.json`, as now.

#### Scenario: A stale index

- **WHEN** the live `hashes.json` was written with an older `index.json` than the live one
- **THEN** the deploy job fails and no deployment is created

#### Scenario: A border cell counted once

- **WHEN** the live index lists 400 cells, 16 of them covered by two areas, and a run builds 2 more
- **THEN** the new index lists 402 cells and the deploy goes ahead

#### Scenario: A cell no area covers any more

- **WHEN** an area is removed from `areas.json` and the live index lists cells only it covered
- **THEN** the new index would list fewer cells, so the deploy job fails and nothing is deployed

### Requirement: A cell's copies share its hash

A kept cell's file at a v1 path `hashes.json` doesn't list (an area that newly covers the cell) SHALL be
deployed with the hash of the same file at its `cells/` path, unread, and the same for the other way
round. A file Cloudflare lacks SHALL be read back from a path `hashes.json` lists, its `cells/` path
first; one listed at neither SHALL be read back as a kept file.

#### Scenario: An area newly covering a built cell

- **WHEN** `utah` is added to `areas.json`, covering kept cell `152_-437`, which `hashes.json` lists only at `cells/152_-437/` and `colorado/152_-437/`
- **THEN** the deployment names `utah/152_-437/t1-4.json.gz` with that file's hash, and the deploy job requests no `utah/` path

### Requirement: The first run moves the cells onto the grid

When the live site has a v1 manifest and no `index.json`, the deploy job SHALL keep every cell that
manifest lists and this run doesn't build, and deploy its files at its `cells/` path and every covering
area's v1 path by the hash `hashes.json` gives its v1 path in the first region listing it, reading back
only its `t1-4`, as a kept cell's.

#### Scenario: Colorado's cells move

- **WHEN** the live site holds 350 built Colorado cells under `colorado/` and no `index.json`, and a run builds 48 more
- **THEN** the deploy reads back only the 350 `t1-4` files from `colorado/…`, and the deployment holds all 398 cells at `cells/…` and at `colorado/…`, with an index listing all 398

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
each area's coverage in order, each covered cell once that its tile's index doesn't list, lists with
another recipe number, lists as built more than 300 days ago, or lists whole with a layer left out, at most 48, in
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
and one `Cache-Control` per path, by rules naming each area: one day for cell files (`/cells/…`, `/<area>/<cell>/…`),
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

### Requirement: The site lists its files' hashes

Each deploy SHALL write `hashes.json`: JSON with exactly `format` `slope-hashes`, `version` 1, and
`files` mapping every file of the deployment but itself and `_headers`, as `/<path>`, to its Pages
hash: the first 32 lowercase hex digits of the BLAKE3 hash of the file's base64 text followed by its
extension, the text after its name's last dot.

#### Scenario: A file's hash

- **WHEN** the site holds `a.json` with the two bytes `{}`
- **THEN** `hashes.json` maps `/a.json` to `ec47da64e7da6749028b38bc647d8a22`

#### Scenario: A cell file's hash

- **WHEN** the site holds `a.json.gz` with the two bytes `{}`
- **THEN** `hashes.json` maps `/a.json.gz` to `c4d46c65815aef2535f97005ed44d325`, hashed with extension `gz`

#### Scenario: A deployed site

- **WHEN** a run deploys a site of one cell of one area
- **THEN** `hashes.json` lists that cell's three files under `cells/` and under the area's v1 path, its
  tile's index and overview, the area's v1 overview, `index.json`, `manifest.json`, `404.html` and
  `LICENSE.txt`, each with its hash, and nothing else

### Requirement: A deploy reads back only what it needs

The deploy job SHALL read back from the live site `hashes.json`, each kept cell's `t1-4` files once from
its `cells/` path (a v1 path on the first run), for the overviews, and each kept file no path of which
`hashes.json` lists, and deploy them from the bytes read; it SHALL
take every other kept file's hash from `hashes.json` unread. With no live manifest it SHALL read no
`hashes.json`; one answering 404 SHALL list nothing. A kept cell is one the new manifest lists and
this run didn't build.

#### Scenario: A run after a run

- **WHEN** the live site holds one cell and its `hashes.json`, Cloudflare holds every kept hash, and a run builds another cell
- **THEN** the deploy job requests from the live site `index.json`, the tile indexes, `hashes.json` and
  the first cell's `t1-4` file at `cells/` only, and the deployment names both cells' files

#### Scenario: The first run after this change

- **WHEN** the live site holds one cell and no `hashes.json`, and a run builds another cell
- **THEN** the deploy job reads back and checks all three of the first cell's files, as before, and
  the new `hashes.json` lists both cells' files

#### Scenario: A hash not of its form

- **WHEN** the live `hashes.json` maps a kept file to `"zz"`
- **THEN** the deploy job fails and nothing is deployed

## REMOVED Requirements

### Requirement: The regions list

**Reason**: Areas replace regions: a list of boxes per area, and cells stored once on the grid.
**Migration**: "The areas list"; `regions.json` becomes `areas.json`, Colorado's bounds its one box.
