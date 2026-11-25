"""The published site: regions list, manifest, and planning which cells a run builds.

Standard library only (the plan and deploy jobs install nothing).

Site layout, deployed to Cloudflare Pages (project slope-extracts) by Direct Upload:
    manifest.json                       every region, its coverage and its built cells
    <region>/<cell>/<layer>.json.gz     one file per built cell and layer (see cellfile.py)
    _headers, 404.html, LICENSE.txt
"""
import json
import os
import re

from . import grid

REGION_ID = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
LAYERS = ('t0-3m', 't0-2m', 't1-4')
MAX_SITE_FILES = 19000
ATTRIBUTION = 'Elevation: USGS 3D Elevation Program (3DEP), public domain'
REPOSITORY_URL = 'https://github.com/TimZander/slope-extracts'
BOUND_KEYS = ('south', 'west', 'north', 'east')
REGION_KEYS = {'id', 'name', 'bounds', 'only'}
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _is_obj(v):
    return isinstance(v, dict)


def validate_regions(regions):
    if not isinstance(regions, list) or not regions:
        raise ValueError('the regions list must be a non-empty array')
    seen = set()
    for r in regions:
        if not _is_obj(r) or set(r) - REGION_KEYS or not {'id', 'name', 'bounds'} <= set(r):
            raise ValueError(f'a region must have exactly id, name, bounds and optionally only: {r!r}')
        if not isinstance(r['id'], str) or not REGION_ID.match(r['id']):
            raise ValueError(f'region id {r["id"]!r} is not valid')
        if r['id'] in seen:
            raise ValueError(f'region id {r["id"]} is listed twice')
        seen.add(r['id'])
        if not isinstance(r['name'], str) or not r['name'].strip():
            raise ValueError(f'region {r["id"]}: name is blank')
        b = r['bounds']
        if not _is_obj(b) or set(b) != set(BOUND_KEYS) or not all(isinstance(b[k], (int, float)) and not isinstance(b[k], bool) for k in BOUND_KEYS):
            raise ValueError(f'region {r["id"]}: bounds must be exactly numeric south, west, north, east')
        if not (-90 <= b['south'] < b['north'] <= 90 and -180 <= b['west'] < b['east'] <= 180):
            raise ValueError(f'region {r["id"]}: bounds are out of order or range')
        if 'only' in r:
            cov = set(coverage(r))
            if not isinstance(r['only'], list) or not r['only'] or not all(isinstance(c, str) and c in cov for c in r['only']):
                raise ValueError(f'region {r["id"]}: only must be a non-empty list of cells in its coverage')
    return regions


def load_regions(path='regions.json'):
    with open(path) as fh:
        return validate_regions(json.load(fh))


def coverage(region):
    b = region['bounds']
    return grid.cells_in_bounds(b['south'], b['west'], b['north'], b['east'])


def layer_path(region_id, cell_id, layer):
    return f'{region_id}/{cell_id}/{layer}.json.gz'


def validate_entry(e, cell_id=None):
    """A cell's entry as a build job wrote it (or as the manifest holds it, without `cell`)."""
    if not _is_obj(e):
        raise ValueError('an entry is not an object')
    if cell_id is not None and e.get('cell') != cell_id:
        raise ValueError(f'the entry names cell {e.get("cell")!r}, not {cell_id}')
    if type(e.get('recipe')) is not int or e['recipe'] < 1:
        raise ValueError('recipe must be a positive integer')
    if not isinstance(e.get('built'), str) or not DATE.fullmatch(e['built']):
        raise ValueError('built must be YYYY-MM-DD')
    import datetime
    try:
        built = datetime.date.fromisoformat(e['built'])
    except ValueError:
        raise ValueError('built is not a date')
    if built > datetime.date.today() + datetime.timedelta(days=1):
        raise ValueError('built is in the future')
    src = e.get('sources')
    if not _is_obj(src) or set(src) != {'lidar', 'dem10m', 'none'} or not all(type(v) in (int, float) and 0 <= v <= 1 for v in src.values()):
        raise ValueError('sources must be the lidar, dem10m and none fractions')
    if not isinstance(e.get('projects'), list) or not all(isinstance(p, str) and re.fullmatch(r'[A-Za-z0-9_]{1,100}', p) for p in e['projects']):
        raise ValueError('projects must be a list of 3DEP project names')
    layers = e.get('layers')
    if not _is_obj(layers) or set(layers) != set(LAYERS):
        raise ValueError(f'layers must be exactly {", ".join(LAYERS)}')
    for name, l in layers.items():
        if not _is_obj(l) or set(l) != {'bytes', 'tiers'} or type(l['bytes']) is not int or l['bytes'] < 0 or not _is_obj(l['tiers']):
            raise ValueError(f'layer {name} must have exactly bytes and tiers')
        for t, s in l['tiers'].items():
            if t not in {'0', '1', '2', '3', '4'} or not _is_obj(s) or set(s) != {'polygons', 'points'} or not all(type(v) is int and v >= 0 for v in s.values()):
                raise ValueError(f'layer {name}: tier {t!r} must have polygon and point counts')
    return e


def manifest_entry(e):
    """A checked entry, rebuilt field by field so no unchecked key reaches the manifest."""
    return {
        'recipe': e['recipe'], 'built': e['built'],
        'sources': {k: e['sources'][k] for k in ('lidar', 'dem10m', 'none')},
        'projects': list(e['projects']),
        'layers': {l: {'bytes': e['layers'][l]['bytes'],
                       'tiers': {t: {'polygons': v['polygons'], 'points': v['points']} for t, v in e['layers'][l]['tiers'].items()}}
                   for l in LAYERS},
    }


