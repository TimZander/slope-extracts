# Proposal: add-wyoming-utah-idaho

## Why

Colorado is being built (148 of 464 cells on 2026-11-26). The owner asked to add Wyoming, Utah and
Idaho (2026-11-26). Regions sharing a state line share the cells along it, and the pipeline has never
had two regions: a build job given the same cell for two regions writes both into one folder, and the
deploy job keeps only one of them, so the other region's copy is silently never published and is
planned again every run.

## What Changes

- `regions.json` lists, in this order, Colorado, Wyoming, Utah and Idaho. Each new region covers its
  whole bounding box: Wyoming 41–45° N, Utah 37–42° N (to its north line, Wyoming's corner included),
  Idaho 42–49° N (panhandle included, with the cells of neighbouring states inside its box). Owner's
  choices.
- A cell covered by two regions is built and published once for each, under each region's folder,
  and listed in each region's manifest entry (owner's choice; 64 such cells).
- The plan never gives one build job the same cell twice: it starts a new job instead. The deploy job
  fails when a planned job lists a cell twice.
- No change to the cell format, the manifest's form, the limits, the recipe or the workflow file.

## Capabilities

### Modified Capabilities

- `slope-extract`: a border cell is built for each region that covers it, and a build job never holds
  the same cell twice.

## Impact

- `regions.json`, `slope_extracts/site.py` (the plan's jobs), `slope_extracts/publish.py` (the
  artifact check), tests, README.
- The site grows to about 2,048 cells and 6,150 files (the guard is 19,000), and the manifest to about
  2.2 MB (the plan job reads at most 4 MiB). About 33 more runs, roughly four days, after Colorado.
- The manifest's readers see three more regions in the same form.
