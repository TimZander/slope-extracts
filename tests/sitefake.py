"""Shared fakes for the site tests: a live site, build-job artifacts, and a version 1 site to move from.

The Pages hash is BLAKE3, which Python's standard library lacks, so the fake site lists a stand-in hash;
the Node step's real hashing is tested in deploy/pages.test.mjs and tests/test_site_publish.py.
"""
import hashlib
import json
import os
import pathlib
import shutil

from slope_extracts import cellfile, grid, publish, site

COLORADO = {'id': 'colorado', 'name': 'Colorado',
            'boxes': [{'south': 37.01, 'west': -109.04, 'north': 40.99, 'east': -102.06}]}
AREAS = [COLORADO]
DILLON, OTHER = '158_-425', '158_-424'  # tiles 19_-54 and 19_-53 (column -424 starts the next tile)
NEIGHBOUR = '158_-426'  # beside DILLON, in its tile 19_-54
LEFT_OUT = {'bytes': 0, 'tiers': {'0': {'polygons': 0, 'points': 0}}}
EMPTY = {'bytes': 0, 'tiers': {}}
URL = 'https://slope.test'


def fake_hash(data, name):
    return hashlib.sha256(data + name.rsplit('.', 1)[-1].encode()).hexdigest()[:32]


class FakeSite:
    """The live site: path -> bytes; a missing path is a 404."""
    def __init__(self, files=None):
        self.files = dict(files or {})
        self.requests = []

    def get(self, url, limit):
        path = url.split('slope.test/', 1)[1].split('?', 1)[0]
        self.requests.append(path)
        if path not in self.files:
            return 404, b''
        if len(self.files[path]) > limit:
            raise RuntimeError(f'{url} is over {limit} bytes')
        return 200, self.files[path]

    def publish(self, out, hashes=True):
        """What deploying `out` (and its state folder) would leave live: the run's files, the kept ones by
        hash (their bytes from where the live site held them), `_headers` and `hashes.json`."""
        state = state_of(out)
        kept = json.loads((state / 'kept.json').read_text()) if (state / 'kept.json').exists() else {}
        old = self.files
        self.files = {}
        for path, k in kept.items():
            self.files[path.lstrip('/')] = old[(k.get('from') or path).lstrip('/')]
        for root, _d, names in os.walk(out):
            for n in names:
                full = os.path.join(root, n)
                self.files[os.path.relpath(full, out).replace(os.sep, '/')] = open(full, 'rb').read()
        if (state / '_headers').exists():
            self.files['_headers'] = (state / '_headers').read_bytes()
        self.files.pop('hashes.json', None)
        if hashes:
            self.set_hashes()

    def set_hashes(self):
        listed = {'/' + k: fake_hash(v, k) for k, v in self.files.items() if k not in ('_headers', 'hashes.json')}
        self.files['hashes.json'] = json.dumps({'format': 'slope-hashes', 'version': 1, 'files': listed}).encode()


def entry(cell, recipe=1, built='2026-11-23'):
    return {'cell': cell, 'recipe': recipe, 'built': built, 'sources': {'lidar': 1.0, 'dem10m': 0.0, 'none': 0.0},
            'projects': ['CO_Central_Western_2016'],
            'layers': {l: {'bytes': 9, 'tiers': {'0' if l.startswith('t0') else '4': {'polygons': 1, 'points': 3}}}
                       for l in site.LAYERS}}


def ring_in(cell, tag=0, quarter=None):
    s, w, _n, _e = grid.quarter_bounds(cell, quarter) if quarter else grid.cell_bounds(cell)
    y, x = grid.to_units(s) + 100, grid.to_units(w) + 100
    return [[(y + tag, x), (y + 10, x), (y + 10, x + 10)]]


def write_layers(cdir, cell, empty=(), left_out=(), t4=1, tag=0, quarter=None):
    """Layer files and their entries as build_cell writes them."""
    layers = {}
    for l in site.LAYERS:
        if l in left_out:
            layers[l] = dict(LEFT_OUT)
            continue
        if l in empty:
            layers[l] = dict(EMPTY)
            continue
        polys = [ring_in(cell, tag, quarter)] if l.startswith('t0') else [ring_in(cell, 20 * i + tag, quarter) for i in range(t4)]
        tiers = {0: {30: polys}} if l.startswith('t0') else {4: {30: polys}}
        doc = cellfile.build(cell, l, tiers, quarter=quarter)
        data = cellfile.dumps(doc)
        (cdir / f'{l}.json.gz').write_bytes(data)
        layers[l] = {'bytes': len(data), 'tiers': cellfile.stats(doc)}
    return layers


