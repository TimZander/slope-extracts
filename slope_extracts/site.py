"""The published site: the areas list, the manifest and tile indexes, and planning which cells a run builds.

Standard library only (the plan and deploy jobs install nothing).

Site layout (manifest version 2, the coordinate grid), deployed to Cloudflare Pages (project
slope-extracts) from a manifest of file hashes:
    manifest.json                       format slope-extract version 2: the tiles and the areas
    tiles/<tile>/index.json             a 2-degree tile's covered cells and built cells' entries
    tiles/<tile>/overview.json.gz       its built cells' tier 4 (see overview.py)
    cells/<cell>/<layer>.json.gz        a whole cell's layer (see cellfile.py), unless left out or empty
    cells/<cell>/<quarter>/<layer>.json.gz
                                        a split cell's quarter's layer
    hashes.json                         every other file's Pages hash, so a deploy needn't read it back
    404.html, LICENSE.txt
    _headers                            sent beside the deployment, not as one of its files

A cell is built and stored once, however many areas cover it. Version 1 (regions, `<region>/<cell>/…`)
is read only on the first run on the grid, to move its cells.
"""
import json
import re

from . import grid

AREA_ID = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
REGION_ID = AREA_ID
LAYERS = ('t0-3m', 't0-2m', 't1-4')
# A layer too large to publish is left out: no file, and this entry. Only t0-2m may be (its bands are
# also in t0-3m at 3 m). A layer with no polygon is empty: no file, `tiers` {}. A layer file is gzip,
# never 0 bytes, so bytes 0 means one of these two and nothing else.
OPTIONAL_LAYER = 't0-2m'
LEFT_OUT_TIERS = {'0': {'polygons': 0, 'points': 0}}
EMPTY_TIERS = {}
MAX_SITE_FILES = 19000
ATTRIBUTION = 'Elevation: USGS 3D Elevation Program (3DEP), public domain'
REPOSITORY_URL = 'https://github.com/TimZander/slope-extracts'
BOUND_KEYS = ('south', 'west', 'north', 'east')
AREA_KEYS = {'id', 'name', 'boxes'}
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
MASK = re.compile(r'^[0-9a-f]{16}$')
TILE_ENTRY_KEYS = ('covered', 'built', 'coveredMask', 'builtMask', 'indexBytes')


def _is_obj(v):
    return isinstance(v, dict)


def _is_int(v):
    return type(v) is int and v >= 0


# --- areas ---------------------------------------------------------------------------------------

def _validate_box(b, where):
    if not _is_obj(b) or set(b) != set(BOUND_KEYS) or not all(isinstance(b[k], (int, float)) and not isinstance(b[k], bool) for k in BOUND_KEYS):
        raise ValueError(f'{where}: a box must be exactly numeric south, west, north, east')
    if not (-90 <= b['south'] < b['north'] <= 90 and -180 <= b['west'] < b['east'] <= 180):
        raise ValueError(f'{where}: a box is out of order or range')


def _validate_area(a):
    if not _is_obj(a) or set(a) != AREA_KEYS:
        raise ValueError(f'an area must have exactly id, name and boxes: {a!r}')
    if not isinstance(a['id'], str) or not AREA_ID.match(a['id']):
        raise ValueError(f'area id {a["id"]!r} is not valid')
    if not isinstance(a['name'], str) or not a['name'].strip():
        raise ValueError(f'area {a["id"]}: name is blank')
    if not isinstance(a['boxes'], list) or not a['boxes']:
        raise ValueError(f'area {a["id"]}: boxes must be a non-empty list')
    for b in a['boxes']:
        _validate_box(b, f'area {a["id"]}')


def validate_areas(areas):
    if not isinstance(areas, list) or not areas:
        raise ValueError('the areas list must be a non-empty array')
    seen = set()
    for a in areas:
        _validate_area(a)
        if a['id'] in seen:
            raise ValueError(f'area id {a["id"]} is listed twice')
        seen.add(a['id'])
    return areas


