"""What a cell holds: the slope classes per zoom tier, watch-tested on the Enduro 3 (spike of 2026-11-23, design v10). The look (colours, dot density, type codes) is the app's; a cell
holds only geometry per class.

Each layer is one file per cell:
  t0-3m  tier 0, bands at 3 m, cliffs at 2 m   (the default closest zoom)
  t0-2m  tier 0, bands and cliffs at 2 m        (the opt-in closest zoom)
  t1-4   tiers 1-4                              (zoomed out; the same for either tier 0)

A class is named by its lower slope bound in degrees; its upper bound is the next class's lower bound
in the same tier, or none. So tier 0's "35" is 35-45 and "50" is 50+ (cliffs "60" lie over it), and tier 2's
"45" is 45+.

Sieve and minimum area are in pixels and square metres; simplify tolerance in metres. Changing any
number here changes the cells: bump RECIPE so the next run rebuilds every cell.
"""

RECIPE = 2

# Bands from DEM pixels of `res` metres. Tier 0 values scale with the pixel (sieve 10 px, simplify
# 0.9 px, minimum area 2 px^2), as in the 1/2/3 m Buffalo comparison. Tier 0's seven classes are the
# reader's "B" bands (recipe 2): finer steps from 27 to 35, one 35-45 band, then 45-50, 50-60 and cliffs.
TIER0_EDGES = [27, 30, 32, 35, 45, 50]
TIER0_BANDS_3M = dict(res=3.0, edges=TIER0_EDGES, keep=TIER0_EDGES, sieve=10, simplify=2.7, min_area=18.0)
TIER0_BANDS_2M = dict(res=2.0, edges=TIER0_EDGES, keep=TIER0_EDGES, sieve=10, simplify=1.8, min_area=8.0)
TIER0_CLIFFS = dict(res=2.0, edges=[60], keep=[60], sieve=6, simplify=1.8, min_area=8.0)

# Tiers 1-4 come from the 3 m DEM, block-averaged by `factor`. Zoomed out, whole bands drop out,
# never small areas (owner): 30-35 is gone from tier 1, cliffs fold into 45+ from tier 2, and tier 4
# is a single 30+ class.
LOW_TIERS = [
    dict(tier=1, factor=3, edges=[30, 35, 40, 45], keep=[35, 40, 45], sieve=8, simplify=12.0, min_area=2500.0,
         cliffs=dict(res=2.0, edges=[55], keep=[55], sieve=50, simplify=7.0, min_area=1200.0)),
    dict(tier=2, factor=6, edges=[30, 35, 40, 45], keep=[35, 40, 45], sieve=8, simplify=24.0, min_area=9000.0, cliffs=None),
    dict(tier=3, factor=12, edges=[30, 35, 40, 45], keep=[35, 40, 45], sieve=6, simplify=32.0, min_area=8000.0, cliffs=None),
    dict(tier=4, factor=24, edges=[30], keep=[30], sieve=6, simplify=60.0, min_area=50000.0, cliffs=None),
]

LAYERS = ('t0-3m', 't0-2m', 't1-4')

# Metres of DEM read beyond the cell on every side, so slopes, sieving and minimum areas near the
# cell's edge see the same terrain as its neighbour does. Polygons are clipped to the cell after.
BUFFER_M = 1000.0
# Grid origins snap to multiples of this (the coarsest pixel, 3 m x 24), so neighbouring cells in a
# UTM zone share one pixel grid at every tier.
GRID_SNAP_M = 72.0
