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


def _ring_rounded(coords):
    """A ring of (x, y) map-unit floats as [(y, x), ...] integers, without the closing or repeated points."""
    pts = []
    for x, y in coords:
        p = (int(round(y)), int(round(x)))
        if not pts or pts[-1] != p:
            pts.append(p)
    while len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return pts if len(pts) >= 3 else None


def _flat_polygons(g):
    if isinstance(g, Polygon):
        if not g.is_empty:
            yield g
    elif hasattr(g, 'geoms'):
        for part in g.geoms:
            yield from _flat_polygons(part)


def clip_to_quarters(cell_id, by_class):
    """{quarter: {lower bound: [polygon]}} from a cell's {lower bound: [polygon]} (rings of (y, x) map
    units): each polygon cut along the quarter lines. A polygon inside one quarter goes there unchanged;
    one across a line goes, cut, to each quarter it reaches, each piece a polygon, new points rounded to
    map units. Every quarter has every class, empty or not, in the cell's order. Build job only (shapely)."""
    south, west, north, east = grid.cell_bounds(cell_id)
    ym = (south + north) / 2 * grid.UNITS_PER_DEG
    xm = (west + east) / 2 * grid.UNITS_PER_DEG
    # outer edges well past the cell's, so only the quarter lines cut (points already lie in the cell)
    y0, y1 = grid.to_units(south) - 10, grid.to_units(north) + 10
    x0, x1 = grid.to_units(west) - 10, grid.to_units(east) + 10
    qs = grid.quarters(cell_id)
    boxes = [box(x0, y0, xm, ym), box(xm, y0, x1, ym), box(x0, ym, xm, y1), box(xm, ym, x1, y1)]
    out = {q: {b: [] for b in by_class} for q in qs}

    def side(lo, hi, mid):
        return 0 if hi < mid else 1 if lo > mid else None

    for b, polys in by_class.items():
        for poly in polys:
            ys = [y for y, _x in poly[0]]
            xs = [x for _y, x in poly[0]]
            i, j = side(min(ys), max(ys), ym), side(min(xs), max(xs), xm)
            if i is not None and j is not None:
                out[qs[2 * i + j]][b].append(poly)
                continue
            g = Polygon([(x, y) for y, x in poly[0]], [[(x, y) for y, x in r] for r in poly[1:]])
            if not g.is_valid:
                g = make_valid(g)
            for k, q in enumerate(qs):
                ki, kj = divmod(k, 2)
                if (i is not None and ki != i) or (j is not None and kj != j):
                    continue
                for p in _flat_polygons(g.intersection(boxes[k])):
                    outer = _ring_rounded(p.exterior.coords)
                    if outer is None:
                        continue
                    holes = [r for r in (_ring_rounded(h.coords) for h in p.interiors) if r is not None]
                    out[q][b].append([outer, *holes])
    return out