def load_areas(path='areas.json'):
    with open(path) as fh:
        return validate_areas(json.load(fh))


def area_coverage(area):
    """Every cell one of the area's boxes overlaps (an edge on a cell line overlaps no cell beyond),
    each once, in row then column order."""
    cells = set()
    for b in area['boxes']:
        cells.update(grid.cells_in_bounds(b['south'], b['west'], b['north'], b['east']))
    return sorted(cells, key=grid.compare_key)


def site_coverage(areas):
    """Every covered cell once: the areas in list order, each area's coverage in order."""
    seen, out = set(), []
    for a in areas:
        for c in area_coverage(a):
            if c not in seen:
                seen.add(c)
                out.append(c)
    return out


# --- paths and layers ----------------------------------------------------------------------------

def cell_path(cell_id, layer):
    return f'cells/{cell_id}/{layer}.json.gz'


def quarter_path(cell_id, quarter, layer):
    return f'cells/{cell_id}/{quarter}/{layer}.json.gz'


def tile_index_path(tile_id):
    return f'tiles/{tile_id}/index.json'


def tile_overview_path(tile_id):
    return f'tiles/{tile_id}/overview.json.gz'


def is_split(entry):
    """Whether a checked entry is a split cell's (published as four quarters)."""
    return 'quarters' in entry


def left_out(layer_entry):
    """Whether a layer is the left-out marker (too large to publish)."""
    return layer_entry['bytes'] == 0 and layer_entry['tiers'] == LEFT_OUT_TIERS


def is_empty(layer_entry):
    """Whether a layer has no polygon and so no file."""
    return layer_entry['bytes'] == 0 and layer_entry['tiers'] == EMPTY_TIERS


def present_layers(entry):
    """The layers of a checked entry (or a quarter's) that have a file."""
    return [l for l in LAYERS if entry['layers'][l]['bytes'] > 0]


def has_polygons(layer_entry):
    return any(t['polygons'] > 0 for t in layer_entry['tiers'].values())


def files_of(cell_id, entry):
    """[(site path, quarter or None, layer, bytes)] of a checked entry's files, left-out and empty layers
    excluded: a split cell's by quarter (row then column order), then layer."""
    if is_split(entry):
        return [(quarter_path(cell_id, q, l), q, l, qe['layers'][l]['bytes'])
                for q, qe in entry['quarters'].items() for l in present_layers(qe)]
    return [(cell_path(cell_id, l), None, l, entry['layers'][l]['bytes']) for l in present_layers(entry)]


def v1_path(region_id, path):
    """A `cells/…` path's version 1 path, where the first run on the grid reads it from."""
    assert path.startswith('cells/')
    return f'{region_id}/{path[len("cells/"):]}'


# --- entries -------------------------------------------------------------------------------------

def validate_entry(e, cell_id=None, key=None, split=None, strict=True):
    """A cell's entry as a build job wrote it (with `cell`), or as a tile index holds it.

    A whole cell's has `layers` and no `quarters`; a split cell's `quarters` (exactly its four, each
    exactly `layers`) and no `layers`. `key` is the cell the entry is for (default `cell_id`); `split`
    requires one form (None: either). `strict` refuses a layer with a file but no polygon (it must be
    empty); a version 1 manifest's entries are read with strict=False, as the old pipeline wrote them."""
    if not _is_obj(e):
        raise ValueError('an entry is not an object')
    if cell_id is not None and e.get('cell') != cell_id:
        raise ValueError(f'the entry names cell {e.get("cell")!r}, not {cell_id}')
    key = cell_id if key is None else key
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
    has_layers, has_quarters = 'layers' in e, 'quarters' in e
    if has_layers == has_quarters:
        raise ValueError('an entry must have exactly one of layers (a whole cell) and quarters (a split cell)')
    if split is not None and has_quarters != split:
        raise ValueError('a cells entry must have layers, a quartered entry quarters')
    if has_layers:
        _validate_layers(e['layers'], strict=strict)
        return e
    if key is None:
        raise ValueError('a split entry needs its cell')
    quarters = e['quarters']
    if not _is_obj(quarters) or list(quarters) != grid.quarters(key):
        raise ValueError(f'quarters must be exactly {", ".join(grid.quarters(key))}, in that order')
    for q, qe in quarters.items():
        if not _is_obj(qe) or set(qe) != {'layers'}:
            raise ValueError(f'quarter {q} must have exactly layers')
        _validate_layers(qe['layers'], f'quarter {q}: ', strict=strict)
    return e


