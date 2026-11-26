"""Builds one cell's three layer files and its entry.

    python -m slope_extracts.build_cell <cell-id> --out <dir> [--dem <GeoTIFF> ...]

Writes <dir>/<cell>/{t0-3m,t0-2m,t1-4}.json.gz and <dir>/<cell>/entry.json. A t0-2m layer over the
deploy job's limits is left out (no file; its entry is LEFT_OUT); any other layer over them fails the cell,
and a failed cell leaves no folder. With --dem, the given
files are the only elevation source (tests and local runs); without it the cell reads USGS 3DEP
lidar found through the TNM Access API, and the ~10 m DEM where lidar has a gap.

A cell is built from its id alone, with no region, so the same entry point can build a cell asked for
on demand later.
"""
import argparse
import copy
import datetime
import json
import os
import shutil
import sys
import time

from rasterio import Affine
from rasterio.warp import transform_bounds

from . import cellfile, classes, dem, grid, publish, recipe, sources

# The deploy job's limits per layer file: gzip bytes, and JSON bytes unpacked.
MAX_FILE_BYTES = publish.MAX_FILE_BYTES
MAX_JSON_BYTES = publish.MAX_CELL_JSON
# The only layer that may be left out, and its entry when it is: no file, nothing counted.
OPTIONAL_LAYER = 't0-2m'
LEFT_OUT = {'bytes': 0, 'tiers': {'0': {'polygons': 0, 'points': 0}}}


def _layer_bands(z, transform, crs, cell_id, p):
    cls = classes.classify(z, p['res'], p['edges'], p['sieve'])
    return classes.polygons(cls, transform, crs, cell_id, p['edges'], p['keep'], p['simplify'], p['min_area'])


def build(cell_id, out_dir, dem_paths=None, log=print, today=None):
    grid.parse_cell(cell_id)
    t_start = time.monotonic()
    if dem_paths:
        lidar, fallback, projects = list(dem_paths), [], []
    else:
        # the buffered frame in lon/lat: every tile touching it is read
        crs, ft, width, height = dem.utm_frame(cell_id, 2.0)
        lb = transform_bounds(crs, 'EPSG:4326', ft.c, ft.f - height * 2.0, ft.c + width * 2.0, ft.f)
        tiles = sources.lidar_tiles(lb[1], lb[0], lb[3], lb[2])
        lidar = [t['url'] for t in tiles]
        projects = sorted({t['project'] for t in tiles})
        fallback = sources.dem10m_tiles(lb[1], lb[0], lb[3], lb[2])
        log(f'{cell_id}: {len(lidar)} lidar tile(s) from {", ".join(projects) or "no project"}')

    exists = None if dem_paths else _http_exists
    z2, t2, crs, fractions = dem.elevation_2m(cell_id, lidar, fallback, exists=exists)
    log(f'{cell_id}: 2 m mosaic {z2.shape}, lidar {fractions["lidar"]:.1%}, 10 m {fractions["dem10m"]:.1%}, '
        f'none {fractions["none"]:.1%}')

    cliffs = _layer_bands(z2, t2, crs, cell_id, recipe.TIER0_CLIFFS)
    bands2 = _layer_bands(z2, t2, crs, cell_id, recipe.TIER0_BANDS_2M)
    tier1_cliffs = _layer_bands(z2, t2, crs, cell_id, recipe.LOW_TIERS[0]['cliffs'])
    z3, t3 = dem.resample(z2, t2, crs, 3.0)
    del z2
    bands3 = _layer_bands(z3, t3, crs, cell_id, recipe.TIER0_BANDS_3M)

    low = {}
    for p in recipe.LOW_TIERS:
        k = p['factor']
        zk = dem.block_mean(z3, k)
        tk = t3 @ Affine.scale(k)
        polys = _layer_bands(zk, tk, crs, cell_id, dict(p, res=3.0 * k))
        if p['cliffs']:
            polys.update(tier1_cliffs)
        low[p['tier']] = polys
    del z3

    docs = {
        't0-3m': cellfile.build(cell_id, 't0-3m', {0: {**bands3, **cliffs}}),
        't0-2m': cellfile.build(cell_id, 't0-2m', {0: {**bands2, **cliffs}}),
        't1-4': cellfile.build(cell_id, 't1-4', low),
    }
    cell_dir = os.path.join(out_dir, cell_id)
    os.makedirs(cell_dir, exist_ok=True)
    try:
        entry = _write(cell_id, cell_dir, docs, fractions, projects, today, log)
    except BaseException:
        # a failed cell leaves no folder, so the deploy job keeps its previous files
        shutil.rmtree(cell_dir, ignore_errors=True)
        raise
    log(f'{cell_id}: done in {time.monotonic() - t_start:.0f} s; ' +
        ', '.join(f'{n} {l["bytes"] / 1e6:.2f} MB' for n, l in entry['layers'].items()))
    return entry


def _write(cell_id, cell_dir, docs, fractions, projects, today, log):
    layers = {}
    for name, doc in docs.items():
        raw = cellfile.json_bytes(doc)
        data = cellfile.compress(raw)
        over = []
        if len(data) > MAX_FILE_BYTES:
            over.append(f'{len(data)} bytes, over the {MAX_FILE_BYTES}-byte limit per file')
        if len(raw) > MAX_JSON_BYTES:
            over.append(f'{len(raw)} bytes of JSON, over the {MAX_JSON_BYTES}-byte limit unpacked')
        if over:
            if name != OPTIONAL_LAYER:
                raise RuntimeError(f'{cell_id}/{name} is ' + ' and '.join(over))
            log(f'::warning::cell {cell_id}: layer {name} left out: it is {" and ".join(over)}; '
                f'the cell is published without it')
            layers[name] = copy.deepcopy(LEFT_OUT)
            continue
        with open(os.path.join(cell_dir, f'{name}.json.gz'), 'wb') as fh:
            fh.write(data)
        layers[name] = {'bytes': len(data), 'tiers': cellfile.stats(doc)}
    entry = {
        'cell': cell_id,
        'recipe': recipe.RECIPE,
        'built': (today or datetime.date.today()).isoformat(),
        'sources': fractions,
        'projects': projects,
        'layers': layers,
    }
    with open(os.path.join(cell_dir, 'entry.json'), 'w') as fh:
        json.dump(entry, fh, indent=1)
        fh.write('\n')
    return entry


def _http_exists(url):
    import urllib.request
    req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': sources.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200
    except Exception:
        return False


def main(argv=None):
    """Cells are given as `<cell>` or, from the workflow's plan, `<region>/<cell>`; the list as given
    is written to <out>/jobs.txt, which the deploy job checks the artifact against."""
    ap = argparse.ArgumentParser()
    ap.add_argument('cells', nargs='+')
    ap.add_argument('--out', required=True)
    ap.add_argument('--dem', action='append')
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, 'jobs.txt'), 'w') as fh:
        fh.write(' '.join(args.cells) + '\n')
    failed = []
    for item in args.cells:
        c = item.rsplit('/', 1)[-1]
        try:
            build(c, args.out, args.dem)
        except Exception as e:  # one cell's failure leaves the others' files; named, then the run fails
            print(f'::error::cell {c} failed: {e}', file=sys.stderr)
            failed.append(c)
    if failed:
        with open(os.path.join(args.out, 'failed.json'), 'w') as fh:
            json.dump(failed, fh)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
