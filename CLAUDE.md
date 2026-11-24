# CLAUDE.md

Guidance for agents working in this repository.

## Spec-driven workflow

@.claude/sdd-workflow.md

## Project

- Python 3.12 (rasterio, numpy, shapely as hash-pinned wheels; `requirements.txt` for CI,
  `requirements.in` locally). Tests: `python -m pytest -q tests`. OpenSpec tooling: `npm ci`.
- The plan and deploy jobs use only Python's standard library (`slope_extracts/site.py`, `publish.py`,
  `grid.py`, `recipe.py`): keep it that way, because the deploy job holds the write token.
- The build workflow (`.github/workflows/build.yml`) is high-risk: changes to it get `/security-review`
  and an attack test. It deploys with a Cloudflare token whose Pages permission is account-wide (ADR
  0003): the token stays in the `pages-production` Environment and reaches only the wrangler step.
  Never add a workflow input, a `pull_request_target` trigger, or a step after checkout that runs code
  from a cell artifact.
- The cell format and manifest are a contract with garmin-map's `slope-layer` spec. Changing them is a
  change in both repositories. garmin-map is private: never copy its text here.
- Changing any number in `recipe.py` changes the cells: bump `RECIPE` so the next runs rebuild them.
- `tnmaccess.nationalmap.gov`, `prd-tnm.s3.amazonaws.com` and `*.pages.dev` may be blocked in agent
  containers; the tests use a synthetic DEM and a local git remote.