def _validate_layers(layers, where='', strict=True):
    if not _is_obj(layers) or set(layers) != set(LAYERS):
        raise ValueError(f'{where}layers must be exactly {", ".join(LAYERS)}')
    for name, l in layers.items():
        if not _is_obj(l) or set(l) != {'bytes', 'tiers'} or type(l['bytes']) is not int or l['bytes'] < 0 or not _is_obj(l['tiers']):
            raise ValueError(f'{where}layer {name} must have exactly bytes and tiers')
        for t, st in l['tiers'].items():
            if t not in {'0', '1', '2', '3', '4'} or not _is_obj(st) or set(st) != {'polygons', 'points'} or not all(type(v) is int and v >= 0 for v in st.values()):
                raise ValueError(f'{where}layer {name}: tier {t!r} must have polygon and point counts')
        if l['bytes'] == 0:
            if l['tiers'] == EMPTY_TIERS:
                continue  # an empty layer: no polygon, no file
            if name != OPTIONAL_LAYER or l['tiers'] != LEFT_OUT_TIERS:
                raise ValueError(f'{where}layer {name}: bytes 0 is an empty layer (tiers {{}}) or, on {OPTIONAL_LAYER} only, '
                                 f'the left-out marker (tiers {json.dumps(LEFT_OUT_TIERS)})')
        elif strict and not has_polygons(l):
            raise ValueError(f'{where}layer {name}: a layer with no polygon has no file (bytes 0, tiers {{}})')


def _layers_copy(layers):
    return {l: {'bytes': layers[l]['bytes'],
                'tiers': {t: {'polygons': v['polygons'], 'points': v['points']} for t, v in layers[l]['tiers'].items()}}
            for l in LAYERS}


def manifest_entry(e):
    """A checked entry, rebuilt field by field so no unchecked key reaches a tile index."""
    out = {
        'recipe': e['recipe'], 'built': e['built'],
        'sources': {k: e['sources'][k] for k in ('lidar', 'dem10m', 'none')},
        'projects': list(e['projects']),
    }
    if is_split(e):
        out['quarters'] = {q: {'layers': _layers_copy(qe['layers'])} for q, qe in e['quarters'].items()}
    else:
        out['layers'] = _layers_copy(e['layers'])
    return out


def _emptied(layers):
    """A version 1 entry's layers, with a file of no polygon turned into an empty layer."""
    return {l: ({'bytes': 0, 'tiers': {}} if v['bytes'] > 0 and not has_polygons(v) else v) for l, v in layers.items()}


# --- the version 1 manifest (read on the first run on the grid) ----------------------------------

