## ADDED Requirements

### Requirement: An oversize 2 m layer is left out of its cell

When a cell's `t0-2m` file would be over 20 MiB of gzip or 64 MiB of JSON, the build job SHALL write the
cell without that file, log a warning naming the cell and the layer, and count the cell as built. A
`t0-3m` or `t1-4` file over 20 MiB SHALL still fail its cell. No limit SHALL change.

#### Scenario: A 2 m layer too large to publish

- **WHEN** a cell's `t0-2m` file would be 24 MB of gzip, and its other two layers are 5 MB each
- **THEN** the cell's folder holds `t0-3m.json.gz`, `t1-4.json.gz` and `entry.json` but no
  `t0-2m.json.gz`, the job logs a warning naming the cell and `t0-2m`, and the job doesn't fail

#### Scenario: A 2 m layer whose JSON is too large

- **WHEN** a cell's `t0-2m` file would be 15 MB of gzip unpacking to 70 MB of JSON
- **THEN** the cell is written without `t0-2m.json.gz`, as above

#### Scenario: A 3 m layer too large to publish

- **WHEN** a cell's `t0-3m` file would be 24 MB of gzip
- **THEN** the cell fails as before and the job ends red

### Requirement: The manifest marks a left-out layer

A left-out layer's entry SHALL keep its key, with `bytes` 0 and `tiers` holding only tier `0` with 0
polygons and 0 points; the site SHALL hold no file for it and the deploy job SHALL request none. A layer file is never 0 bytes, so a
reader can tell the layer is absent without requesting it. `bytes` 0 on `t0-3m` or `t1-4`, or on a
`t0-2m` with any other `tiers`, SHALL make the entry invalid.

#### Scenario: A cell published without its 2 m layer

- **WHEN** a run publishes a cell whose `t0-2m` was left out
- **THEN** its manifest entry's `t0-2m` is `{"bytes": 0, "tiers": {"0": {"polygons": 0, "points": 0}}}`,
  its other layers are listed as usual, and the site holds its `t0-3m` and `t1-4` files only

#### Scenario: The marker on another layer

- **WHEN** a build job's entry gives `t1-4` `bytes` 0
- **THEN** the deploy job fails and nothing is deployed

## MODIFIED Requirements

### Requirement: A cell is three gzip JSON layer files

A cell SHALL be published as `<region>/<cell>/t0-3m.json.gz`, `t0-2m.json.gz` (unless left out) and
`t1-4.json.gz`: gzip JSON with `format` `slope-cell`, `version` 1, `cell`, `layer`, and `tiers` mapping a
tier to its classes. A class SHALL map to polygons, each a list of rings, outer first. A ring SHALL be
integers: its first point in 24-bit map units (lat, lon), then each next point's difference, at least 3
points, closed implicitly.

#### Scenario: A ring

- **WHEN** a ring has points (100, 200), (103, 199), (101, 190) in map units
- **THEN** it is written `[100, 200, 3, -1, -2, -9]`

#### Scenario: The same cell builds to the same bytes

- **WHEN** a cell is built twice from the same DEM
- **THEN** its files are byte for byte the same

### Requirement: The deploy job accepts only well-formed cells

The deploy job SHALL fail, publishing nothing, when:
- an artifact holds anything but `jobs.txt`, an optional `failed.json` and one folder per listed cell
- a cell folder holds anything but its layers and `entry.json`
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

#### Scenario: A left-out layer's file is there anyway

- **WHEN** a cell's entry marks `t0-2m` left out but its folder holds a `t0-2m.json.gz`
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: A layer missing without the marker

- **WHEN** a cell's folder lacks `t0-2m.json.gz` and its entry gives `t0-2m` a size above 0
- **THEN** the deploy job fails and nothing is deployed

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

#### Scenario: A live cell without its 2 m layer

- **WHEN** the live manifest lists a cell whose `t0-2m` is marked left out, and a run builds another cell
- **THEN** the deploy job reads back that cell's `t0-3m` and `t1-4`, requests no `t0-2m`, and the new
  manifest keeps its entry as it was

#### Scenario: The switch forgives a manifest the plan job read

- **WHEN** the plan job read a valid manifest, and the deploy job, with `FIRST_DEPLOY` `true`, reads the manifest as none
- **THEN** the deploy job fails, and no site of this run's cells alone is published

#### Scenario: The custom domain stops answering

- **WHEN** the plan job read the live manifest but the deploy job gets a 404 for it
- **THEN** the deploy job fails, and no site of this run's cells alone is published
