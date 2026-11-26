# Tasks: grid-v2

The reader's version 2 change ships before this merges (ADR 0030).

## 1. Tests first

- [ ] 1.1 Tests for the new and changed scenarios, seen to fail: areas and their coverage, one copy of a border cell, tiles, tile indexes and overviews, the version 2 manifest and its checks, empty layers, the plan from tile indexes (and from a version 1 manifest on the first run), the first run's move by hash, headers

## 2. Code

- [ ] 2.1 `areas.json` (Colorado as one box) and its checks, replacing `regions.json`
- [ ] 2.2 `grid.py`: a cell's tile; `site.py`: coverage as the union of areas, the plan, the manifest, tile indexes, empty layers, `_headers`
- [ ] 2.3 `publish.py` and `overview.py`: cells at `cells/`, tile overviews, the first run's move, the live manifest's and tile indexes' checks
- [ ] 2.4 `build_cell.py`: empty layers write no file; the deploy's artifact check refuses an empty layer's file; `build.yml`: plain cell ids in job lists, the plan job's limit at 30 minutes, the plan's output of the live manifest's version, the deploy job's condition (deploy while version 1, even with nothing built or all failed) and its check that it read the plan's version
- [ ] 2.5 `deploy/pages.mjs`: the hash tie on the manifest and each tile index ("The live hashes belong to the live manifest")

## 3. Records

- [x] 3.1 ADRs for the owner's answers: areas as boxes (0028), 2° tiles (0029), switching at once (0030), no file for an empty layer (0031), the tile entries' masks and `indexBytes` (0032), the version 2 contract (0033)
- [ ] 3.2 README; the paused `add-wyoming-utah-idaho` branch closed, its areas carried over
- [ ] 3.3 Security review and attack test (the deploy job's paths change)
