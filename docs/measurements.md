# Measurements

## Pilot cells, 2026-11-23

Built locally with `python -m slope_extracts.build_cell` (MacBook, 10 cores, 17 GB; Python 3.14,
rasterio 1.5.2), recipe 1, real 3DEP lidar over HTTP. Time is wall-clock, mostly download.

| Cell | Area | Lidar | Time | Peak memory | t0-3m polygons / MB | t0-2m polygons / MB | t1-4 polygons / MB |
|---|---|---|---|---|---|---|---|
| 158_-425 | Dillon: Peak 1, Tenmile, Buffalo | 100 % | 462 s | 6.3 GB | 157,624 / 5.03 | 318,444 / 9.81 | 8,056 / 0.43 |
| 158_-426 | Vail Pass, Copper, Gore south end | 100 % | 554 s | 6.5 GB¹ | 196,329 / 6.29 | 405,198 / 12.51 | 10,012 / 0.51 |
| 159_-425 | Gore Range east side, Silverthorne north | 100 % | 290 s | 6.5 GB¹ | 53,541 / 1.80 | 109,731 / 3.60 | 1,622 / 0.07 |
| 158_-424 | Keystone, Loveland, Montezuma | 100 % | 562 s | 6.5 GB¹ | 163,368 / 5.83 | 334,064 / 11.31 | 7,707 / 0.38 |

¹ The three ran in one process; 6.5 GB is that process's peak.

Lidar projects read: CO_Central_Western_2016, CO_DRCOG_2020_B20, CO_ArapahoRooseveltPikeNF_D23,
CO_NorthwestCO_2020_D20, CO_ParkFremontCuster_2018_C21. No pilot cell needed the 10 m fill.

Per steep cell: ~12–19 MB for all three layers. For Colorado's ~200 mountain cells that comes to ~3–4 GB,
with plains cells adding little. The largest file seen is 12.5 MB (158_-426 at 2 m), under the 20 MiB guard.

Tiers 1–4 of 158_-425: 5,293 / 1,340 / 1,314 / 109 polygons (the spike's v10 map: 5,246 / 1,332 /
1,277 / 114, without a buffer).

## Compiling a cell (garmin-map's side)

`tools/cell_to_mp.py` → Polish + v10 TYP → mkgmap r4923, cell 158_-425 with tiers 1–4:

| Tier 0 | Polygons | `.mp` | `.img` | Java 17 native | CheerpJ 4.3, desktop Chromium |
|---|---|---|---|---|---|
| 3 m | 165,680 | 87 MB | 4.95 MB | 8 s | 67 s |
| 2 m | 326,500 | 181 MB | 9.2 MB | 16 s | 135 s |

The CheerpJ runs used garmin-map's real `buildImgInBrowser` in a throwaway Vitest browser bench, with a
pilot build running alongside. A phone is not measured.

## Encoding (tier 0 at 3 m, cell 158_-425)

| Form | Raw | Gzip |
|---|---|---|
| Polish text (the spike's) | 86 MB | – |
| JSON of delta map units | 18.8 MB | 5.0 MB |
| varint binary of delta map units | 7.3 MB | 4.5 MB |
