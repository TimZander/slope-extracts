# Proposal: back-to-back-runs

## Why

A run builds at most 48 cells and takes 25 to 60 minutes, but the build workflow starts only every 3
hours (ADR 0006), so most of each 3 hours builds nothing. The owner asked (2026-11-26) to keep the
pipeline running, starting the next run as soon as one finishes, rather than every 3 hours.

## What Changes

- The build workflow is scheduled every 15 minutes. Its runs stay one at a time (`concurrency:
  slope-extract`, never cancelling a running one), so a run scheduled while another runs waits and
  starts when it ends; a run with nothing to build still ends after the plan job.
- The README, the workflow's comments and ADR 0006 say so; ADR 0035 records the decision.

## Impact

- `.github/workflows/build.yml` (`on.schedule`, comments), `tests/test_workflow.py`, `README.md`,
  `docs/decisions/`.
- No change to what a run builds, to the site or to the manifest. Public repository: the extra
  plan-only runs cost no billed minutes.
