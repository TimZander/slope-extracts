# Proposal: slope-extract-pipeline

## Why

garmin-map's slope-angle shading was proven on the owner's Enduro 3 on 2026-11-23:
one-colour 32×32 stipples, a set of slope classes per zoom tier, from USGS 3DEP lidar. Computing those
classes takes about 8 minutes and 6 GB of memory per 0.25° cell, plus a few hundred MB of download.
That is too heavy for a phone. The owner decided the classes are precomputed per cell by a pipeline in
this public repository (a sibling of TimZander/osm-extracts) and served as a static Cloudflare Pages
site, which the app reads and compiles with its in-browser mkgmap.

## What Changes

- A new capability, `slope-extract`: the cell grid (shared with osm-extracts), the slope classes and
  detail per zoom tier, the cell file format garmin-map reads, the manifest, the guards against a bad
  or hostile build job, and how a run adds cells to the published site.
- A Python package, `slope_extracts`, with tests:
  - reading the lidar through the TNM Access API, with the ~10 m DEM filling gaps
  - classifying slope, sieving and simplifying
  - writing the three layer files per cell
  - planning which cells a run builds
  - checking and publishing the result
- A GitHub Actions workflow (`build.yml`) that runs on a schedule and by hand, never from a pull
  request, with no inputs. Every job is read-only.
  - Build jobs build at most 48 cells per run, with no secret.
  - One deploy job checks their files and reads the rest of the site back from the live site.
  - Its last step deploys the whole site with `wrangler pages deploy` (Direct Upload). It is the only
    step given the Cloudflare token, which is kept in the `pages-production` Environment.
  - A test workflow runs the tests on pull requests.
- A regions list holding Colorado. Its first runs build only four pilot cells in Summit County; then the
  `only` list is removed and the schedule builds the rest of the state.
- This repository's first ADRs.

## Capabilities

### New Capabilities

- `slope-extract`: builds slope-angle class polygons per 0.25° cell from USGS 3DEP and publishes them as
  a static site in the format garmin-map's slope layer reads.

### Modified Capabilities

None. `openspec/specs/` is empty.

## Impact

- New: `.github/workflows/build.yml`, `.github/workflows/test.yml`, `regions.json`,
  `requirements.txt` (hash-pinned Linux wheels), `requirements.in`, `slope_extracts/*`, `tests/*`,
  and `tools/cell_to_mp.py` (a development check, not run by the workflow).
- The site grows to an estimated 3–4 GB for all of Colorado, on Cloudflare only; nothing is committed to
  GitHub but code. Each run uploads at most ~0.75 GB (48 steep cells).
- New secrets `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` in the Environment `pages-production`,
  which the owner creates. The token's Pages permission is account-wide (ADR 0003).
- The first live run waits for the owner. They create the Pages project, the Environment and its
  secrets, then start the workflow by hand.
- Out of scope: other states, British Columbia, building a cell on request (see design.md), and the
  app side (garmin-map's `slope-layer` change).
