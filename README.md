# slope-extracts

Slope-angle shading cells for [garmin-map](https://maps.timzander.com)'s slope layer, computed from the
USGS 3D Elevation Program (3DEP) in the United States and Natural Resources Canada's HRDEM lidar in
Canada, and published as a static site at <https://slope.timzander.com>.

- **What it builds:** `openspec/specs/slope-extract` (the spec), `docs/decisions/` (why).
- **How:** `.github/workflows/build.yml` runs every 15 minutes, one run at a time, so runs follow one
  another (and by hand). It reads the live site past its CDN cache, and builds the covered cells
  the site lacks or built with an older recipe, at most 48 per run, three per job:
  - `areas.json` lists named areas (Colorado, British Columbia), each with its elevation `source`
    (`3dep` or `hrdem`) and one or more boxes; the coverage is every 0.25° cell a box
    overlaps, each cell built and stored once however many areas cover it.
  - Each build job reads 3DEP 1 m lidar (the ~10 m DEM where lidar has a gap) as a 2 m mosaic, or, in
    an `hrdem` area, NRCan's HRDEM 1 m mosaic only, found through NRCan's STAC catalogue: where there
    is no lidar there is no data, and a cell no lidar project meets is built empty without a read.
  - It classifies slope into the bands and zoom tiers in `slope_extracts/recipe.py` (tier 0, the closest
    zoom: `27`, `30`, `32`, `35`–45°, `45`, `50` (50°+, under the cliffs) and cliffs `60`, since recipe 2), and writes up to
    three gzip JSON files per cell at `cells/<cell>/<layer>.json.gz`; a layer with no polygon gets no
    file (its entry: `bytes` 0, `tiers` `{}`). A cell with a file too large to publish (over 20 MiB of
    gzip or 64 MiB of JSON) is split into its four 0.125° quarters, at
    `cells/<cell>/<quarter>/<layer>.json.gz`; a quarter's `t0-2m` still too large is left out (`bytes`
    0, tier `0` counted at 0).
  - The site is indexed by 2° tiles of 64 cells: `manifest.json` (version 2) lists each tile's counts,
    cell masks and index size, and the areas; `tiles/<tile>/index.json` holds its cells' entries and
    `tiles/<tile>/overview.json.gz` their tier 4, the app's zoomed-out view.
  - A deploy job checks the cells, reads back from the live site only what it needs (each kept cell's
    `t1-4`, for the tile overviews), and writes `hashes.json`: every file's Pages hash. It then creates
    a Pages deployment from that manifest of hashes, uploading only the files Cloudflare lacks
    (`deploy/pages.mjs`), so a deploy's time and disk grow with its new cells, not the site.
- **Setup:** `docs/setup.md` (Cloudflare project, token, Environment, then `BUILD_ENABLED`).
- **Locally:** `python -m venv .venv && .venv/bin/pip install -r requirements.in && .venv/bin/python -m
  pytest -q tests`. Build a real cell with `.venv/bin/python -m slope_extracts.build_cell 158_-425 --out
  out/`.

Elevation data: U.S. Geological Survey, 3D Elevation Program, public domain. The code is MIT-licensed.
