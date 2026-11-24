"""The elevation mosaic over a cell (plus its buffer) on a UTM grid, and the reductions tiers need."""
import math

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from rasterio.warp import reproject, transform_bounds

from . import grid, recipe

GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif',
                GDAL_HTTP_MAX_RETRY='5', GDAL_HTTP_RETRY_DELAY='3', VSI_CACHE='TRUE',
                GDAL_HTTP_USERAGENT='slope-extracts (https://github.com/TimZander/slope-extracts)')


def utm_frame(cell_id, res):
    """(crs, transform, width, height) of the buffered cell at `res` metres, its origin snapped to
    the shared grid so neighbouring cells' pixels line up at every tier."""
    crs = grid.utm_epsg(cell_id)
    south, west, north, east = grid.cell_bounds(cell_id)
    left, bottom, right, top = transform_bounds('EPSG:4326', crs, west, south, east, north, densify_pts=21)
    snap, b = recipe.GRID_SNAP_M, recipe.BUFFER_M
    left = math.floor((left - b) / snap) * snap
    bottom = math.floor((bottom - b) / snap) * snap
    right = math.ceil((right + b) / snap) * snap
    top = math.ceil((top + b) / snap) * snap
    width, height = round((right - left) / res), round((top - bottom) / res)
    return crs, from_origin(left, top, res, res), width, height


def _open(url):
    return rasterio.open(url if '://' not in url else '/vsicurl/' + url)


def _mosaic(paths, crs, transform, width, height, resampling):
    """Merge `paths` onto the frame, first valid value wins; NaN where none covers."""
    res = transform.a
    bounds = (transform.c, transform.f - height * res, transform.c + width * res, transform.f)
    opened, datasets = [], []
    try:
        for p in paths:
            src = _open(p)
            opened.append(src)
            if src.crs != crs:
                vrt = WarpedVRT(src, crs=crs, resampling=resampling)
                opened.append(vrt)
                datasets.append(vrt)
            else:
                datasets.append(src)
        if not datasets:
            return np.full((height, width), np.nan, dtype='float32')
        arr, _ = merge(datasets, bounds=bounds, res=(res, res), resampling=resampling, nodata=np.nan,
                       dtype='float32', target_aligned_pixels=False)
    finally:
        for d in reversed(opened):
            d.close()
    z = arr[0][:height, :width]
    if z.shape != (height, width):  # merge rounds its own shape; pad to the frame
        out = np.full((height, width), np.nan, dtype='float32')
        out[:z.shape[0], :z.shape[1]] = z
        z = out
    return z


def elevation_2m(cell_id, lidar_paths, dem10m_paths, exists=None):
    """The 2 m mosaic: lidar where any covers, else the ~10 m DEM (bilinear), else NaN.

    Returns (z, transform, crs, fractions) with fractions of the buffered frame from each source.
    """
    crs, transform, width, height = utm_frame(cell_id, 2.0)
    with rasterio.Env(**GDAL_ENV):
        z = _mosaic(lidar_paths, crs, transform, width, height, Resampling.average)
        lidar = ~np.isnan(z)
        if not lidar.all():
            present = [p for p in dem10m_paths if exists is None or exists(p)]
            fill = _mosaic(present, crs, transform, width, height, Resampling.bilinear)
            z = np.where(lidar, z, fill)
    filled = ~np.isnan(z)
    n = z.size
    fractions = dict(lidar=round(float(lidar.sum()) / n, 4),
                     dem10m=round(float((filled & ~lidar).sum()) / n, 4),
                     none=round(float((~filled).sum()) / n, 4))
    return z, transform, crs, fractions


def resample(z, transform, crs, res):
    """`z` averaged onto the same frame at a coarser `res` (the 3 m DEM from the 2 m one)."""
    left, top = transform.c, transform.f
    width = round(z.shape[1] * transform.a / res)
    height = round(z.shape[0] * transform.a / res)
    dst_t = from_origin(left, top, res, res)
    out = np.full((height, width), np.nan, dtype='float32')
    reproject(z, out, src_transform=transform, src_crs=crs, dst_transform=dst_t, dst_crs=crs,
              resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
    return out, dst_t


def block_mean(z, k):
    """Mean of k x k blocks, ignoring NaN; an all-NaN block stays NaN."""
    if k == 1:
        return z
    h, w = (z.shape[0] // k) * k, (z.shape[1] // k) * k
    blocks = z[:h, :w].reshape(h // k, k, w // k, k)
    with np.errstate(invalid='ignore'):
        count = np.sum(~np.isnan(blocks), axis=(1, 3))
        total = np.nansum(blocks, axis=(1, 3))
        out = np.where(count > 0, total / np.maximum(count, 1), np.nan)
    return out.astype('float32')
