## 1. Areas

- [x] 1.1 Tests: an area's `source`, refused when missing or unknown, and a cell two sources cover fails the plan, seen to fail
- [x] 1.2 `site.py`: areas' `source`, the one-source check; a live manifest's area still has exactly `id`, `name`, `boxes`, `tiles` (test)

## 2. The HRDEM source

- [x] 2.1 Tests (fake catalogue): an hrdem cell reads only the mosaic's trusted DTM URLs (not another host, not `-dsm.tif`), records `dem10m` 0 and the kept projects of every page, drops a refused id, with no project is built empty with no raster read, and fails on an empty mosaic answer; UTM zones 7 to 11; seen to fail
- [x] 2.2 `sources.py`: the catalogue search (mosaic tiles, then projects), trusted URLs and ids; an empty mosaic answer fails
- [x] 2.3 `build_cell.py`: the cell's source from the areas; no fill for `hrdem`; the empty build; `grid.py`: zones 7 to 19
- [x] 2.4 A real BC cell built here from the live catalogue (lidar, partly, and none), checked
- [x] 2.5 `site.py`: the entry check accepts project ids of letters, digits, `_` and `-` (deploy and live tile indexes), with tests

## 3. The credit

- [x] 3.1 Tests: `LICENSE.txt` and `attribution` credit both sources, seen to fail
- [x] 3.2 `site.py`: the credit

## 4. British Columbia

- [x] 4.1 `areas.json`: Colorado `source` `3dep`, then `british-columbia` (`hrdem`, 48 boxes)

## 5. Records

- [x] 5.1 ADRs (no lidar no data; an area's source; the HRDEM mosaic and the catalogue gate); README
- [x] 5.2 Security review and attack test (new hosts, untrusted catalogue answers): no finding
