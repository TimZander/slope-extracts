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
- **THEN** the run plans and builds it once, and the site holds its files under `cells/152_-437/` only, listed once in its tile's index

### Requirement: Cells are indexed by 2-degree tiles

A tile SHALL be `<trow>_<tcol>` with trow = floor(latitude / 2) and tcol = floor(longitude / 2): 2° square,
64 cells. Each tile holding a covered cell SHALL have `tiles/<tile>/index.json` with exactly `format`
`slope-tile`, `version` 1, `tile`, `coverage` (its covered cells, in row then column order), `cells` and
`quartered`, mapping its built cells to their entries.

#### Scenario: A cell's tile

- **WHEN** cell `158_-425` is built
- **THEN** it is listed in `tiles/19_-54/index.json`, the tile of 38–40° N, 108–106° W, whose coverage holds at most 64 cells

#### Scenario: A tile with nothing covered

- **WHEN** no area covers any cell of tile `20_-60`
- **THEN** the site holds no `tiles/20_-60/` files and the manifest lists no such tile

### Requirement: Each tile has an overview of its built cells' tier 4

A tile with a built cell SHALL have `tiles/<tile>/overview.json.gz`: gzip JSON with exactly `format`
`slope-overview`, `version` 2, `tile`, and `tiers` holding only tier `4`, class `30`: the tier-4 polygons
of its built cells, whole or split, in row then column order, a split cell's quarters by qrow then qcol,
each file's polygons in its `t1-4` file's order, rings encoded as in a cell. A tile with no built cell
SHALL have no overview.

#### Scenario: Two built cells

- **WHEN** a tile has two built cells, with 3 and 5 tier-4 polygons
- **THEN** its overview holds 8 polygons in class `30` of tier `4`, the first cell's 3 first

#### Scenario: The same cells give the same bytes

- **WHEN** the overview is written twice from the same cell files
- **THEN** both are byte for byte the same

#### Scenario: No built cell

- **WHEN** a tile has covered cells but none built
- **THEN** the site holds no overview for it

#### Scenario: A split cell's tier 4

- **WHEN** a tile's only built cell, `158_-425`, is split, its quarters `316_-850`, `316_-849`, `317_-850` and `317_-849` holding 1, 2, 0 and 4 tier-4 polygons
- **THEN** its overview holds those 7 polygons, `316_-850`'s first and `317_-849`'s 4 last

### Requirement: The manifest lists tiles and areas

`manifest.json` SHALL hold exactly `format` `slope-extract`, `version` 2, `attribution`, `cellFormat`,
`layers`, `tiles`, mapping each tile with a covered cell to its entry, and `areas`, in `areas.json`'s
order, each with `id`, `name`, `boxes` and `tiles` (the tiles holding cells it covers). The boxes describe
an area; whether a cell exists is the tiles' to say.

#### Scenario: Colorado's manifest

- **WHEN** only Colorado is listed and 10 of its cells are built
- **THEN** `manifest.json` is version 2, its `areas` holds Colorado with its box and its 12 tiles, and the tiles' `built` counts sum to 10

#### Scenario: Areas in their list's order

- **WHEN** `areas.json` lists `colorado` then `utah`
- **THEN** the manifest's `areas` lists `colorado` then `utah`

### Requirement: A tile's entry counts and masks its cells