def validate_manifest(m):
    """A version 1 manifest, read as before grid-v2: regions with at least id, coverage, cells and,
    optionally, quartered (other keys ignored)."""
    if not _is_obj(m) or m.get('format') != 'slope-extract' or m.get('version') != 1:
        raise ValueError('not a slope-extract version 1 manifest')
    if not isinstance(m.get('regions'), list):
        raise ValueError('the manifest has no regions array')
    for r in m['regions']:
        if not _is_obj(r) or not isinstance(r.get('id'), str) or not REGION_ID.match(r['id']):
            raise ValueError('a manifest region has no valid id')
        if not isinstance(r.get('coverage'), list) or not _is_obj(r.get('cells')):
            raise ValueError(f'region {r["id"]}: coverage and cells are required')
        if not _is_obj(r.get('quartered', {})):
            raise ValueError(f'region {r["id"]}: quartered must be an object')
        for c, e in r['cells'].items():
            grid.parse_cell(c)
            validate_entry(e, key=c, split=False, strict=False)
        for c, e in r.get('quartered', {}).items():
            grid.parse_cell(c)
            if c in r['cells']:
                raise ValueError(f'region {r["id"]}: cell {c} is in both cells and quartered')
            validate_entry(e, key=c, split=True, strict=False)
    return m


def v1_cells(m):
    """({cell: entry}, {cell: region id}) of a checked version 1 manifest: a cell listed by two regions
    takes the first one's entry; a layer with a file and no polygon becomes empty."""
    cells, regions = {}, {}
    for r in m['regions']:
        for c, e in {**r['cells'], **r.get('quartered', {})}.items():
            if c in cells:
                continue
            e = manifest_entry(e)
            if is_split(e):
                e['quarters'] = {q: {'layers': _emptied(qe['layers'])} for q, qe in e['quarters'].items()}
            else:
                e['layers'] = _emptied(e['layers'])
            cells[c], regions[c] = e, r['id']
    return cells, regions


# --- tiles and the version 2 manifest ------------------------------------------------------------

def build_tiles(areas, cells):
    """{tile: tile index} for every tile holding a covered cell, tiles in row then column order; `cells`
    {cell: entry} gives the built ones (any outside the coverage are left out)."""
    by_tile = {}
    for c in sorted(site_coverage(areas), key=grid.compare_key):
        by_tile.setdefault(grid.tile_of(c), []).append(c)
    out = {}
    for t in sorted(by_tile, key=grid.compare_key):
        cov = by_tile[t]
        built = [c for c in cov if c in cells]
        out[t] = {'format': 'slope-tile', 'version': 1, 'tile': t, 'coverage': cov,
                  'cells': {c: cells[c] for c in built if not is_split(cells[c])},
                  'quartered': {c: cells[c] for c in built if is_split(cells[c])}}
    return out


def tile_index_bytes(doc):
    return (json.dumps(doc, indent=1) + '\n').encode()


def tile_built(doc):
    """A tile index's built cells, in row then column order."""
    return sorted({**doc['cells'], **doc['quartered']}, key=grid.compare_key)


def build_manifest(areas, tiles, index_bytes, overviews):
    """The version 2 manifest from the tile indexes, their files' sizes and their overviews' entries."""
    entries = {}
    for t, doc in tiles.items():
        built = tile_built(doc)
        e = {'covered': len(doc['coverage']), 'built': len(built), 'coveredMask': grid.mask(doc['coverage']),
             'builtMask': grid.mask(built), 'indexBytes': index_bytes[t]}
        if t in overviews:
            e['overview'] = overviews[t]
        entries[t] = e
    area_list = []
    for a in areas:
        ts = sorted({grid.tile_of(c) for c in area_coverage(a)}, key=grid.compare_key)
        area_list.append({'id': a['id'], 'name': a['name'], 'boxes': [dict(b) for b in a['boxes']], 'tiles': ts})
    return {'format': 'slope-extract', 'version': 2, 'attribution': ATTRIBUTION,
            'cellFormat': {'format': 'slope-cell', 'version': 1}, 'layers': list(LAYERS),
            'tiles': entries, 'areas': area_list}


