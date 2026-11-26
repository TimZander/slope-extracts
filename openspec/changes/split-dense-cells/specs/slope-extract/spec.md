## ADDED Requirements

### Requirement: A cell too large to publish whole is split into its four quarters

When any of a cell's three layer files would be over 20 MiB of gzip or 64 MiB of JSON, the build job
SHALL write the cell, all three layers, as its four 0.125° quarters instead, log a GitHub `::warning::`
annotation naming the cell, and write no whole-cell layer file. A quarter's id SHALL be `<qrow>_<qcol>`
with qrow = floor(latitude × 8) and qcol = floor(longitude × 8). A cell under both limits SHALL be
written whole, as before.

#### Scenario: A 2 m layer too large to publish whole

- **WHEN** cell `158_-425`'s `t0-2m` file would be 24 MB of gzip and its other two layers 5 MB each
- **THEN** its folder holds `entry.json` and the folders `316_-850`, `316_-849`, `317_-850` and
  `317_-849`, each with `t0-3m.json.gz`, `t0-2m.json.gz` and `t1-4.json.gz`, holds no whole-cell layer
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
cell's order. Every point SHALL lie within its quarter. A quarter with no polygon in a class SHALL still be written, with that class empty.

#### Scenario: A polygon across the quarters' middle line

- **WHEN** a split cell holds a polygon crossing the line between quarters `316_-850` and `317_-850`
- **THEN** each of those quarters holds the part on its side, and every point of each lies within its quarter's bounds, to one map unit

#### Scenario: A quarter with no steep ground

- **WHEN** a split cell's quarter `317_-849` has no slope over 30°
- **THEN** its three files are written, each with its tiers and every class empty

#### Scenario: The same split cell builds to the same bytes

- **WHEN** a split cell is built twice from the same DEM
- **THEN** its twelve files are byte for byte the same

### Requirement: A quarter file names its cell and its quarter

A quarter's layer SHALL be published as `<region>/<cell>/<quarter>/<layer>.json.gz`, in the slope-cell
version 1 form of a whole cell's with exactly one more key, `quarter`, holding the quarter's id; `cell`
SHALL hold the parent cell's id. A whole cell's file SHALL have no `quarter` key.

#### Scenario: A quarter's 2 m layer

- **WHEN** quarter `316_-850` of cell `158_-425` of region `colorado` is published
- **THEN** `colorado/158_-425/316_-850/t0-2m.json.gz` holds `format` `slope-cell`, `version` 1, `cell`
  `158_-425`, `quarter` `316_-850`, `layer` `t0-2m` and `tiers`

### Requirement: The manifest lists quartered cells apart from whole ones

Each region SHALL have `quartered` (possibly empty) beside `cells`, mapping each split cell to its
`recipe`, `built`, `sources`, `projects` and `quarters`: exactly its four quarters, each with exactly
`layers`, counted and checked as a whole cell's are, the left-out marker's rules included. A
`quartered` entry SHALL have no `layers`, and a `cells` entry no `quarters`. A cell SHALL be in at most one of `cells` and `quartered`. The manifest
SHALL keep `version` 1, so a reader that knows only `cells` reads a quartered cell as not yet built.

#### Scenario: A region with one split cell

- **WHEN** a run publishes `158_-424` whole and `158_-425` split
- **THEN** the region's `cells` lists `158_-424` only, and its `quartered` maps `158_-425` to an entry
  whose `quarters` holds `316_-850`, `316_-849`, `317_-850` and `317_-849`, each with per-layer `bytes`
  and per-tier `polygons` and `points`

#### Scenario: No split cell

- **WHEN** a region has no split cell
- **THEN** its `quartered` is `{}`

#### Scenario: A cell listed both ways

- **WHEN** the live manifest lists a cell in both `cells` and `quartered`
- **THEN** the plan job fails with "the live manifest is not valid" and nothing is built

#### Scenario: A quartered cell missing a quarter

- **WHEN** a build job's entry for a split cell lists three quarters
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: A live entry with both forms

- **WHEN** the live manifest's `quartered` entry for a cell also has `layers`
- **THEN** the plan job fails with "the live manifest is not valid" and nothing is built

#### Scenario: The marker on a quarter's zoomed-out layer

