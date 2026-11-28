# Proposal: catalogue-fail-fast

## Why

About one run in ten, one of the 16 build jobs can't reach NRCan's catalogue at all, while the others
reach it at the same moment (runs 25, 119, 133 and 146). Each of that job's `hrdem` cells then spends
about 9 minutes retrying before it fails, so a job of three cells holds the run's deploy back by about
27 minutes. The cells already fail safely and are planned again by a later run. The owner asked
(2026-11-28) for the job to fail fast instead.

## What Changes

- Once a catalogue request has used up its retries in a build job, the job's later `hrdem` cells fail at
  once, without asking the catalogue again: each keeps its previous files and is planned again by a
  later run, as now. `3dep` cells in the same job are built as usual.
- The retries of the first failed request stay as they are (4 tries).

## Impact

- `slope_extracts/sources.py`, `tests/test_bc.py`.
- No change to the site, the manifest, the workflow or what a successful build writes.
