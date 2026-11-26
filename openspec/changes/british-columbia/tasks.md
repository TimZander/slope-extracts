## 1. Areas

- [ ] 1.1 Tests: an area's `source`, refused when missing or unknown, and a cell two sources cover fails the plan, seen to fail
- [ ] 1.2 `site.py`: areas' `source`, the one-source check; a live manifest's area still has exactly `id`, `name`, `boxes`, `tiles` (test)

## 2. The HRDEM source

- [ ] 2.1 Tests (fake catalogue): an hrdem cell reads only the mosaic's trusted DTM URLs, records `dem10m` 0 and the projects, and with no project is built empty with no raster read; UTM zones 7 to 11; seen to fail
- [ ] 2.2 `sources.py`: the catalogue search (mosaic tiles, then projects), trusted URLs and ids; an empty mosaic answer fails
- [ ] 2.5 `site.py`: the entry check accepts project ids of letters, digits, `_` and `-` (deploy and live tile indexes), with tests
- [ ] 2.3 `build_cell.py`: the cell's source from the areas; no fill for `hrdem`; the empty build; `grid.py`: zones 7 to 19
- [ ] 2.4 A real BC cell built here from the live catalogue (lidar, partly, and none), checked

## 3. The credit

- [ ] 3.1 Tests: `LICENSE.txt` and `attribution` credit both sources, seen to fail
- [ ] 3.2 `site.py`: the credit

## 4. British Columbia

- [ ] 4.1 `areas.json`: Colorado `source` `3dep`, then `british-columbia` (`hrdem`, 48 boxes)

## 5. Records

- [ ] 5.1 ADRs (no lidar no data; an area's source; the HRDEM mosaic and the catalogue gate); README
- [ ] 5.2 Security review and attack test (new hosts, untrusted catalogue answers)