- **WHEN** the live manifest gives a quarter's `t1-4` `bytes` 0
- **THEN** the plan job fails with "the live manifest is not valid" and nothing is built

#### Scenario: A live manifest from before this change

- **WHEN** the live manifest's regions have no `quartered` key
- **THEN** the plan and deploy jobs read it as a manifest with no split cell

### Requirement: The deploy job accepts only well-formed split cells

A split cell's `entry.json` SHALL have `quarters` and no `layers`, a whole cell's `layers` and no
`quarters`. A split cell's folder SHALL hold exactly `entry.json` and its four quarter folders, real
folders, not links, each holding exactly the layers its quarter doesn't mark left out. Each quarter file SHALL pass a whole
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

## MODIFIED Requirements

### Requirement: The deploy job accepts only well-formed cells

The deploy job SHALL fail, publishing nothing, when:
- an artifact holds anything but `jobs.txt`, an optional `failed.json` and one folder per listed cell
- a whole cell's folder holds anything but `entry.json` and the layers its entry doesn't mark left out
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

### Requirement: A cell is three gzip JSON layer files

A cell SHALL be published as `<region>/<cell>/t0-3m.json.gz`, `t0-2m.json.gz` (unless left out) and
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

### Requirement: The manifest lists each region's coverage and built cells

`manifest.json` SHALL hold `format` `slope-extract`, `version` 1, an attribution, the cell format, the
layer names and each region's `id`, `name`, `bounds`, `coverage`, `cells` and `quartered`. Each built
whole cell SHALL map to its `recipe`, `built` date, `sources`, `projects`, and per layer its `bytes` and
per tier its `polygons` and `points`. A covered cell not yet built SHALL be in neither `cells` nor
`quartered`.

#### Scenario: A pilot run

- **WHEN** only four cells of Colorado are built, all whole
- **THEN** the manifest lists all 464 cells in Colorado's coverage, those four in its cells, and an empty quartered

### Requirement: A run builds missing and stale cells, at most 48

The plan job SHALL read the live site's manifest and choose, in coverage order (or the `only` list's), the
cells it lists in neither `cells` nor `quartered`, lists with another recipe number, lists as built more
than 300 days ago, or lists in `cells` with a layer left out, at most 48, in jobs of 3 cells. With none to
build, no build or deploy job SHALL run.

#### Scenario: A stale cell

- **WHEN** a cell was built with recipe 0 and the current recipe is 1
- **THEN** the next run builds it again

#### Scenario: The yearly refresh

- **WHEN** a cell was built 2025-11-01 and the plan runs on 2026-11-23
- **THEN** the run builds it again; on 2026-06-01 it would not have

#### Scenario: Nothing left

- **WHEN** every cell of every region is built with the current recipe
- **THEN** the run ends after the plan job

#### Scenario: A whole cell built without its 2 m layer

- **WHEN** the live manifest lists a cell in `cells`, built today with the current recipe, with its `t0-2m` left out
- **THEN** the run builds it again

#### Scenario: A split cell with a quarter's 2 m layer left out

- **WHEN** the live manifest lists a cell in `quartered`, built today with the current recipe, with one quarter's `t0-2m` left out
- **THEN** the run doesn't build it

### Requirement: Files read back from the live site are checked

Each file read back from the live site SHALL be the size the live manifest gives it and pass the cell-file
checks. The deploy job SHALL fail before the wrangler step otherwise, or when:
- the live manifest is invalid, unless the first-deploy switch reads it as no manifest
- a file it lists answers 404
- it reads no manifest (a 404, or the switch) though the plan job read one
- the new manifest would list fewer cells, whole and quartered together, than the live one

#### Scenario: A file changed on the live site

- **WHEN** a live cell file's size differs from the live manifest's
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: A live cell without its 2 m layer

- **WHEN** the live manifest lists a cell whose `t0-2m` is marked left out, and a run builds another cell but not it
- **THEN** the deploy job reads back that cell's `t0-3m` and `t1-4`, requests no `t0-2m`, and the new
  manifest keeps its entry as it was

#### Scenario: A live split cell

- **WHEN** the live manifest lists a split cell, and a run builds another cell
- **THEN** the deploy job reads back its quarters' files, each checked against its quarter's size and
  bounds, and the new manifest keeps its entry under `quartered` as it was

