# Tasks: slope-overview

## 1. Overview

- [x] 1.1 Tests for every new and changed scenario, seen to fail, and an attack test (a build job's own overview is refused)
- [x] 1.2 `slope_extracts/overview.py`: build the overview from a region's `t1-4` files (standard library only)
- [x] 1.3 `publish.assemble` writes each overview after the cell checks, with the 20 MiB guard
- [x] 1.4 `site.py`: the manifest's `overview` entry (a live one accepted and unused), the cell rule narrowed to `/:region/:cell/*` and an overview rule in `_headers`, the file list

## 2. Records

- [x] 2.1 ADR: the overview written by the deploy job; vector tier 4 in the cell encoding recorded as assumptions until the owner answers design.md's open questions 1 and 2 (each answer gets its own ADR)
- [x] 2.2 README: the overview file
- [x] 2.3 Security review of the deploy-job change (a read-only review agent: no findings) and an attack test (the deploy job holds the token)

## 3. After merge

- [ ] 3.1 The first run that builds a cell after merge (after the all-Colorado change merges) publishes `colorado/overview.json.gz`; check its size against the estimate — not done: after merge, on the live site
