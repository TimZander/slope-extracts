"""Slope classes from a DEM, and their polygons clipped to the cell, in 24-bit map units."""
import numpy as np
from rasterio import features
from rasterio.warp import transform_geom
from shapely import make_valid
from shapely.geometry import Polygon, box, mapping, shape

from . import grid


def slope_degrees(z, res):
    gy, gx = np.gradient(z, res, res)
    with np.errstate(invalid='ignore'):
        return np.degrees(np.arctan(np.hypot(gx, gy))).astype('float32')


def classify(z, res, edges, sieve):
    """Class i (1-based) for edges[i-1] <= slope < edges[i]; 0 below the first edge or where there is
    no elevation. Regions under `sieve` pixels are merged into their neighbours."""
    s = slope_degrees(z, res)
    cls = np.digitize(np.nan_to_num(s, nan=0.0), edges).astype('uint8')
    del s
    if sieve > 1:
        cls = features.sieve(cls, size=sieve, connectivity=8)
    return cls


def _ring_units(coords):
    """A ring as [(y, x), ...] in map units, without the closing point or repeated points."""
    pts = []
    for lon, lat in coords:
        p = (grid.to_units(lat), grid.to_units(lon))
        if not pts or pts[-1] != p:
            pts.append(p)
    while len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return pts if len(pts) >= 3 else None


def polygons(cls, transform, crs, cell_id, edges, keep, simplify, min_area):
    """{lower bound: [polygon]} for the kept classes, each polygon a list of rings in map units,
    outer ring first. Simplified and filtered by area in metres before being reprojected and clipped,
    so a polygon crossing the cell edge passes or fails the same in both cells."""
    south, west, north, east = grid.cell_bounds(cell_id)
    cell = box(west, south, east, north)
    wanted = {i + 1: edges[i] for i in range(len(edges)) if edges[i] in keep}
    out = {edges[i - 1]: [] for i in wanted}
    for geom, value in features.shapes(cls, mask=cls > 0, transform=transform, connectivity=8):
        bound = wanted.get(int(value))
        if bound is None:
            continue
        g = shape(geom).simplify(simplify, preserve_topology=True)
        if g.is_empty or g.area < min_area:
            continue
        g = shape(transform_geom(crs, 'EPSG:4326', mapping(g)))
        if not g.is_valid:
            g = make_valid(g)
        g = g.intersection(cell)
        for p in getattr(g, 'geoms', [g]):
            if not isinstance(p, Polygon) or p.is_empty:
                continue
            outer = _ring_units(p.exterior.coords)
            if outer is None:
                continue
            holes = [r for r in (_ring_units(i.coords) for i in p.interiors) if r is not None]
            out[bound].append([outer, *holes])
    return out
