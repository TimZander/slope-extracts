import math

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

from slope_extracts import grid, recipe

# A small stand-in for a cell (about 1.4 x 1.1 km) so an end-to-end build runs in seconds. The real
# grid is untouched; tests that use it patch cell_bounds and the buffer.
MINI = (39.600, -106.150, 39.610, -106.1325)
CELL = '158_-425'
CRS = 'EPSG:26913'
# Concentric rings of known slope around a summit: (outer radius m, slope degrees)
RINGS = [(60, 62.0), (140, 50.0), (230, 42.0), (320, 37.0), (420, 32.0), (10_000, 10.0)]


def cone(width, height, res, left, top, cx, cy):
    xs = left + (np.arange(width) + 0.5) * res
    ys = top - (np.arange(height) + 0.5) * res
    X, Y = np.meshgrid(xs, ys)
    r = np.hypot(X - cx, Y - cy)
    z = np.full(r.shape, 4000.0)
    inner = 0.0
    for outer, deg in RINGS:
        seg = np.clip(r - inner, 0, outer - inner)
        z -= seg * math.tan(math.radians(deg))
        inner = outer
    return z.astype('float32')


@pytest.fixture
def mini_cell(monkeypatch):
    monkeypatch.setattr(grid, 'cell_bounds', lambda c: MINI)
    monkeypatch.setattr(recipe, 'BUFFER_M', 200.0)
    return CELL


@pytest.fixture
def cone_dem(tmp_path):
    """A 1 m GeoTIFF of the cone, centred in the mini cell, covering it and its buffer."""
    s, w, n, e = MINI
    left, bottom, right, top = transform_bounds('EPSG:4326', CRS, w, s, e, n, densify_pts=21)
    left, bottom, right, top = left - 400, bottom - 400, right + 400, top + 400
    res = 1.0
    width, height = int((right - left) / res), int((top - bottom) / res)
    cx, cy = (left + right) / 2, (bottom + top) / 2
    z = cone(width, height, res, left, top, cx, cy)
    path = tmp_path / 'cone.tif'
    with rasterio.open(path, 'w', driver='GTiff', width=width, height=height, count=1, dtype='float32',
                       crs=CRS, transform=from_origin(left, top, res, res), nodata=np.nan) as dst:
        dst.write(z, 1)
    return str(path)