def fake_cell(root, cell, **kw):
    cdir = root / cell
    cdir.mkdir(parents=True)
    e = dict(entry(cell), layers=write_layers(cdir, cell, **kw))
    (cdir / 'entry.json').write_text(json.dumps(e))
    return cdir


def fake_split_cell(root, cell, t4=None, empty=None):
    cdir = root / cell
    cdir.mkdir(parents=True)
    quarters = {}
    for q in grid.quarters(cell):
        (cdir / q).mkdir()
        quarters[q] = {'layers': write_layers(cdir / q, cell, quarter=q, t4=(t4 or {}).get(q, 1),
                                              empty=(empty or {}).get(q, ()))}
    e = {k: v for k, v in entry(cell).items() if k != 'layers'}
    e['quarters'] = quarters
    (cdir / 'entry.json').write_text(json.dumps(e))
    return cdir


def artifact(tmp_path, cells, split=(), n=0, **kw):
    root = tmp_path / 'artifacts' / f'cells-{n}'
    if (tmp_path / 'artifacts').exists():
        shutil.rmtree(tmp_path / 'artifacts')
    root.mkdir(parents=True)
    (root / 'jobs.txt').write_text(' '.join(list(cells) + list(split)))
    for c in cells:
        fake_cell(root, c, **kw)
    for c in split:
        fake_split_cell(root, c)
    return root


def planned_jobs(tmp_path):
    root = tmp_path / 'artifacts'
    names = sorted(p.name for p in root.iterdir()) if root.exists() else []
    return [(root / n / 'jobs.txt').read_text().strip() for n in names if (root / n / 'jobs.txt').exists()]


def live_version(live):
    if 'manifest.json' not in live.files:
        return None
    return json.loads(live.files['manifest.json']).get('version')


def run(tmp_path, live, name='site', jobs=None, had_manifest=None, areas=None, version='auto'):
    out = tmp_path / name
    had = ('manifest.json' in live.files) if had_manifest is None else had_manifest
    changed = publish.assemble(str(tmp_path / 'artifacts'), str(out), planned_jobs(tmp_path) if jobs is None else jobs, had,
                               areas=areas or AREAS, site_url=URL, get=live.get, log=lambda *_: None,
                               state_dir=str(out) + '-state',
                               plan_manifest_version=live_version(live) if version == 'auto' else version)
    return changed, out


def state_of(out):
    return pathlib.Path(str(out) + '-state')


def deployed(out):
    """Every path the deployment names but hashes.json: the run's folder and the kept files."""
    kept = json.loads((state_of(out) / 'kept.json').read_text())
    here = {str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()}
    return here | {k.lstrip('/') for k in kept}


def v1_site(cells, split=(), region='colorado', regions=None, hashes=True, empty=None, left_out=None):
    """A live site as the version 1 pipeline left it: regions' files under <region>/<cell>/…."""
    files = {}
    entries = {}
    import tempfile
    tmp = pathlib.Path(tempfile.mkdtemp())
    for c in cells:
        cdir = tmp / c
        cdir.mkdir()
        layers = write_layers(cdir, c, empty=(), left_out=(left_out or {}).get(c, ()))
        for l in (empty or {}).get(c, ()):
            # a v1 file with no polygon: the old pipeline wrote it, with zero counts
            doc = cellfile.build(c, l, {0: {30: []}} if l.startswith('t0') else {4: {30: []}})
            data = cellfile.dumps(doc)
            (cdir / f'{l}.json.gz').write_bytes(data)
            layers[l] = {'bytes': len(data), 'tiers': cellfile.stats(doc)}
        entries[c] = dict(site.manifest_entry(dict(entry(c), layers=layers)))
        for l in site.LAYERS:
            p = cdir / f'{l}.json.gz'
            if p.exists():
                files[f'{region}/{c}/{l}.json.gz'] = p.read_bytes()
    shutil.rmtree(tmp)
    cov = site.area_coverage(COLORADO)
    regs = regions or [{'id': region, 'name': region.title(), 'bounds': COLORADO['boxes'][0],
                        'coverage': cov, 'cells': entries, 'quartered': {}}]
    m = {'format': 'slope-extract', 'version': 1, 'attribution': site.ATTRIBUTION,
         'cellFormat': {'format': 'slope-cell', 'version': 1}, 'layers': list(site.LAYERS), 'regions': regs}
    files['manifest.json'] = (json.dumps(m, indent=1) + '\n').encode()
    s = FakeSite(files)
    if hashes:
        s.set_hashes()
    return s