#### Scenario: A whole cell becomes split

- **WHEN** the live manifest lists a cell in `cells`, and this run builds it split
- **THEN** the new manifest lists it in `quartered` only, the site holds its quarters' files and none
  of its whole-cell files, and the deploy goes ahead

#### Scenario: A split cell fits whole again

- **WHEN** the live manifest lists a cell in `quartered`, and this run builds it whole
- **THEN** the new manifest lists it in `cells` only, and the site holds its whole-cell files and none
  of its quarters'

#### Scenario: The switch forgives a manifest the plan job read

- **WHEN** the plan job read a valid manifest, and the deploy job, with `FIRST_DEPLOY` `true`, reads the manifest as none
- **THEN** the deploy job fails, and no site of this run's cells alone is published

#### Scenario: The custom domain stops answering

- **WHEN** the plan job read the live manifest but the deploy job gets a 404 for it
- **THEN** the deploy job fails, and no site of this run's cells alone is published

### Requirement: The site sets its CORS and cache headers

`_headers` SHALL send `Access-Control-Allow-Origin: *` and `X-Content-Type-Options: nosniff` on every path,
and one `Cache-Control` per path:
one day for cell files (`/<region>/<cell>/…`, quarters' included), an hour for `LICENSE.txt` and overview
files, five minutes for `manifest.json`.
A missing path SHALL answer from `404.html`.

#### Scenario: Reading the headers file

- **WHEN** `_headers` is read
- **THEN** no path matches two rules that set `Cache-Control`

#### Scenario: The overview's cache

- **WHEN** `_headers` is read
- **THEN** `/colorado/overview.json.gz` matches one rule, which caches it for an hour, and
  `/colorado/158_-425/t1-4.json.gz` matches one, which caches it for a day

#### Scenario: A quarter's cache

- **WHEN** `_headers` is read
- **THEN** `/colorado/158_-425/316_-850/t0-2m.json.gz` matches one rule, which caches it for a day

### Requirement: Each region has an overview of its built cells' tier 4

A region with a built cell SHALL have `<region>/overview.json.gz`: gzip JSON with exactly the keys
`format` `slope-overview`, `version` 1, `region`, and `tiers` holding only tier `4`, class `30`: the tier-4
polygons of every built cell of the region, whole or split, cells in coverage order, a split cell's
quarters by qrow then qcol, each file's polygons in its `t1-4` file's order, rings encoded as in a cell.
A region with no built cell SHALL have no overview.

#### Scenario: Two built cells

- **WHEN** a region has two built cells, with 3 and 5 tier-4 polygons
- **THEN** its overview holds 8 polygons in class `30` of tier `4`, the first cell's 3 first

#### Scenario: The same cells give the same bytes

- **WHEN** the overview is written twice from the same cell files
- **THEN** both are byte for byte the same

#### Scenario: No built cell

- **WHEN** a region has no built cell
- **THEN** the site holds no overview for it

#### Scenario: A split cell's tier 4

- **WHEN** a region's only built cell, `158_-425`, is split, its quarters `316_-850`, `316_-849`, `317_-850` and `317_-849` holding 1, 2, 0 and 4 tier-4 polygons
- **THEN** its overview holds those 7 polygons, `316_-850`'s first and `317_-849`'s 4 last

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

### Requirement: The site holds at most 19,000 files

The deploy job SHALL fail before pushing when the site would hold more than 19,000 files.

#### Scenario: Too many files

- **WHEN** the manifest would name 19,001 files
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: Counting a split cell's files

- **WHEN** a region has one whole cell and one split cell with one quarter's `t0-2m` left out
- **THEN** the site's file count includes 3 files for the whole cell and 11 for the split one

### Requirement: The site carries its sources notice

`LICENSE.txt` SHALL name USGS 3DEP as the source, state it is public domain, list every lidar project the
built cells used, and link this repository.

#### Scenario: The pilot's notice

- **WHEN** the Dillon cell is built from three lidar projects
- **THEN** `LICENSE.txt` lists those three projects

#### Scenario: A split cell's projects

- **WHEN** the only built cell is split and was built from two lidar projects
- **THEN** `LICENSE.txt` lists those two projects
