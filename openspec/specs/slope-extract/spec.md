# slope-extract Specification

## Purpose
Builds slope-angle class polygons per 0.25° cell from USGS 3DEP elevation and publishes them as a static
Cloudflare Pages site in the form garmin-map's slope layer reads, with its deploy credential confined to one step.

## Requirements

### Requirement: Cells share the OSM extract's grid

A cell SHALL be identified as `<row>_<col>` with row = floor(latitude × 4) and col = floor(longitude × 4),
covering 0.25° of latitude by 0.25° of longitude, the grid of TimZander/osm-extracts.

#### Scenario: A cell's id

- **WHEN** a place lies at 39.6° N, 106.1° W
- **THEN** it lies in cell `158_-425`, which covers 39.50–39.75° N and 106.25–106.00° W

### Requirement: The regions list

The regions list SHALL be one file of at least one region, each with exactly `id` (lowercase letters,
digits and single hyphens, unique), `name` (not blank), `bounds` (numeric `south` < `north` within ±90,
`west` < `east` within ±180) and optionally `only` (a non-empty list of cells in its coverage). A region's
coverage SHALL be every cell its bounds touch. A list breaking a rule SHALL fail the plan job.

#### Scenario: Colorado's coverage

- **WHEN** the list holds Colorado with bounds 37.01–40.99° N, 109.04–102.06° W
- **THEN** its coverage is the 464 cells of rows 148–163 and columns −437 to −409

#### Scenario: An invalid list

- **WHEN** a region's `only` names a cell outside its coverage
- **THEN** the plan job fails and no cell is built

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
`t0-3m` (sieve 10 px, simplify 2.7 m, minimum 18 m²) and from the 2 m DEM in layer `t0-2m` (sieve 10 px,
simplify 1.8 m, minimum 8 m²).

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

A cell SHALL read every 3DEP 1 m lidar tile the TNM Access API lists for its buffered frame, as a 2 m
mosaic in which the newest publication wins where surveys overlap. Pixels no lidar covers SHALL take the
1/3 arc-second DEM. Only URLs under the 3DEP staged-products prefix SHALL be read. The entry SHALL record
each source's share of the frame and the lidar projects used.

#### Scenario: An untrusted URL in the API's answer

- **WHEN** the API lists a tile on another host
- **THEN** that tile is not read

#### Scenario: Overlapping surveys

- **WHEN** a 2016 and a 2023 survey cover the same tile
- **THEN** the 2023 survey's tile is read first

### Requirement: A cell is three gzip JSON layer files

A cell SHALL be published as `<region>/<cell>/t0-3m.json.gz`, `t0-2m.json.gz` and `t1-4.json.gz`: gzip
JSON with `format` `slope-cell`, `version` 1, `cell`, `layer`, and `tiers` mapping a tier to its classes.
A class SHALL map to polygons, each a list of rings, outer first. A ring SHALL be integers: its first point
in 24-bit map units (lat, lon), then each next point's difference, at least 3 points, closed implicitly.

#### Scenario: A ring

- **WHEN** a ring has points (100, 200), (103, 199), (101, 190) in map units
- **THEN** it is written `[100, 200, 3, -1, -2, -9]`

#### Scenario: The same cell builds to the same bytes

- **WHEN** a cell is built twice from the same DEM
- **THEN** its files are byte for byte the same

### Requirement: The manifest lists each region's coverage and built cells

`manifest.json` SHALL hold `format` `slope-extract`, `version` 1, an attribution, the cell format, the
layer names and each region's `id`, `name`, `bounds`, `coverage` and `cells`. Each built cell SHALL map to
its `recipe`, `built` date, `sources`, `projects`, and per layer its `bytes` and per tier its `polygons`
and `points`. A covered cell not yet built SHALL be absent from `cells`.

#### Scenario: A pilot run

- **WHEN** only four cells of Colorado are built
- **THEN** the manifest lists all 464 cells in Colorado's coverage and those four in its cells

### Requirement: A run builds missing and stale cells, at most 48

The plan job SHALL read the live site's manifest and choose, in coverage order (or the `only` list's), the
cells it lacks, lists with another recipe number, or lists as built more than 300 days ago, at most 48, in
jobs of 3 cells. With none to build, no build or deploy job SHALL run.

#### Scenario: A stale cell

- **WHEN** a cell was built with recipe 0 and the current recipe is 1
- **THEN** the next run builds it again

#### Scenario: The yearly refresh

- **WHEN** a cell was built 2025-11-01 and the plan runs on 2026-11-23
- **THEN** the run builds it again; on 2026-06-01 it would not have

#### Scenario: Nothing left

- **WHEN** every cell of every region is built with the current recipe
- **THEN** the run ends after the plan job

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
merged before its Cloudflare project and secrets exist doesn't fail every 3 hours.

#### Scenario: Before setup

- **WHEN** a scheduled run starts and `BUILD_ENABLED` isn't set
- **THEN** the plan, build and deploy jobs are skipped and the run ends without failing

#### Scenario: After setup

- **WHEN** the owner has set `BUILD_ENABLED` to `true`
- **THEN** the plan job runs as before

### Requirement: Wrangler is installed from its lockfile, with no install scripts

The deploy job SHALL install wrangler 3.114.17 and its dependencies with `npm ci --ignore-scripts` from
`deploy/package-lock.json`, in a step that holds no secret, and no wrangler config file SHALL exist in the
repository.