def validate_manifest_v2(m):
    if not _is_obj(m) or set(m) != {'format', 'version', 'attribution', 'cellFormat', 'layers', 'tiles', 'areas'}:
        raise ValueError('a version 2 manifest has exactly format, version, attribution, cellFormat, layers, tiles and areas')
    if m['format'] != 'slope-extract' or m['version'] != 2:
        raise ValueError('not a slope-extract version 2 manifest')
    if not isinstance(m['attribution'], str) or m['cellFormat'] != {'format': 'slope-cell', 'version': 1} or m['layers'] != list(LAYERS):
        raise ValueError('attribution, cellFormat or layers is not as this pipeline writes them')
    if not _is_obj(m['tiles']):
        raise ValueError('tiles must be an object')
    for t, e in m['tiles'].items():
        grid.parse_tile(t)
        if not _is_obj(e) or not set(TILE_ENTRY_KEYS) <= set(e) or set(e) - set(TILE_ENTRY_KEYS) - {'overview'}:
            raise ValueError(f'tile {t}: its entry must have exactly {", ".join(TILE_ENTRY_KEYS)} and optionally overview')
        if not all(_is_int(e[k]) for k in ('covered', 'built', 'indexBytes')) or e['indexBytes'] == 0:
            raise ValueError(f'tile {t}: covered, built and indexBytes must be counts')
        if not all(isinstance(e[k], str) and MASK.fullmatch(e[k]) for k in ('coveredMask', 'builtMask')):
            raise ValueError(f'tile {t}: masks must be 16 lowercase hex digits')
    if not isinstance(m['areas'], list):
        raise ValueError('areas must be a list')
    for a in m['areas']:
        if not _is_obj(a) or set(a) != {'id', 'name', 'boxes', 'tiles'}:
            raise ValueError('a manifest area has exactly id, name, boxes and tiles')
        _validate_area({k: a[k] for k in ('id', 'name', 'boxes')})
        if not isinstance(a['tiles'], list) or not all(isinstance(t, str) for t in a['tiles']):
            raise ValueError(f'area {a["id"]}: tiles must be a list of tile ids')
    return m


def validate_tile_index(doc, tile, tile_entry):
    """A live tile index, checked against its tile and its entry in the manifest; its {cell: entry}."""
    if not _is_obj(doc) or list(doc) != ['format', 'version', 'tile', 'coverage', 'cells', 'quartered']:
        raise ValueError(f'tile {tile}: an index has exactly format, version, tile, coverage, cells and quartered')
    if doc['format'] != 'slope-tile' or doc['version'] != 1 or doc['tile'] != tile:
        raise ValueError(f'tile {tile}: not the slope-tile version 1 index of this tile')
    cov = doc['coverage']
    if not isinstance(cov, list) or not all(isinstance(c, str) for c in cov):
        raise ValueError(f'tile {tile}: coverage must be a list of cells')
    for c in cov:
        grid.parse_cell(c)
        if grid.tile_of(c) != tile:
            raise ValueError(f'tile {tile}: cell {c} lies outside the tile')
    if cov != sorted(set(cov), key=grid.compare_key):
        raise ValueError(f'tile {tile}: coverage must be each cell once, in row then column order')
    if not _is_obj(doc['cells']) or not _is_obj(doc['quartered']):
        raise ValueError(f'tile {tile}: cells and quartered must be objects')
    covered = set(cov)
    for c in [*doc['cells'], *doc['quartered']]:
        grid.parse_cell(c)
        if c not in covered:
            raise ValueError(f'tile {tile}: built cell {c} is outside its coverage')
    both = set(doc['cells']) & set(doc['quartered'])
    if both:
        raise ValueError(f'tile {tile}: cell {sorted(both)[0]} is in both cells and quartered')
    for c, e in doc['cells'].items():
        validate_entry(e, key=c, split=False)
    for c, e in doc['quartered'].items():
        validate_entry(e, key=c, split=True)
    built = tile_built(doc)
    if (tile_entry['covered'], tile_entry['built']) != (len(cov), len(built)):
        raise ValueError(f'tile {tile}: its counts differ from the manifest\'s')
    if (tile_entry['coveredMask'], tile_entry['builtMask']) != (grid.mask(cov), grid.mask(built)):
        raise ValueError(f'tile {tile}: its masks differ from the manifest\'s')
    return {**doc['cells'], **doc['quartered']}


