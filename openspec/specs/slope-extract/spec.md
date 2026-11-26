# slope-extract Specification

## Purpose
Builds slope-angle class polygons per 0.25° cell from USGS 3DEP elevation and publishes them as a static
Cloudflare Pages site in the form garmin-map's slope layer reads, with its deploy credential confined to two plain API calls.

## Requirements

### Requirement: Cells share the OSM extract's grid

A cell SHALL be identified as `<row>_<col>` with row = floor(latitude × 4) and col = floor(longitude × 4),
covering 0.25° of latitude by 0.25° of longitude, the grid of TimZander/osm-extracts.

#### Scenario: A cell's id

- **WHEN** a place lies at 39.6° N, 106.1° W
- **THEN** it lies in cell `158_-425`, which covers 39.50–39.75° N and 106.25–106.00° W

### Requirement: Slope classes are named by their lower bound

A class SHALL be named by its lower slope bound in degrees. Its upper bound SHALL be the next class's
lower bound in the same tier, or none for the tier's last class. Slope SHALL be computed from the DEM's
gradient on a UTM grid (the cell centre's NAD83 zone). Pixels with no elevation SHALL be in no class.

#### Scenario: A plane at 41 degrees

- **WHEN** a DEM is a plane sloping 41°
- **THEN** its pixels are in class `40` (40–45°) at tier 0

### Requirement: Tier 0 holds every band and the cliffs

Tier 0 SHALL hold classes `30`, `35`, `40`, `45` (45–55°) and `55` (cliffs). Cliffs SHALL always come
from the 2 m DEM (sieve 6 px, simplify 1.8 m, minimum 8 m²). Bands SHALL come from the 3 m DEM in layer
`t0-3m` (sieve 10 px, simplify 2.7 m, minimum 18 m²) and, unless that layer is left out, from the 2 m DEM
in layer `t0-2m` (sieve 10 px, simplify 1.8 m, minimum 8 m²).

#### Scenario: A cone of known slopes

- **WHEN** a cell is built from a DEM of concentric rings at 32°, 37°, 42°, 50° and 62°
- **THEN** both tier-0 layers hold polygons in all five classes

### Requirement: Zoomed out, whole bands drop out, never small areas

Layer `t1-4` SHALL hold tiers 1–4 from the 3 m DEM block-averaged by 3, 6, 12 and 24. Tier 1 SHALL hold
`35`, `40`, `45` (45–55°) and cliffs `55` (2 m: sieve 50 px, simplify 7 m, minimum 1,200 m²). Tiers 2 and
3 SHALL hold `35`, `40` and `45` (45°+). Tier 4 SHALL hold one class, `30` (30°+). Sieve, simplify and
minimum area per tier SHALL be the values in `recipe.py`, the watch-tested v10 design.

#### Scenario: Tier 1 has no 30–35 band

- **WHEN** the cone is built
- **THEN** tier 1 holds classes `35`, `40`, `45` and `55`, tiers 2 and 3 hold `35`, `40` and `45`, and
  tier 4 holds only `30`

### Requirement: Polygons are clipped to their cell

The DEM SHALL be read with a 1 km buffer beyond the cell, on a grid snapped to 72 m multiples. Polygons
SHALL be simplified and filtered by area before being clipped to the cell, so a polygon crossing the edge
passes or fails the same in both cells. Every point SHALL lie within the cell.

#### Scenario: Points stay in the cell

- **WHEN** a cell is built
- **THEN** every point of every layer lies within the cell's bounds, to one map unit

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

### Requirement: A cell is three gzip JSON layer files

A cell SHALL be published as `cells/<cell>/t0-3m.json.gz`, `t0-2m.json.gz` and `t1-4.json.gz`,
each unless left out or empty: gzip JSON with `format` `slope-cell`, `version` 1, `cell`, `layer`, and `tiers` mapping a
tier to its classes. A class SHALL map to polygons, each a list of rings, outer first. A ring SHALL be
integers: its first point in 24-bit map units (lat, lon), then each next point's difference, at least 3
points, closed implicitly. A split cell's files SHALL be its quarters'.

#### Scenario: A ring

- **WHEN** a ring has points (100, 200), (103, 199), (101, 190) in map units
- **THEN** it is written `[100, 200, 3, -1, -2, -9]`

#### Scenario: The same cell builds to the same bytes

- **WHEN** a cell is built twice from the same DEM
- **THEN** its files are byte for byte the same

### Requirement: A run builds missing and stale cells, at most 48

The plan job SHALL read the live manifest and tile indexes and choose, the areas in list order and each
area's coverage in order, each covered cell once that its tile's `cells` and `quartered` don't list, lists with another recipe
number, lists as built more than 300 days ago, or lists whole with `t0-2m` left out (not empty), at most
48, in jobs of 3 cells. With none to
build, no build job SHALL run, nor a deploy job unless the live manifest is version 1.

#### Scenario: A stale cell

- **WHEN** a cell was built with recipe 0 and the current recipe is 1
- **THEN** the next run builds it again

#### Scenario: The yearly refresh

- **WHEN** a cell was built 2025-11-01 and the plan runs on 2026-11-23
- **THEN** the run builds it again; on 2026-06-01 it would not have

#### Scenario: Nothing left

- **WHEN** the live manifest is version 2 and every cell of every area is built with the current recipe
- **THEN** the run ends after the plan job

#### Scenario: A whole cell built without its 2 m layer

- **WHEN** its tile index lists a cell in `cells`, built today with the current recipe, with its `t0-2m` left out
- **THEN** the run builds it again

#### Scenario: A split cell with a quarter's 2 m layer left out

- **WHEN** its tile index lists a cell in `quartered`, built today with the current recipe, with one quarter's `t0-2m` left out
- **THEN** the run doesn't build it

#### Scenario: A flat cell

- **WHEN** its tile index lists a cell built today with the current recipe, every layer empty
- **THEN** the run doesn't build it

#### Scenario: The first run on the grid

- **WHEN** the live manifest is version 1
- **THEN** the plan reads its built cells as built, and builds none of them again for the change

### Requirement: Nothing a pull request, a fork or a caller can steer runs the build workflow

The build workflow's only triggers SHALL be `schedule` and `workflow_dispatch` with no inputs, and every
job SHALL have `contents: read` only. Only GitHub's checkout, upload-artifact and download-artifact
actions SHALL be used, each pinned by commit SHA, with no expression inside `run:`.

#### Scenario: Reading the workflow file

- **WHEN** the workflow file is read
- **THEN** its `on:` has exactly `schedule` and `workflow_dispatch`, no input, and no job can write

### Requirement: Runs wait until the owner turns building on

The build workflow's plan job SHALL run only when the repository variable `BUILD_ENABLED` is `true`.
Until then every run SHALL skip all its jobs and build, read and deploy nothing, so a repository
merged before its Cloudflare project and secrets exist doesn't fail on every scheduled run.

#### Scenario: Before setup

- **WHEN** a scheduled run starts and `BUILD_ENABLED` isn't set
- **THEN** the plan, build and deploy jobs are skipped and the run ends without failing

#### Scenario: After setup

- **WHEN** the owner has set `BUILD_ENABLED` to `true`
- **THEN** the plan job runs as before

### Requirement: Build-job packages are installed from pinned hashes

The build and test jobs SHALL install their Python packages only from wheels whose SHA-256 hashes
`requirements.txt` pins.

#### Scenario: A changed wheel

- **WHEN** a package index serves a wheel whose hash differs from the pinned one
- **THEN** the install fails and no cell is built

### Requirement: The deploy job accepts only well-formed cells

The deploy job SHALL fail, publishing nothing, when:
- an artifact holds anything but `jobs.txt`, an optional `failed.json` and one folder per listed cell
- a whole cell's folder holds anything but `entry.json` and the layers its entry gives a size above 0
- any of these files is not regular, or is over 20 MiB
- a file is not exactly the slope-cell form of its path (classes per tier, points within its cell or
  quarter), or `entry.json` holds keys or values an entry may not hold

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

### Requirement: A build job publishes only the cells the plan gave it

The deploy job SHALL take the plan's job list, and fail, publishing nothing, when an artifact is not
`cells-<n>` for a job the plan made, when its `jobs.txt` is not that job's planned list, or when the plan
lists a cell twice.

#### Scenario: An artifact the plan didn't make

- **WHEN** a build job also uploads `cells-99` with cells it wasn't given
- **THEN** the deploy job fails

### Requirement: A failed cell keeps its previous files

A cell that fails to build SHALL be left out of its job's artifact, the job SHALL end red, and the deploy
job SHALL keep that cell's previous files and entry.

#### Scenario: One cell of three fails

- **WHEN** one cell of a job fails and the other two build
- **THEN** the site publishes the two, keeps the failed cell's previous files, and the run is red

#### Scenario: A cell fails after writing a layer

- **WHEN** a cell fails on its `t1-4` file after its `t0-3m` file was written
- **THEN** the job's artifact holds no folder for that cell, and the deploy publishes the job's other cells

### Requirement: Deploying adds to the live site

The deploy job SHALL create a deployment of Pages project `slope-extracts` on branch `main` from a
manifest naming every file of the site: every built cell's files, each tile's index and overview, the
new manifest, `hashes.json`, `404.html` and `LICENSE.txt`, with `_headers` beside it. A run that built no cell SHALL deploy
nothing, unless the live manifest is version 1.

#### Scenario: A second run

- **WHEN** a run builds one more cell
- **THEN** the deployed site holds both cells' files, tile indexes listing both and a manifest counting both

#### Scenario: Nothing built

- **WHEN** the live manifest is version 2 and every cell of a run failed
- **THEN** nothing is deployed, and the live site stays as it was

### Requirement: Files read back from the live site are checked

Each file read back from the live site SHALL be the size its live entry gives it and pass the cell-file
checks. The deploy job SHALL fail before the deployment is created otherwise, or when:
- the live manifest is invalid, unless the first-deploy switch reads it as no manifest
- a file it lists answers 404
- it reads no manifest (a 404, or the switch) though the plan job read one
- the new site would leave out a built cell the live one holds

#### Scenario: A file changed on the live site

- **WHEN** a live cell file the deploy job reads back to assemble the site differs in size from the live manifest's
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: A live cell without its 2 m layer

- **WHEN** the live site lists a cell whose `t0-2m` is marked left out, `hashes.json` lists none of its files, and a run builds another cell but not it
- **THEN** the deploy job reads back that cell's `t0-3m` and `t1-4`, requests no `t0-2m`, and the new
  tile index keeps its entry as it was

#### Scenario: A live split cell

- **WHEN** the live site lists a split cell, `hashes.json` lists none of its files, and a run builds another cell
- **THEN** the deploy job reads back its quarters' files, each checked against its quarter's size and
  bounds, and its tile index keeps its entry under `quartered` as it was

#### Scenario: A whole cell becomes split

- **WHEN** the live site lists a cell whole, and this run builds it split
- **THEN** its tile index lists it in `quartered` only, the site holds its quarters' files and none
  of its whole-cell files, and the deploy goes ahead

#### Scenario: A split cell fits whole again

- **WHEN** the live site lists a cell split, and this run builds it whole
- **THEN** its tile index lists it in `cells` only, and the site holds its whole-cell files and none
  of its quarters'

#### Scenario: The switch forgives a manifest the plan job read

- **WHEN** the plan job read a valid manifest, and the deploy job, with `FIRST_DEPLOY` `true`, reads the manifest as none
- **THEN** the deploy job fails, and no site of this run's cells alone is published

#### Scenario: The custom domain stops answering

- **WHEN** the plan job read the live manifest but the deploy job gets a 404 for it
- **THEN** the deploy job fails, and no site of this run's cells alone is published

### Requirement: The site holds at most 19,000 files

The deploy job SHALL fail before the deployment is created when its manifest would name more than
19,000 files, `hashes.json` counted and `_headers`, which it doesn't name, not.

#### Scenario: Too many files

- **WHEN** the deployment's manifest would name 19,001 files
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: Counting a split cell's files

- **WHEN** a tile has one whole cell and one split cell with one quarter's `t0-2m` left out
- **THEN** the site's file count includes 3 files for the whole cell and 11 for the split one

#### Scenario: Counting the hashes file

- **WHEN** the deployment's manifest would name 18,999 files besides `hashes.json`
- **THEN** it names 19,000 files, and the deploy goes ahead

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

### Requirement: A first deploy can replace a placeholder site

While the repository variable `FIRST_DEPLOY` is exactly `true`, the plan and deploy jobs SHALL read a
live `manifest.json` that answers 200 with a body `json.loads` can't decode or parse as no manifest, and
build from scratch, but only when a path no site holds also answers 200. Otherwise such a body, and any
JSON body that isn't a valid manifest, SHALL fail the plan job.

#### Scenario: A placeholder that answers every path

- **WHEN** `FIRST_DEPLOY` is `true`, the live `manifest.json` answers 200 with an empty or HTML body, and a path no site holds answers 200 too
- **THEN** the plan job reports no manifest and plans cells from scratch, and the deploy job publishes a site of this run's cells with its own `404.html`

#### Scenario: The switch left off

- **WHEN** `FIRST_DEPLOY` is `false`, `True` or not set, and the live `manifest.json` answers 200 with an HTML body
- **THEN** the plan job fails with "the live manifest is not valid" and nothing is built

#### Scenario: The switch left on over a live site

- **WHEN** `FIRST_DEPLOY` is `true` and the live site has a valid manifest
- **THEN** the run reads it and keeps every cell it lists, as without the switch

#### Scenario: A pipeline site whose manifest answers HTML

- **WHEN** `FIRST_DEPLOY` is `true`, the live `manifest.json` answers 200 with an HTML body, and a path no site holds answers 404 (the site has a `404.html`)
- **THEN** the plan job fails with "the live manifest is not valid", and no site of this run's cells alone is published

#### Scenario: A broken manifest with the switch on

- **WHEN** `FIRST_DEPLOY` is `true` and the live `manifest.json` is JSON but not a valid manifest
- **THEN** the plan job fails with "the live manifest is not valid"

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

### Requirement: An oversize 2 m layer is left out of its cell

When a split cell's quarter's `t0-2m` file would still be over 20 MiB of gzip or 64 MiB of JSON, the
build job SHALL write that quarter without the file, log a GitHub `::warning::` annotation naming the
cell, the quarter and the layer, and count the cell as built. A quarter's `t0-3m` or `t1-4` file over
either limit SHALL fail its cell. A whole cell's layer SHALL never be left out: the cell is split. The
limits are those the deploy job checks; this rule changes none of them.

#### Scenario: A 2 m layer too large to publish

- **WHEN** a cell's `t0-2m` file would be 24 MB of gzip, and its other two layers are 5 MB each
- **THEN** the cell is split into its four quarters, and no layer is left out where its quarter's file fits

#### Scenario: A 2 m layer whose JSON is too large

- **WHEN** a cell's `t0-2m` file would be 15 MB of gzip unpacking to 70 MB of JSON
- **THEN** the cell is split, as above

#### Scenario: A 3 m layer too large to publish

- **WHEN** a cell's `t0-3m` file would be 24 MB of gzip
- **THEN** the cell is split, as above, where it used to fail

#### Scenario: A zoomed-out layer whose JSON is too large

- **WHEN** a cell's `t1-4` file would be 15 MB of gzip unpacking to 70 MB of JSON
- **THEN** the cell is split, as above, where it used to fail

#### Scenario: A quarter's 2 m layer still too large

- **WHEN** a split cell's quarter `316_-850` would have a 22 MB `t0-2m` file, and every other file is under 10 MB
- **THEN** that quarter's folder holds `t0-3m.json.gz` and `t1-4.json.gz` but no `t0-2m.json.gz`, its
  entry marks that `t0-2m` left out, the job logs a warning naming the cell, `316_-850` and `t0-2m`,
  and the job doesn't fail

#### Scenario: A quarter's 3 m layer too large

- **WHEN** a split cell's quarter would have a 24 MB `t0-3m` file
- **THEN** the cell fails, the build job leaves it out of the artifact, and the job ends red

#### Scenario: A quarter's zoomed-out layer whose JSON is too large

- **WHEN** a split cell's quarter would have a `t1-4` file of 15 MB unpacking to 70 MB of JSON
- **THEN** the cell fails, the build job leaves it out of the artifact, and the job ends red

### Requirement: The manifest marks a left-out layer

A left-out layer's entry SHALL keep its key, with `bytes` 0 and `tiers` holding only tier `0` with 0
polygons and 0 points; the site SHALL hold no file for it and the deploy job SHALL request none. A layer file is never 0 bytes, so a
reader can tell the layer is absent without requesting it. Otherwise `bytes` 0 SHALL mean an empty layer,
`tiers` `{}`; with any other `tiers`, on any layer, it SHALL make the entry invalid.

#### Scenario: A cell published without its 2 m layer

- **WHEN** a run publishes a cell whose `t0-2m` was left out
- **THEN** its entry's `t0-2m` is `{"bytes": 0, "tiers": {"0": {"polygons": 0, "points": 0}}}`,
  its other layers are listed as usual, and the site holds its `t0-3m` and `t1-4` files only

#### Scenario: The marker on another layer

- **WHEN** a build job's entry gives `t1-4` `bytes` 0 and tier `0` counted
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: A marker with counts

- **WHEN** a build job's entry gives `t0-2m` `bytes` 0 and tier `0` 12 polygons
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: The marker on another layer in the live manifest

- **WHEN** a live tile index gives a cell's `t0-3m` `bytes` 0 and tier `0` counted
- **THEN** the plan job fails with "the live manifest is not valid" and nothing is built

### Requirement: A cell too large to publish whole is split into its four quarters

When any of a cell's three layer files would be over 20 MiB of gzip or 64 MiB of JSON, the build job
SHALL write the cell, all three layers, as its four 0.125° quarters instead, log a GitHub `::warning::`
annotation naming the cell, and write no whole-cell layer file. A quarter's id SHALL be `<qrow>_<qcol>`
with qrow = floor(latitude × 8) and qcol = floor(longitude × 8). A cell under both limits SHALL be
written whole, as before.

#### Scenario: A 2 m layer too large to publish whole

- **WHEN** cell `158_-425`'s `t0-2m` file would be 24 MB of gzip and its other two layers 5 MB each
- **THEN** its folder holds `entry.json` and the folders `316_-850`, `316_-849`, `317_-850` and
  `317_-849`, each with its non-empty layers' files (here `t0-3m.json.gz`, `t0-2m.json.gz` and `t1-4.json.gz`), holds no whole-cell layer
  file, and the job logs a warning naming `158_-425`

#### Scenario: A zoomed-out layer's JSON too large to publish whole

- **WHEN** a cell's `t1-4` file would be 15 MB of gzip unpacking to 70 MB of JSON
- **THEN** the cell is written as its four quarters, as above

#### Scenario: A cell exactly at the limit

- **WHEN** a cell's largest layer file would be exactly 20,971,520 bytes of gzip and 67,108,864 bytes of JSON
- **THEN** the cell is written whole, as three layer files

### Requirement: A quarter holds its cell's polygons clipped to the quarter

Each quarter's layers SHALL hold the same tiers and classes as the whole cell's, with the polygons the
cell would hold whole, clipped to the quarter's bounds: a polygon inside one quarter SHALL be written
unchanged, and one crossing a quarter's edge SHALL be cut along it, each piece a polygon, in the whole
cell's order. Every point SHALL lie within its quarter. A quarter's layer with no polygon in a class SHALL list that class empty; one with no polygon
at all is empty, with no file.

#### Scenario: A polygon across the quarters' middle line

- **WHEN** a split cell holds a polygon crossing the line between quarters `316_-850` and `317_-850`
- **THEN** each of those quarters holds the part on its side, and every point of each lies within its quarter's bounds, to one map unit

#### Scenario: A quarter with no steep ground

- **WHEN** a split cell's quarter `317_-849` has no slope over 30°
- **THEN** its three layers are empty: its entry gives each `bytes` 0 and `tiers` `{}`, and no file is written for it

#### Scenario: The same split cell builds to the same bytes

- **WHEN** a split cell is built twice from the same DEM
- **THEN** its twelve files are byte for byte the same

### Requirement: A quarter file names its cell and its quarter

A quarter's layer SHALL be published as `cells/<cell>/<quarter>/<layer>.json.gz`, in the slope-cell
version 1 form of a whole cell's with exactly one more key, `quarter`, holding the quarter's id; `cell`
SHALL hold the parent cell's id. A whole cell's file SHALL have no `quarter` key.

#### Scenario: A quarter's 2 m layer

- **WHEN** quarter `316_-850` of cell `158_-425` is published
- **THEN** `cells/158_-425/316_-850/t0-2m.json.gz` holds `format` `slope-cell`, `version` 1, `cell`
  `158_-425`, `quarter` `316_-850`, `layer` `t0-2m` and `tiers`

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

- **WHEN** a run deploys a site of one cell, of one area whose coverage lies in one tile
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
- **THEN** the deploy job requests from the live site `manifest.json`, every tile index it lists,
  `hashes.json` and the first cell's `t1-4` file only, and the deployment names both cells' files

#### Scenario: The first run after this change

- **WHEN** the live site holds one cell and no `hashes.json`, and a run builds another cell
- **THEN** the deploy job reads back and checks all three of the first cell's files, as before, and
  the new `hashes.json` lists both cells' files

#### Scenario: A hash not of its form

- **WHEN** the live `hashes.json` maps a kept file to `"zz"`
- **THEN** the deploy job fails and nothing is deployed

### Requirement: The live hashes belong to the live manifest

The deploy job SHALL fail, creating no deployment, when the live `hashes.json` is over 4 MiB, not its
keys, format, version and `/<path>` → hash entries, or answers other than 200 or 404; when its
`/manifest.json` entry, or a tile index's, isn't the read file's hash; or when a file read back hashes to another entry
it gives. It SHALL ignore entries for paths it doesn't keep, and read back kept paths with none, but
on the first run on the grid, where a `cells/` path takes its v1 path's entry.

#### Scenario: Hashes from another deployment

- **WHEN** the live `hashes.json` was written with an older manifest than the live one
- **THEN** the deploy job fails and no deployment is created

#### Scenario: A `t1-4` file that doesn't match its hash

- **WHEN** a kept cell's `t1-4` file reads back with bytes whose hash differs from `hashes.json`'s
- **THEN** the deploy job fails and no deployment is created

#### Scenario: A path that is no longer kept

- **WHEN** the live `hashes.json` lists the whole-cell files of a cell this run builds split
- **THEN** the deploy job ignores those entries, and the new `hashes.json` lists the cell's quarters' files only

#### Scenario: A tile index from another deployment

- **WHEN** a live tile index of the size the manifest gives it doesn't hash to its `hashes.json` entry
- **THEN** the deploy job fails and no deployment is created

### Requirement: A deploy uploads only the files Cloudflare lacks

The deploy job SHALL ask Cloudflare which of the deployment's hashes it lacks, upload only those files,
then confirm every hash of the deployment to Cloudflare. A lacking file in the run's folder SHALL be
uploaded from it; any other SHALL be read back, a bucket at a time without writing it to disk, and
uploaded only if it is the size its entry gives, passes the cell-file checks and hashes to its `hashes.json`
entry; else the deploy fails.

#### Scenario: Only new files

- **WHEN** Cloudflare holds every kept file's hash, and lacks two of the files this run wrote
- **THEN** the run uploads exactly those two, confirms every hash of the deployment, and creates the deployment

#### Scenario: A kept file Cloudflare no longer holds

- **WHEN** Cloudflare lacks the hash of a kept cell's `t0-3m` file, and the live site serves that file unchanged
- **THEN** the deploy job reads it back, uploads it, and creates the deployment

#### Scenario: A kept file read back too large

- **WHEN** Cloudflare lacks a kept file's hash, and the live site serves that path with more bytes than the manifest gives it
- **THEN** the deploy job fails without reading past that size, and no deployment is created

#### Scenario: A kept file re-read that isn't a cell file

- **WHEN** Cloudflare lacks a kept file's hash, and the live site serves at that path bytes of its manifest size that hash to its `hashes.json` entry but aren't a slope-cell file of that cell and layer
- **THEN** the deploy job fails and no deployment is created

#### Scenario: A re-read leaves no file

- **WHEN** the deploy job reads back a kept file Cloudflare lacks and uploads it
- **THEN** no file holding its bytes is left on the runner

#### Scenario: A kept file changed on the live site

- **WHEN** Cloudflare lacks a kept file's hash, and the live site serves that path with other bytes
- **THEN** the deploy job fails and no deployment is created

### Requirement: Waits on Cloudflare are bounded

Each call to Cloudflare's API and each read from the live site SHALL time out after 2 minutes (the
deployment's call after 5), and be retried at most twice on a network error or a 5xx answer, the
deployment's call never. Any other failure, or an answer the deploy doesn't expect (a missing hash no
file of the deployment has, an answer that isn't JSON), SHALL fail the run with no deployment.

#### Scenario: A transient 5xx

- **WHEN** Cloudflare answers one call with a 502, then with success
- **THEN** the call is made again and the upload goes on

#### Scenario: A call that hangs

- **WHEN** Cloudflare doesn't answer a call within its timeout, three times
- **THEN** the run fails and no deployment is created

#### Scenario: A hash no file has

- **WHEN** Cloudflare reports lacking a hash that no file of the deployment has
- **THEN** the run fails and no deployment is created

### Requirement: Files keep their content types

Every file the deploy job uploads SHALL carry the content type wrangler gave it: `application/gzip`
for `.gz`, `application/json` for `.json`, `text/html` for `.html` and `text/plain` for `.txt`.

#### Scenario: A cell file's type

- **WHEN** a run uploads `cells/158_-425/t1-4.json.gz` and `manifest.json`
- **THEN** they are sent as `application/gzip` and `application/json`

### Requirement: The deploy's one package is installed from its lockfile

The deploy job SHALL install only `blake3-wasm` 2.1.5, with `npm ci --ignore-scripts` from
`deploy/package-lock.json`, in a step that holds no secret, and no wrangler config file SHALL exist in
the repository.

#### Scenario: Reading the package files

- **WHEN** `deploy/package.json` and its lockfile are read
- **THEN** the only dependency is `blake3-wasm` 2.1.5, with its integrity hash, and the package has no install script

#### Scenario: Reading the install step

- **WHEN** the workflow file is read
- **THEN** the deploy job installs with `npm ci --ignore-scripts` in a step that names no secret

### Requirement: The Cloudflare token reaches two curl calls only

The token and account id SHALL be secrets of the Environment `pages-production`, used only by the
deploy job, and given only to two steps after the assemble and hash steps: one fetching an upload
token for project `slope-extracts`, one creating the deployment from files earlier steps wrote. Each
SHALL write them with shell builtins into curl's header and config files, removed on exit, unset them
before running any program, and print nothing of an answer but the deployment's id and URL.

#### Scenario: Reading the deploy job

- **WHEN** the workflow file is read
- **THEN** `secrets.` appears in exactly two steps of the deploy job, each calling only `api.cloudflare.com` with curl, for project `slope-extracts`, the deployment on branch `main`, both after the assemble and hash steps, and in no other job

#### Scenario: Reading a token step

- **WHEN** either token step is read
- **THEN** the token reaches curl only through a header file and the account id only through a config file, both secrets are unset before curl runs, curl writes its answer to a file, and the step removes those files on exit

### Requirement: The upload token stays out of the log

The step that fetches the upload token SHALL mask it before anything else uses it, and pass it on only
in a file under the runner's temporary folder that only the job's user can read, never in a step
output or the environment. The upload step SHALL remove that file when it ends, failed or not, and
SHALL print neither the token nor an API response.

#### Scenario: Reading the token step

- **WHEN** the workflow file is read
- **THEN** the token step writes `::add-mask::` before it writes the token's file, and neither token step writes `GITHUB_OUTPUT` or `GITHUB_ENV`

#### Scenario: A failed upload

- **WHEN** the upload step fails on Cloudflare's answer
- **THEN** the token's file is gone and the step's output holds neither the token nor the answer's body

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

#### Scenario: Only empty zoomed-out layers

- **WHEN** a tile's only built cell has an empty `t1-4`
- **THEN** its overview holds class `30` of tier `4` with no polygon, and its manifest entry gives that overview

#### Scenario: A split cell's tier 4

- **WHEN** a tile's only built cell, `158_-425`, is split, its quarters `316_-850`, `316_-849`, `317_-850` and `317_-849` holding 1, 2, 0 and 4 tier-4 polygons
- **THEN** its overview holds those 7 polygons, `316_-850`'s first and `317_-849`'s 4 last

### Requirement: The manifest lists tiles and areas

`manifest.json` SHALL hold exactly `format` `slope-extract`, `version` 2, `attribution` (the sources'
credit), `cellFormat` (the cell file's format and version), `layers` (the layer names), `tiles`, mapping each tile with a covered cell to its entry, and `areas`, in `areas.json`'s
order, each with exactly `id`, `name`, `boxes` and `tiles` (the tiles holding cells it covers, in row then
column order). The boxes describe an area; whether a cell exists is the tiles' to say.

#### Scenario: Colorado's manifest

- **WHEN** only Colorado is listed and 10 of its cells are built
- **THEN** `manifest.json` is version 2, its `areas` holds Colorado with its box and its 12 tiles, and the tiles' `built` counts sum to 10

#### Scenario: Areas in their list's order

- **WHEN** `areas.json` lists `colorado` then `utah`
- **THEN** the manifest's `areas` lists `colorado` then `utah`

### Requirement: A tile's entry counts and masks its cells

A tile's entry SHALL hold exactly `covered` and `built` (counts of cells, a split cell once),
`coveredMask` and `builtMask`, `indexBytes` (its index's size) and, when it has a built cell, `overview`
(`bytes`, and `polygons` and `points` counted as a cell tier's). A mask is 64 bits, bit (row − 8 × trow) × 8 + (col − 8 × tcol) set for
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
a reader knows it is empty without requesting it; a build job's or tile index's entry giving a layer
with no polygon more bytes SHALL be invalid (a version 1 one is read as the first run says). This is apart from the left-out marker, whose `tiers` count tier `0`.

#### Scenario: A flat cell

- **WHEN** a cell on the plains has no slope over 30°
- **THEN** its entry gives each layer `{"bytes": 0, "tiers": {}}`, and the site holds no file for it

#### Scenario: An empty layer's file is there anyway

- **WHEN** a build job's entry gives `t1-4` `bytes` 0 and `tiers` `{}`, and its folder holds `t1-4.json.gz`
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: A file with no polygons

- **WHEN** a build job's entry gives `t0-3m` 500 bytes and tier `0` 0 polygons, with its file
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: An empty layer with counts

- **WHEN** an entry gives a layer `bytes` 0 and `tiers` with any tier
- **THEN** it is the left-out marker when the layer is `t0-2m` with tier `0` at 0 and 0, and otherwise invalid

### Requirement: The live manifest is checked, with its tile indexes

The plan and deploy jobs SHALL read `manifest.json` and each tile index it lists (each at most 4 MiB),
and fail when any isn't of its form, a listed tile index answers other than 200 or isn't the size the
manifest gives it, a tile index lists a cell outside its tile or a built cell outside its coverage, or its
counts or masks differ from the manifest's.
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

### Requirement: A version 1 manifest still deploys

While the live manifest is version 1, a run SHALL deploy even when it builds no cell, or all its cells
fail, so the site moves to the grid at the first run after the change. The version 1 manifest SHALL be read as it was: `format`
`slope-extract`, `version` 1, and regions each with at least an `id`, `coverage`, `cells` and,
optionally, `quartered` (other keys ignored), whose entries take a tile index's form and checks; a cell
listed by two regions takes the first one's entry.

#### Scenario: Nothing to build on the first run

- **WHEN** the live manifest is version 1 and every covered cell is built and current
- **THEN** the run still deploys, and the site holds a version 2 manifest and every cell under `cells/`

#### Scenario: An invalid version 1 manifest

- **WHEN** the live version 1 manifest lists a cell in both `cells` and `quartered` of a region
- **THEN** the plan job fails with "the live manifest is not valid" and nothing is built

### Requirement: The first run moves the cells onto the grid

When the live manifest is version 1, checked as before this change, the deploy job SHALL keep each cell
it lists and this run doesn't build, deploying each file at `cells/` by its v1 path's hash; it SHALL read
back from that v1 path its `t1-4`, any file `hashes.json` doesn't list or Cloudflare lacks. A layer with
a file and no polygon in its v1 counts becomes empty; a left-out marker stays one. No v1 path or
manifest is published.

#### Scenario: Colorado's cells move

- **WHEN** the live site holds 350 built Colorado cells under `colorado/` and a version 1 manifest, `hashes.json` lists all their files, Cloudflare holds them, and a run builds 48 more
- **THEN** the deploy reads back only the 350 `t1-4` files from `colorado/…`, and the deployment holds all 398 under `cells/…`, nothing under `colorado/`, and a version 2 manifest listing all 398

#### Scenario: A v1 cell no area covers

- **WHEN** the version 1 manifest lists a cell under a region that no area's boxes cover
- **THEN** the new site would leave that cell out, so the deploy job fails and nothing is deployed

#### Scenario: A v1 cell no area covers, while a run builds more

- **WHEN** the version 1 manifest lists a cell no area's boxes cover, and a run builds two cells
- **THEN** the new site would leave that cell out though it holds more cells, so the deploy job fails
  and nothing is deployed

#### Scenario: A v1 left-out 2 m layer

- **WHEN** a v1 cell's `t0-2m` is the left-out marker
- **THEN** its new entry keeps the marker, and the plan still treats the layer as left out

#### Scenario: A v1 layer file with no polygons

- **WHEN** the version 1 manifest gives a cell's `t1-4` 300 bytes and 0 polygons in every tier
- **THEN** the plan accepts the manifest, and the new tile index gives that `t1-4` `{"bytes": 0, "tiers": {}}`

#### Scenario: A v1 layer with no polygons

- **WHEN** a v1 cell's `t1-4` counts 0 polygons in every tier
- **THEN** its new entry gives `t1-4` `{"bytes": 0, "tiers": {}}`, and the site holds no `t1-4` file for it

### Requirement: The deploy job checks the live site once deployed

Once the deployment is created, the deploy job SHALL read the live site, with no credential, until its
`manifest.json` is the bytes it deployed, for at most 10 minutes. It SHALL then check that manifest and
every tile index it lists as the plan job does, that the live `hashes.json` is the bytes it deployed,
and, in each tile, one file of its first built cell that has one against that file's entry and the
cell-file checks. The job SHALL fail otherwise, naming what failed.

#### Scenario: A deployment that went live

- **WHEN** the live site answers with the manifest, `hashes.json`, tile indexes and files just deployed
- **THEN** the check passes, having read one cell file per tile with a built cell

#### Scenario: A deployment slow to go live

- **WHEN** the live manifest is the earlier one at first, then the one just deployed
- **THEN** the check reads it again until it is, and passes

#### Scenario: A deployment that never goes live

- **WHEN** the live manifest is still the earlier one after 10 minutes
- **THEN** the deploy job fails

#### Scenario: A broken live file

- **WHEN** the live manifest is the one deployed but a tile index or the checked cell file is not the one its entry gives
- **THEN** the deploy job fails, naming that file

#### Scenario: The check holds no secret

- **WHEN** the workflow is read
- **THEN** the step that checks the live site has no secret in its environment and runs only after the deployment is created

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

### Requirement: Runs follow one another

The build workflow SHALL be scheduled every 15 minutes and SHALL run one run at a time, never cancelling
a running one. Of the runs scheduled while one runs, the newest SHALL start when it ends; older waiting
runs are dropped without starting.

#### Scenario: Reading the schedule

- **WHEN** the workflow file is read
- **THEN** its one `cron` fires every 15 minutes, and its concurrency group is one group that never cancels a run in progress

### Requirement: The pipeline reads the live site past its edge cache

Every read of the live site by the plan and deploy jobs (manifest, `hashes.json`, tile indexes, read-back
files and the check once deployed) SHALL carry a query string of its own, so the CDN's cache never
answers it and each read gets the files of the live deployment.

#### Scenario: A file the CDN still caches

- **WHEN** the CDN still holds a file of the previous deployment and the plan job reads that path
- **THEN** the request carries a query string, and the plan reads the live deployment's file
