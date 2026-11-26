# slope-extracts

Slope-angle shading cells for [garmin-map](https://maps.timzander.com)'s slope layer, computed from the
USGS 3D Elevation Program (3DEP) and published as a static site at <https://slope.timzander.com>.

- **What it builds:** `openspec/specs/slope-extract` (the spec), `docs/decisions/` (why).
- **How:** `.github/workflows/build.yml` runs every 3 hours and by hand. It builds the cells of
  `regions.json` that the site lacks or built with an older recipe, at most 48 per run, three per job:
  - Each build job reads 3DEP 1 m lidar (the ~10 m DEM where lidar has a gap) as a 2 m mosaic.
  - It classifies slope into the bands and zoom tiers in `slope_extracts/recipe.py`, and writes three
    gzip JSON files per 0.25° cell. A cell with a file too large to publish (over 20 MiB of gzip or
    64 MiB of JSON) is split: all three layers are written for each of its four 0.125° quarters, at
    `<region>/<cell>/<quarter>/<layer>.json.gz`, and the manifest lists it under the region's
    `quartered`, not `cells`, with per-quarter layers. A quarter's `t0-2m` still too large is left out
    with a warning; the manifest then gives that layer `bytes` 0 and no polygons, and the site holds no
    file for it.
  - A deploy job checks them, reads back from the live site only what it needs (every cell's `t1-4`,
    for each region's `overview.json.gz`, the app's zoomed-out view), and writes `hashes.json`: every
    file's Pages hash. It then creates a Pages deployment from that manifest of hashes, uploading only
    the files Cloudflare lacks (`deploy/pages.mjs`), so a deploy's time and disk grow with its new
    cells, not the site.
- **Setup:** `docs/setup.md` (Cloudflare project, token, Environment, then `BUILD_ENABLED`).
- **Locally:** `python -m venv .venv && .venv/bin/pip install -r requirements.in && .venv/bin/python -m
  pytest -q tests`. Build a real cell with `.venv/bin/python -m slope_extracts.build_cell 158_-425 --out
  out/`.

Elevation data: U.S. Geological Survey, 3D Elevation Program, public domain. The code is MIT-licensed.
