# Proposal: back-to-back-runs

## Why

A run builds at most 48 cells and takes 25 to 60 minutes, but the build workflow starts only every 3
hours (ADR 0006), so most of each 3 hours builds nothing. The owner asked (2026-11-26) to keep the
pipeline running, starting the next run as soon as one finishes, rather than every 3 hours.

## What Changes

- The build workflow is scheduled every 15 minutes. Its runs stay one at a time (`concurrency:
  slope-extract`, never cancelling a running one), so a run scheduled while another runs waits and
  starts when it ends; a run with nothing to build still ends after the plan job.
- Every read of the live site by the plan and deploy jobs carries a query string of its own, so the
  CDN's cache (5 minutes for the manifest, a day for cell files) never answers it.
- The README and the workflow's comments say so; ADR 0035 records the decision and marks ADR 0006's
  schedule superseded.

## Impact

- `.github/workflows/build.yml` (`on.schedule`, comments), `slope_extracts/publish.py` and
  `deploy/pages.mjs` (live reads), their tests, `README.md`,
  `docs/decisions/`.
- No change to what a run builds, to the site or to the manifest. Public repository: the extra
  plan-only runs cost no billed minutes.
