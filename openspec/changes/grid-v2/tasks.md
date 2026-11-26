# Tasks: grid-v2

The owner answers the design's open questions before task 1.

## 1. Tests first

- [ ] 1.1 Tests for the new and changed scenarios, seen to fail: areas and their coverage, one copy of a border cell, tiles and their indexes and overviews, `index.json`, the v1 copies, the plan from the index (and from a v1 manifest on the first run), headers

## 2. Code

- [ ] 2.1 `areas.json` (Colorado as one box) and its checks, replacing `regions.json`
- [ ] 2.2 `grid.py`: tiles of a cell; `site.py`: coverage as the union of areas, the plan, the index, tile indexes, v1 regions from areas, `_headers`
- [ ] 2.3 `publish.py` and `overview.py`: cells at `cells/`, tile overviews, v1 copies, read-back by the new paths
- [ ] 2.4 `build_cell.py` and `build.yml`: plain cell ids in job lists

## 3. Records

- [ ] 3.1 ADRs: grid layout, areas, tiles, the index's form, the transition (each open question the owner answers)
- [ ] 3.2 README; the paused `add-wyoming-utah-idaho` branch reworked as areas or closed
- [ ] 3.3 Security review and attack test (the deploy job's paths change)
