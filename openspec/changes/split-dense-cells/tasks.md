# Tasks: split-dense-cells

## 1. Tests first

- [ ] 1.1 Tests for every new and changed scenario, seen to fail: the split and its limits, quarter clipping and ids, quarter file keys, `quartered` in the manifest, the plan rules, the artifact and read-back checks, the headers, the overview, the quarter fallback
- [ ] 1.2 Attack tests: a whole-cell file beside quarters, a quarter's point in another quarter, a quarter file naming another quarter, three quarters, a cell in both `cells` and `quartered`

## 2. Code

- [ ] 2.1 `grid.py`: quarter ids and bounds of a cell
- [ ] 2.2 `cellfile.py`: a quarter document (`quarter` key) and clipping a cell's polygons to a quarter in map units
- [ ] 2.3 `build_cell.py`: write a cell whole or, when any layer is over a limit, as four quarters; the `t0-2m` fallback per quarter; a quarter's other layer over a limit fails the cell
- [ ] 2.4 `site.py`: the split entry check, `quartered` in the manifest and its check, the plan rules, the file list, the licence's projects
- [ ] 2.5 `publish.py`: the artifact check, cell-file check with a quarter, read-back of quartered cells, the cell count, copying quarter files
- [ ] 2.6 `overview.py` / assembly: a split cell's quarters in order

## 3. Records

- [ ] 3.1 ADRs: the owner's manifest and file decisions; split replaces the skip with the skip as fallback; and each open question the owner answers (quarters cut from the cell's polygons, replanning whole cells with a layer left out, `quartered` always present, a quarter's keys)
- [ ] 3.2 README: split cells
- [ ] 3.3 The manifest reader's matching change to read `quartered` and quarter files — not done: it belongs to the reader's own repository and is the owner's to schedule