A tile's entry SHALL hold exactly `covered` and `built` (counts of cells, a split cell once),
`coveredMask` and `builtMask`, `indexBytes` (its index's size) and, when it has a built cell, `overview`
(`bytes`, `polygons`, `points`). A mask is 64 bits, bit (row − 8 × trow) × 8 + (col − 8 × tcol) set for
each such cell, a split cell one bit, written as 16 lowercase hex digits, bit 0 last.

#### Scenario: One built cell's mask

- **WHEN** tile `19_-54` (rows 152–159, columns −432 to −425) has cells `152_-432` and `158_-425` built, `158_-425` split
- **THEN** its `built` is 2 and its `builtMask` is `0080000000000001`: bit 0 for `152_-432`, bit 55 for `158_-425`

#### Scenario: Masks that disagree with the tile index

- **WHEN** a live tile index's `coverage` holds a cell whose bit the tile's `coveredMask` lacks
- **THEN** the plan job fails with "the live manifest is not valid"

#### Scenario: A tile overview's entry

- **WHEN** a tile's overview is 1,200 bytes with 8 polygons of 90 points
- **THEN** the tile's `overview` is `{"bytes": 1200, "polygons": 8, "points": 90}`

### Requirement: A layer with no polygons has no file

A layer, a whole cell's or a quarter's, whose tiers hold no polygon SHALL be published as no file, its
entry `bytes` 0 and `tiers` `{}`, and the deploy job SHALL request none. A layer file is never 0 bytes, so
a reader knows it is empty without requesting it. This is apart from the left-out marker, whose `tiers`
count tier `0`.

#### Scenario: A flat cell

- **WHEN** a cell on the plains has no slope over 30°
- **THEN** its entry gives each layer `{"bytes": 0, "tiers": {}}`, and the site holds no file for it

#### Scenario: An empty layer's file is there anyway

- **WHEN** a build job's entry gives `t1-4` `bytes` 0 and `tiers` `{}`, and its folder holds `t1-4.json.gz`
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: An empty layer with counts

- **WHEN** an entry gives a layer `bytes` 0 and `tiers` with any tier
- **THEN** it is the left-out marker when the layer is `t0-2m` with tier `0` at 0 and 0, and otherwise invalid

### Requirement: The live manifest is checked, with its tile indexes

The plan and deploy jobs SHALL read `manifest.json` and each tile index it lists (each at most 4 MiB),
and fail when any isn't of its form, a listed tile index answers other than 200 or isn't the size the
manifest gives it, a tile index lists a cell outside its tile, or its counts or masks differ from the manifest's.
A tile's `overview` entry is used for nothing. The deploy job SHALL fail when it reads another manifest
version than the plan job did.

#### Scenario: A tile index missing

- **WHEN** `manifest.json` lists tile `19_-54` and `tiles/19_-54/index.json` answers 404
- **THEN** the plan job fails and nothing is built

#### Scenario: A cell in the wrong tile

- **WHEN** `tiles/19_-54/index.json` lists cell `150_-431`
- **THEN** the plan job fails with "the live manifest is not valid"

#### Scenario: The plan and deploy read different versions

- **WHEN** the plan job read a version 1 manifest, and the deploy job reads a version 2 one
- **THEN** the deploy job fails and nothing is deployed

### Requirement: The first run moves the cells onto the grid

When the live manifest is version 1, the deploy job SHALL keep every cell it lists and this run doesn't
build, and deploy each file at its `cells/` path by the hash `hashes.json` gives its v1 path, reading
back only its `t1-4` there; a layer whose v1 counts hold no polygon becomes empty. It SHALL publish no
v1 path or v1 manifest.

#### Scenario: Colorado's cells move

- **WHEN** the live site holds 350 built Colorado cells under `colorado/` and a version 1 manifest, and a run builds 48 more
- **THEN** the deploy reads back only the 350 `t1-4` files from `colorado/…`, and the deployment holds all 398 under `cells/…`, nothing under `colorado/`, and a version 2 manifest listing all 398

#### Scenario: A v1 layer with no polygons

- **WHEN** a v1 cell's `t1-4` counts 0 polygons in every tier
- **THEN** its new entry gives `t1-4` `{"bytes": 0, "tiers": {}}`, and the site holds no `t1-4` file for it

## MODIFIED Requirements

### Requirement: A cell is three gzip JSON layer files

A cell SHALL be published as `cells/<cell>/t0-3m.json.gz`, `t0-2m.json.gz` and `t1-4.json.gz`,
each unless left out or empty,: gzip JSON with `format` `slope-cell`, `version` 1, `cell`, `layer`, and `tiers` mapping a
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

The plan job SHALL read the live manifest and tile indexes and choose, the areas in list order and each
area's coverage in order, each covered cell once that its tile doesn't list, lists with another recipe
number, lists as built more than 300 days ago, or lists whole with a layer left out, at most 48, in jobs
of 3 cells. With none to
build, no build or deploy job SHALL run.

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

- **WHEN** its tile index lists a cell in `cells`, built today with the current recipe, with its `t0-2m` left out
- **THEN** the run builds it again

#### Scenario: A split cell with a quarter's 2 m layer left out

- **WHEN** its tile index lists a cell in `quartered`, built today with the current recipe, with one quarter's `t0-2m` left out
- **THEN** the run doesn't build it

#### Scenario: The first run after this change

- **WHEN** the live manifest is version 1
- **THEN** the plan reads its built cells as built, and builds none of them again for the change

### Requirement: Deploying adds to the live site

The deploy job SHALL create a deployment of Pages project `slope-extracts` on branch `main` from a
manifest naming every file of the site: every built cell's files, each tile's index and overview, the
new manifest, `hashes.json`, `404.html` and `LICENSE.txt`, with `_headers` beside it. A run that built no cell SHALL deploy nothing.

#### Scenario: A second run

- **WHEN** a run builds one more cell
- **THEN** the deployed site holds both cells' files, and tile indexes and a manifest listing both

#### Scenario: Nothing built

- **WHEN** every cell of a run failed
- **THEN** nothing is deployed, and the live site stays as it was

### Requirement: The site sets its CORS and cache headers

`_headers` SHALL send `Access-Control-Allow-Origin: *` and `X-Content-Type-Options: nosniff` on every path,
and one `Cache-Control` per path:
one day for cell files (`/cells/…`, quarters' included), an hour for `LICENSE.txt` and tile overviews,
five minutes for `manifest.json`, `hashes.json` and tile indexes.
A missing path SHALL answer from `404.html`.

#### Scenario: Reading the headers file

- **WHEN** `_headers` is read
- **THEN** no path matches two rules that set `Cache-Control`

#### Scenario: The overview's cache

- **WHEN** `_headers` is read
- **THEN** `/tiles/19_-54/overview.json.gz` matches one rule, which caches it for an hour, and
  `/cells/158_-425/t1-4.json.gz` matches one, which caches it for a day

#### Scenario: A quarter's cache

- **WHEN** `_headers` is read
- **THEN** `/cells/158_-425/316_-850/t0-2m.json.gz` matches one rule, which caches it for a day

#### Scenario: The hashes' cache

- **WHEN** `_headers` is read
- **THEN** `/hashes.json` matches one rule, which caches it for five minutes

#### Scenario: A tile index's cache

- **WHEN** `_headers` is read
- **THEN** `/tiles/19_-54/index.json` matches one rule, which caches it for five minutes

### Requirement: The manifest lists quartered cells apart from whole ones

Each tile index SHALL have `quartered` (possibly empty) beside `cells`, mapping each split cell to its
`recipe`, `built`, `sources`, `projects` and `quarters`: exactly its four, qrow then qcol, each with exactly
`layers`, counted and checked as a whole cell's are, the left-out marker's rules included. A
`quartered` entry SHALL have no `layers`, and a `cells` entry no `quarters`. A cell SHALL be in at
most one of `cells` and `quartered`.

#### Scenario: A region with one split cell

- **WHEN** a run publishes `158_-424` whole and `158_-425` split
- **THEN** their tile index's `cells` lists `158_-424` only, and its `quartered` maps `158_-425` to an entry
  whose `quarters` holds `316_-850`, `316_-849`, `317_-850` and `317_-849`, each with per-layer `bytes`
  and per-tier `polygons` and `points`

#### Scenario: No split cell

- **WHEN** a tile has no split cell
- **THEN** its `quartered` is `{}`

#### Scenario: A cell listed both ways

- **WHEN** a live tile index lists a cell in both `cells` and `quartered`
- **THEN** the plan job fails with "the live manifest is not valid" and nothing is built

#### Scenario: A quartered cell missing a quarter

- **WHEN** a build job's entry for a split cell lists three quarters
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: Quarters out of order

- **WHEN** a live tile index's `quartered` entry lists `316_-849` before `316_-850`
- **THEN** the plan job fails with "the live manifest is not valid" and nothing is built

#### Scenario: A live entry with both forms

- **WHEN** a live tile index's `quartered` entry for a cell also has `layers`
- **THEN** the plan job fails with "the live manifest is not valid" and nothing is built

#### Scenario: The marker on a quarter's zoomed-out layer

- **WHEN** a live tile index gives a quarter's `t1-4` `bytes` 0 with tier `0` counted
- **THEN** the plan job fails with "the live manifest is not valid" and nothing is built

#### Scenario: A live manifest from before this change

- **WHEN** the live manifest is version 1 and its regions have no `quartered` key
- **THEN** the plan and deploy jobs read it as a manifest with no split cell

### Requirement: The deploy job writes the overview from the cells it publishes

The deploy job SHALL write each tile's overview from the `t1-4` files it is about to publish, after their
checks, and SHALL never read an overview back from the live site. It SHALL fail before the deployment
is created when an overview's file would be over 20 MiB or its JSON over 64 MiB, the limits of a cell
file.

#### Scenario: A run adds a cell

- **WHEN** a run builds one more cell of a tile
- **THEN** the tile's deployed overview holds that cell's tier-4 polygons with the others'

#### Scenario: An overview too large

- **WHEN** an overview's gzip file would be 21 MiB
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: A live manifest's overview entry

- **WHEN** the live manifest gives a tile an `overview` entry with any value
- **THEN** the plan and deploy jobs accept it, use none of it, and write the new entry from the new overview

### Requirement: The deploy job accepts only well-formed cells

The deploy job SHALL fail, publishing nothing, when:
- an artifact holds anything but `jobs.txt`, an optional `failed.json` and one folder per listed cell
- a whole cell's folder holds anything but `entry.json` and the layers its entry gives a size above 0
- any of these files is not regular, or is over 20 MiB
- a file is not exactly the slope-cell form of its path (classes per tier, points within its cell or
  quarter), or `entry.json` holds keys or values the manifest doesn't allow

#### Scenario: A hostile artifact

- **WHEN** a build job uploads an `index.html` beside its cells
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: A symbolic link

- **WHEN** a layer file is a symbolic link
- **THEN** the deploy job fails

#### Scenario: A stray key

- **WHEN** a cell file carries an extra top-level key
- **THEN** the deploy job fails

#### Scenario: A left-out layer's file is there anyway

- **WHEN** a cell's entry marks `t0-2m` left out but its folder holds a `t0-2m.json.gz`
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: A layer missing without the marker

- **WHEN** a cell's folder lacks `t0-2m.json.gz` and its entry gives `t0-2m` a size above 0
- **THEN** the deploy job fails and nothing is deployed

### Requirement: The deploy job accepts only well-formed split cells

A split cell's `entry.json` SHALL have `quarters` and no `layers`, a whole cell's `layers` and no
`quarters`. A split cell's folder SHALL hold exactly `entry.json` and its four quarter folders, real
folders, not links, each holding exactly the layers its quarter gives a size above 0. Each quarter file SHALL pass a whole
cell's checks against its quarter's id and bounds, to the same tolerance, and be the size its entry
gives. The deploy job SHALL fail, publishing nothing, otherwise.

#### Scenario: A quarter's point in the next quarter

- **WHEN** a quarter file of a split cell holds a point 100 map units inside another quarter of the same cell
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: A whole-cell file beside the quarters

- **WHEN** a split cell's folder also holds a `t1-4.json.gz` of the whole cell
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: A quarter folder that is a link

- **WHEN** a split cell's quarter folder `316_-850` is a symbolic link to a folder of valid files
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: An entry with both forms

- **WHEN** a build job's `entry.json` has both `layers` and `quarters`
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: A quarter file naming another quarter

- **WHEN** the file in quarter folder `316_-850` gives `quarter` `317_-850`
- **THEN** the deploy job fails and nothing is deployed

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

- **WHEN** a run deploys a site of one cell
- **THEN** `hashes.json` lists that cell's files under `cells/`, its tile's index and overview,
  `manifest.json`, `404.html` and `LICENSE.txt`, each with its hash, and nothing else

### Requirement: A deploy reads back only what it needs

The deploy job SHALL read back from the live site `hashes.json`, the kept cells' `t1-4` files (for the
tile overviews) and each kept file `hashes.json` doesn't list, and deploy them from the bytes read; it SHALL
take every other kept file's hash from `hashes.json` unread. With no live manifest it SHALL read no
`hashes.json`; one answering 404 SHALL list nothing. A kept cell is one the new manifest lists and
this run didn't build.

#### Scenario: A run after a run

- **WHEN** the live site holds one cell and its `hashes.json`, Cloudflare holds every kept hash, and a run builds another cell
- **THEN** the deploy job requests from the live site `manifest.json`, the tile index, `hashes.json`
  and the first cell's `t1-4` file only, and the deployment names both cells' files

#### Scenario: The first run after this change

- **WHEN** the live site holds one cell and no `hashes.json`, and a run builds another cell
- **THEN** the deploy job reads back and checks all three of the first cell's files, as before, and
  the new `hashes.json` lists both cells' files

#### Scenario: A hash not of its form

- **WHEN** the live `hashes.json` maps a kept file to `"zz"`
- **THEN** the deploy job fails and nothing is deployed

## REMOVED Requirements

### Requirement: The regions list

**Reason**: Areas replace regions: boxes per area, each cell stored once on the grid (owner, 2026-11-26).
**Migration**: "The areas list"; `regions.json` becomes `areas.json`, Colorado's bounds its one box.

### Requirement: The manifest lists each region's coverage and built cells

**Reason**: The version 1 manifest goes at once (owner, 2026-11-26); the cells' entries move to tile indexes.
**Migration**: "The manifest lists tiles and areas" and "Cells are indexed by 2-degree tiles".

### Requirement: Each region has an overview of its built cells' tier 4

**Reason**: Overviews are per tile, so none grows with an area.
**Migration**: "Each tile has an overview of its built cells' tier 4".

### Requirement: The manifest gives each region's overview

**Reason**: The overview's entry moves to its tile's entry in the manifest.
**Migration**: "The manifest lists tiles and areas".