def validate_manifest(m):
    if not _is_obj(m) or m.get('format') != 'slope-extract' or m.get('version') != 1:
        raise ValueError('not a slope-extract version 1 manifest')
    if not isinstance(m.get('regions'), list):
        raise ValueError('the manifest has no regions array')
    for r in m['regions']:
        if not _is_obj(r) or not isinstance(r.get('id'), str) or not REGION_ID.match(r['id']):
            raise ValueError('a manifest region has no valid id')
        if not isinstance(r.get('coverage'), list) or not _is_obj(r.get('cells')):
            raise ValueError(f'region {r["id"]}: coverage and cells are required')
        for c, e in r['cells'].items():
            grid.parse_cell(c)
            validate_entry(e)
    return m


def build_manifest(regions, cells_by_region):
    """cells_by_region: {region id: {cell id: manifest entry}}."""
    out = []
    for r in regions:
        cov = coverage(r)
        cells = cells_by_region.get(r['id'], {})
        out.append({
            'id': r['id'], 'name': r['name'], 'bounds': dict(r['bounds']), 'coverage': cov,
            'cells': {c: cells[c] for c in sorted(cells, key=grid.compare_key) if c in set(cov)},
        })
    return {'format': 'slope-extract', 'version': 1, 'attribution': ATTRIBUTION,
            'cellFormat': {'format': 'slope-cell', 'version': 1}, 'layers': list(LAYERS), 'regions': out}


def plan(regions, previous_manifest, current_recipe, max_cells, per_job, today=None, refresh_days=None):
    """The cells this run builds, as job chunks: [[(region, cell), ...], ...].

    A cell is built when it is in its region's coverage (or `only` list) and the live site lacks it,
    built it with another recipe, or built it more than `refresh_days` ago (the yearly refresh). At
    most `max_cells` per run, in coverage order, so one run's build and upload stay bounded; the next
    run picks up the rest.
    """
    import datetime
    today = today or datetime.date.today()
    refresh_days = REFRESH_DAYS if refresh_days is None else refresh_days
    prev = {}
    for r in (previous_manifest or {}).get('regions', []):
        prev[r['id']] = r.get('cells', {})
    todo = []
    for r in regions:
        for c in r.get('only') or coverage(r):
            e = prev.get(r['id'], {}).get(c)
            if (e is None or e.get('recipe') != current_recipe
                    or (today - datetime.date.fromisoformat(e['built'])).days > refresh_days):
                todo.append((r['id'], c))
    todo = todo[:max_cells]
    return [todo[i:i + per_job] for i in range(0, len(todo), per_job)]


HEADERS = """/*
  Access-Control-Allow-Origin: *
  X-Content-Type-Options: nosniff

/:region/*
  Cache-Control: public, max-age=86400

/LICENSE.txt
  Cache-Control: public, max-age=3600

/manifest.json
  Cache-Control: public, max-age=300
"""

NOT_FOUND_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Not found</title></head>
<body><p>Not found. This site holds slope-angle cells; see <a href="/manifest.json">manifest.json</a>.</p></body>
</html>
"""


def license_text(manifest):
    projects = sorted({p for r in manifest['regions'] for e in r['cells'].values() for p in e['projects']})
    lines = '\n'.join(f'- {p}' for p in projects) or '- (none yet)'
    return f"""Slope-angle cells: sources and licence

The elevation data behind these files is from the USGS 3D Elevation Program (3DEP): 1 m lidar
DEMs and, where lidar has a gap, the 1/3 arc-second seamless DEM.
USGS data is in the public domain. Please credit: "U.S. Geological Survey, 3D Elevation Program".

Lidar projects used:
{lines}

The derivation (the code that computes slope classes and writes these files) is public at
{REPOSITORY_URL}
"""


def site_files(manifest):
    """Every path the manifest names, plus the fixed files."""
    paths = ['manifest.json', '_headers', '404.html', 'LICENSE.txt']
    for r in manifest['regions']:
        for c in r['cells']:
            paths += [layer_path(r['id'], c, l) for l in LAYERS]
    return paths


def main_plan(argv=None):
    """python -m slope_extracts.site -> `jobs` and `count` lines for $GITHUB_OUTPUT.

    Reads the live site's manifest (public: no credential), with the first-deploy switch from FIRST_DEPLOY."""
    import argparse
    import sys
    from . import publish, recipe
    ap = argparse.ArgumentParser()
    ap.parse_args(argv)
    try:
        regions = load_regions()
        prev = publish.fetch_manifest(first_deploy=publish.first_deploy_on())
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as e:
        print(f'::error::{e}', file=sys.stderr)
        return 1
    chunks = plan(regions, prev, recipe.RECIPE, MAX_CELLS_PER_RUN, CELLS_PER_JOB)
    jobs = [' '.join(f'{r}/{c}' for r, c in chunk) for chunk in chunks]
    print(f'jobs={json.dumps(jobs)}')
    print(f'count={sum(len(c) for c in chunks)}')
    print(f'had_manifest={"true" if prev is not None else "false"}')
    print(f'{sum(len(c) for c in chunks)} cell(s) to build in {len(jobs)} job(s)', file=sys.stderr)
    return 0


# One run builds at most this many cells (~0.75 GB of files), so a run's jobs and its upload stay
# bounded; the schedule picks up the rest.
MAX_CELLS_PER_RUN = 48
# A cell built longer ago than this is rebuilt: the yearly refresh (the DEM rarely changes).
REFRESH_DAYS = 300
# Cells per build job: a cell takes ~10 min, and a job may run 6 h.
CELLS_PER_JOB = 3


if __name__ == '__main__':
    import sys
    sys.exit(main_plan())
