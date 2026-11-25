# slope-extracts

Slope-angle shading cells for [garmin-map](https://maps.timzander.com)'s slope layer, computed from the
USGS 3D Elevation Program (3DEP) and published as a static site at <https://slope.timzander.com>.

- **What it builds:** `openspec/specs/slope-extract` (the spec), `docs/decisions/` (why).
- **How:** `.github/workflows/build.yml` runs every 3 hours and by hand. It builds the cells of
  `regions.json` that the site lacks or built with an older recipe, at most 48 per run, three per job:
  - Each build job reads 3DEP 1 m lidar (the ~10 m DEM where lidar has a gap) as a 2 m mosaic.
  - It classifies slope into the bands and zoom tiers in `slope_extracts/recipe.py`, and writes three
    gzip JSON files per 0.25° cell.
  - A deploy job checks them and reads the rest of the site back from the live site. It writes each
    region's `overview.json.gz` (every built cell's tier 4, for the app's zoomed-out view), then uploads
    the whole site with `wrangler pages deploy` (Direct Upload sends only changed files).
- **Setup:** `docs/setup.md` (Cloudflare project, token, Environment, then `BUILD_ENABLED`).
- **Locally:** `python -m venv .venv && .venv/bin/pip install -r requirements.in && .venv/bin/python -m
  pytest -q tests`. Build a real cell with `.venv/bin/python -m slope_extracts.build_cell 158_-425 --out
  out/`.

Elevation data: U.S. Geological Survey, 3D Elevation Program, public domain. The code is MIT-licensed.