# --- the plan ------------------------------------------------------------------------------------

def plan(areas, live, current_recipe, max_cells, per_job, today=None, refresh_days=None):
    """The cells this run builds, as job chunks of plain cell ids: [[cell, ...], ...].

    `live` is fetch_live's view of the live site (None: no site yet). A covered cell is built when the
    live site lacks it, built it with another recipe or more than `refresh_days` ago (the yearly refresh),
    or lists it whole with t0-2m left out (not empty: a split cell's left-out quarter, or an empty layer,
    would only build the same again). At most `max_cells` per run, in the areas' order, each cell once.
    """
    import datetime
    today = today or datetime.date.today()
    refresh_days = REFRESH_DAYS if refresh_days is None else refresh_days
    prev = (live or {}).get('cells', {})
    todo = []
    for c in site_coverage(areas):
        e = prev.get(c)
        if (e is None or e.get('recipe') != current_recipe
                or (today - datetime.date.fromisoformat(e['built'])).days > refresh_days
                or (not is_split(e) and left_out(e['layers'][OPTIONAL_LAYER]))):
            todo.append(c)
    todo = todo[:max_cells]
    return [todo[i:i + per_job] for i in range(0, len(todo), per_job)]


# --- the fixed files -----------------------------------------------------------------------------

HEADERS = """/*
  Access-Control-Allow-Origin: *
  X-Content-Type-Options: nosniff

/cells/*
  Cache-Control: public, max-age=86400

/tiles/:tile/index.json
  Cache-Control: public, max-age=300

/tiles/:tile/overview.json.gz
  Cache-Control: public, max-age=3600

/LICENSE.txt
  Cache-Control: public, max-age=3600

/manifest.json
  Cache-Control: public, max-age=300

/hashes.json
  Cache-Control: public, max-age=300
"""

NOT_FOUND_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Not found</title></head>
<body><p>Not found. This site holds slope-angle cells; see <a href="/manifest.json">manifest.json</a>.</p></body>
</html>
"""


def license_text(cells):
    """`cells`: {cell: entry} of every built cell."""
    projects = sorted({p for e in cells.values() for p in e['projects']})
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


def site_files(tiles):
    """Every file the deployment names: each tile's index (and overview, with a built cell), every built
    cell's files, and the fixed files. `_headers` goes beside the deployment, so it isn't one."""
    paths = ['manifest.json', 'hashes.json', '404.html', 'LICENSE.txt']
    for t, doc in tiles.items():
        paths.append(tile_index_path(t))
        built = {**doc['cells'], **doc['quartered']}
        if built:
            paths.append(tile_overview_path(t))
        for c, e in built.items():
            paths += [f[0] for f in files_of(c, e)]
    return paths


def main_plan(argv=None):
    """python -m slope_extracts.site -> `jobs`, `count`, `had_manifest` and `manifest_version` lines for
    $GITHUB_OUTPUT. Reads the live site (public: no credential), with the first-deploy switch."""
    import argparse
    import sys
    from . import publish, recipe
    ap = argparse.ArgumentParser()
    ap.parse_args(argv)
    try:
        areas = load_areas()
        live = publish.fetch_live(publish.SITE_URL, publish.http_get, first_deploy=publish.first_deploy_on())
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as e:
        print(f'::error::{publish.safe(str(e))}', file=sys.stderr)
        return 1
    chunks = plan(areas, live, recipe.RECIPE, MAX_CELLS_PER_RUN, CELLS_PER_JOB)
    jobs = [' '.join(chunk) for chunk in chunks]
    print(f'jobs={json.dumps(jobs)}')
    print(f'count={sum(len(c) for c in chunks)}')
    print(f'had_manifest={"true" if live is not None else "false"}')
    print(f'manifest_version={live["version"] if live is not None else "none"}')
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
