"""The cell file format, "slope-cell" version 1 (garmin-map's slope layer reads it).

A cell file is gzip-compressed JSON (UTF-8), served as `<region>/<cell>/<layer>.json.gz`:

    {"format": "slope-cell", "version": 1, "cell": "158_-425", "layer": "t0-3m",
     "tiers": {"0": {"30": [polygon, ...], "35": [...], ...}}}

- `tiers` maps a tier ("0"-"4") to its classes; a class is its lower slope bound in degrees, as a
  string, and its upper bound is the next class's in that tier.
- A polygon is a list of rings, outer ring first, then holes.
- A ring is a flat list of integers [y0, x0, dy1, dx1, dy2, dx2, ...]: its first point in 24-bit
  Garmin map units (lat, lon times 2**24 / 360, rounded), then each next point as the difference
  from the one before. At least 3 points; the ring closes back to its first point implicitly.

A split cell (one too large to publish whole) is four quarter files instead, served as
`<region>/<cell>/<quarter>/<layer>.json.gz`, each with one more key, `quarter` (its "<qrow>_<qcol>"
id), after `cell`, which stays the parent cell's id.

The contract is only geometry per class, so anything that computes the same classes (a later
on-demand builder, say) can write the same file.
"""
import gzip
import json

FORMAT, VERSION = 'slope-cell', 1


def encode_ring(points):
    y0, x0 = points[0]
    flat = [y0, x0]
    py, px = y0, x0
    for y, x in points[1:]:
        flat += [y - py, x - px]
        py, px = y, x
    return flat


def decode_ring(flat):
    if len(flat) < 6 or len(flat) % 2:
        raise ValueError('a ring needs an even count of at least 6 integers')
    y, x = flat[0], flat[1]
    pts = [(y, x)]
    for i in range(2, len(flat), 2):
        y += flat[i]
        x += flat[i + 1]
        pts.append((y, x))
    return pts


def build(cell_id, layer, tiers, quarter=None):
    """tiers: {tier int: {lower bound int: [polygon of rings of (y, x)]}}; quarter: a split cell's quarter."""
    doc = {'format': FORMAT, 'version': VERSION, 'cell': cell_id}
    if quarter is not None:
        doc['quarter'] = quarter
    doc['layer'] = layer
    doc['tiers'] = {str(t): {str(b): [[encode_ring(r) for r in poly] for poly in polys]
                             for b, polys in sorted(classes.items())}
                    for t, classes in sorted(tiers.items())}
    return doc


def json_bytes(doc):
    """The document's JSON, as a file holds it unpacked."""
    return json.dumps(doc, separators=(',', ':')).encode()


def compress(raw):
    # mtime=0: the same cell builds to the same bytes, so an unchanged cell changes nothing on publish.
    return gzip.compress(raw, compresslevel=9, mtime=0)


def dumps(doc):
    return compress(json_bytes(doc))


def loads(data):
    doc = json.loads(gzip.decompress(data))
    if doc.get('format') != FORMAT or doc.get('version') != VERSION:
        raise ValueError('not a slope-cell version 1 file')
    return doc


def stats(doc):
    """{tier: {"polygons": n, "points": n}} of a cell document."""
    out = {}
    for t, classes in doc['tiers'].items():
        polys = [p for ps in classes.values() for p in ps]
        out[t] = {'polygons': len(polys), 'points': sum(len(r) // 2 for p in polys for r in p)}
    return out
