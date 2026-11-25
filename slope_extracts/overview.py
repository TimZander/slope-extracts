"""A region's overview, "slope-overview" version 1 (garmin-map's slope layer draws it zoomed out).

Served as `<region>/overview.json.gz`, gzip JSON:

    {"format": "slope-overview", "version": 1, "region": "colorado",
     "tiers": {"4": {"30": [polygon, ...]}}}

The tier-4 polygons (30°+) of every built cell of the region, cells in coverage order, each cell's
polygons in its `t1-4` file's order, rings encoded as in a cell (see cellfile.py). The deploy job
writes it from the cell files it is about to publish, after their checks, and never reads one back.

Standard library only (the deploy job installs nothing).
"""
import gzip
import json

from . import cellfile

FORMAT, VERSION = 'slope-overview', 1
# The limits of a cell file (publish.MAX_FILE_BYTES, publish.MAX_CELL_JSON).
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_JSON_BYTES = 64 * 1024 * 1024


def build(region_id, t1_4_paths):
    """The overview document from a region's checked `t1-4` files, in coverage order; None with none."""
    if not t1_4_paths:
        return None
    polygons = []
    for path in t1_4_paths:
        with gzip.open(path, 'rb') as fh:
            doc = json.loads(fh.read())
        polygons += doc['tiers'].get('4', {}).get('30', [])
    return {'format': FORMAT, 'version': VERSION, 'region': region_id, 'tiers': {'4': {'30': polygons}}}


def dumps(doc):
    """The file's bytes; fails when the file or its JSON passes a cell file's limit."""
    raw = json.dumps(doc, separators=(',', ':')).encode()
    if len(raw) > MAX_JSON_BYTES:
        raise RuntimeError(f'the {doc["region"]} overview unpacks to {len(raw)} bytes, over {MAX_JSON_BYTES}')
    data = gzip.compress(raw, compresslevel=9, mtime=0)
    if len(data) > MAX_FILE_BYTES:
        raise RuntimeError(f'the {doc["region"]} overview is {len(data)} bytes, over {MAX_FILE_BYTES}')
    return data


def entry(doc, data):
    """The manifest's `overview` entry: its bytes, and its polygons and points as a cell tier's."""
    counts = cellfile.stats(doc)['4']
    return {'bytes': len(data), 'polygons': counts['polygons'], 'points': counts['points']}
