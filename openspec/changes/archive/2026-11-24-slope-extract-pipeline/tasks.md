# Tasks: slope-extract-pipeline

## 1. Pipeline

- [x] 1.1 Grid, recipe and sources modules (`grid.py`, `recipe.py`, `sources.py`)
- [x] 1.2 DEM mosaic with lidar then 10 m fill, 3 m resample, block means (`dem.py`)
- [x] 1.3 Classes and clipped polygons in map units (`classes.py`)
- [x] 1.4 The slope-cell file format (`cellfile.py`)
- [x] 1.5 One cell's build and entry (`build_cell.py`)
- [x] 1.6 Regions list, manifest and plan (`site.py`)
- [x] 1.7 Artifact checks, reading the live site back, and assembling the site for Direct Upload (`publish.py`)

## 2. Workflows

- [x] 2.1 `build.yml`: plan, build (hash-pinned wheels), deploy
- [x] 2.2 `test.yml`: tests on pull requests and main
- [x] 2.3 Workflow guard tests

## 3. Tests

- [x] 3.1 End-to-end build of a synthetic cone cell
- [x] 3.2 Assembling against a fake live site: first run, second run, nothing built, failed cell, tampered or missing live file
- [x] 3.3 Attack tests: extra file, symlink, cell outside coverage, path in `jobs.txt`, mislabelled cell,
      malformed ring, oversized file; secrets only in the wrangler step
- [x] 3.4 File-count guard, headers and licence tests

## 4. Pilot

- [x] 4.1 Build the four Summit County cells locally and record measurements
- [ ] 4.2 First live run (`workflow_dispatch`) once the owner has created the Pages project and the `pages-production` Environment — not done: waits for the owner
- [ ] 4.3 Remove `only` from Colorado so the schedule builds the state — not done: after the pilot is checked
- [ ] 4.4 Once every Colorado cell is built, switch the schedule to every 3 hours in June only (ADR 0006) — not done: after the backfill
- [x] 4.5 Runs wait for `BUILD_ENABLED` (ADR 0008) and `docs/setup.md` lists the owner's setup