#### Scenario: A dependency's new release

- **WHEN** a package under wrangler publishes a new version with an install script
- **THEN** the deploy installs the locked version, runs no install script, and the token step runs only that code

### Requirement: The Cloudflare credentials reach one step only

The Cloudflare API token and account id SHALL be secrets of the GitHub Environment `pages-production`,
which only the deploy job uses. In it, only the wrangler step SHALL be given them, after the step that
checks the cells. The plan and build jobs SHALL hold no secret.

#### Scenario: Reading the deploy job

- **WHEN** the workflow file is read
- **THEN** `secrets.` appears only in the deploy job's wrangler step, and that step comes after the assemble step

### Requirement: Build-job packages are installed from pinned hashes

The build and test jobs SHALL install their Python packages only from wheels whose SHA-256 hashes
`requirements.txt` pins.

#### Scenario: A changed wheel

- **WHEN** a package index serves a wheel whose hash differs from the pinned one
- **THEN** the install fails and no cell is built

### Requirement: The deploy job accepts only well-formed cells

The deploy job SHALL fail, publishing nothing, when:
- an artifact holds anything but `jobs.txt`, an optional `failed.json` and one folder per listed cell
- a cell folder holds anything but its three layers and `entry.json`
- any of these files is not regular, or is over 20 MiB
- a file is not exactly the slope-cell form of its cell and layer (classes per tier, points within the
  cell), or `entry.json` holds keys or values the manifest doesn't allow

#### Scenario: A hostile artifact

- **WHEN** a build job uploads an `index.html` beside its cells
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: A symbolic link

- **WHEN** a layer file is a symbolic link
- **THEN** the deploy job fails

#### Scenario: A stray key

- **WHEN** a cell file carries an extra top-level key
- **THEN** the deploy job fails

### Requirement: A build job publishes only the cells the plan gave it

The deploy job SHALL take the plan's job list, and fail, publishing nothing, when an artifact is not
`cells-<n>` for a job the plan made, when its `jobs.txt` is not that job's planned list, or when the plan
lists a cell twice.

#### Scenario: An artifact the plan didn't make

- **WHEN** a build job also uploads `cells-99` with cells it wasn't given
- **THEN** the deploy job fails

### Requirement: A failed cell keeps its previous files

A cell that fails to build SHALL be left out of its job's artifact, the job SHALL end red, and the deploy
job SHALL keep that cell's previous files and manifest entry.

#### Scenario: One cell of three fails

- **WHEN** one cell of a job fails and the other two build
- **THEN** the site publishes the two, keeps the failed cell's previous files, and the run is red

### Requirement: Deploying adds to the live site

The deploy job SHALL write the whole site to a folder: this run's cells, every other cell the live
manifest lists (read back from the live site), the new manifest, `_headers`, `404.html` and `LICENSE.txt`.
It SHALL upload it with `wrangler pages deploy` to project `slope-extracts`. A run that built no cell SHALL
deploy nothing.

#### Scenario: A second run

- **WHEN** a run builds one more cell
- **THEN** the deployed site holds both cells' files and a manifest listing both

#### Scenario: Nothing built

- **WHEN** every cell of a run failed
- **THEN** nothing is deployed, and the live site stays as it was

### Requirement: Files read back from the live site are checked

Each file read back from the live site SHALL be the size the live manifest gives it and pass the cell-file
checks. The deploy job SHALL fail before the wrangler step otherwise, or when:
- the live manifest is invalid, unless the first-deploy switch reads it as no manifest
- a file it lists answers 404
- it reads no manifest (a 404, or the switch) though the plan job read one
- the new manifest would list fewer cells than the live one

#### Scenario: A file changed on the live site

- **WHEN** a live cell file's size differs from the live manifest's
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: The switch forgives a manifest the plan job read

- **WHEN** the plan job read a valid manifest, and the deploy job, with `FIRST_DEPLOY` `true`, reads the manifest as none
- **THEN** the deploy job fails, and no site of this run's cells alone is published

#### Scenario: The custom domain stops answering

- **WHEN** the plan job read the live manifest but the deploy job gets a 404 for it
- **THEN** the deploy job fails, and no site of this run's cells alone is published

### Requirement: The site holds at most 19,000 files

The deploy job SHALL fail before pushing when the site would hold more than 19,000 files.

#### Scenario: Too many files

- **WHEN** the manifest would name 19,001 files
- **THEN** the deploy job fails and nothing is deployed

### Requirement: The site sets its CORS and cache headers

`_headers` SHALL send `Access-Control-Allow-Origin: *` and `X-Content-Type-Options: nosniff` on every path,
and one `Cache-Control` per path:
one day for cell files, an hour for `LICENSE.txt`, five minutes for `manifest.json`. A missing path SHALL
answer from `404.html`.

#### Scenario: Reading the headers file

- **WHEN** `_headers` is read
- **THEN** no path matches two rules that set `Cache-Control`

### Requirement: The site carries its sources notice

`LICENSE.txt` SHALL name USGS 3DEP as the source, state it is public domain, list every lidar project the
built cells used, and link this repository.

#### Scenario: The pilot's notice

- **WHEN** the Dillon cell is built from three lidar projects
- **THEN** `LICENSE.txt` lists those three projects

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
