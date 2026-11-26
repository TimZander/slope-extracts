import json
import os
import pathlib
import shutil

import pytest

from slope_extracts import build_cell, cellfile, grid, overview, publish, site

REGION = [{'id': 'colorado', 'name': 'Colorado', 'bounds': {'south': 37.01, 'west': -109.04, 'north': 40.99, 'east': -102.06}}]
DILLON, OTHER = '158_-425', '158_-424'


def entry(cell, recipe=1):
    return {'cell': cell, 'recipe': recipe, 'built': '2026-11-23', 'sources': {'lidar': 1.0, 'dem10m': 0.0, 'none': 0.0},
            'projects': ['CO_Central_Western_2016'],
            'layers': {l: {'bytes': 9, 'tiers': {}} for l in site.LAYERS}}


# --- regions and plan -------------------------------------------------------------------------

def test_regions_list_checks():
    site.validate_regions(REGION)
    for bad in ([], [dict(REGION[0], id='Colorado')], [REGION[0], REGION[0]],
                [dict(REGION[0], bounds={'south': 41, 'west': -109, 'north': 37, 'east': -102})],
                [dict(REGION[0], only=['0_0'])], [dict(REGION[0], extra=1)]):
        with pytest.raises(ValueError):
            site.validate_regions(bad)


def test_plan_builds_missing_and_stale_cells_only():
    regions = [dict(REGION[0], only=[DILLON, OTHER, '158_-423'])]
    prev = site.build_manifest(REGION, {'colorado': {DILLON: site.manifest_entry(entry(DILLON)),
                                                     OTHER: site.manifest_entry(entry(OTHER, recipe=0))}})
    import datetime
    assert site.plan(regions, prev, 1, 48, 3, today=datetime.date(2026, 11, 24)) == [[('colorado', OTHER), ('colorado', '158_-423')]]


def test_plan_caps_cells_per_run_and_chunks():
    chunks = site.plan(REGION, None, 1, 7, 3)
    assert [len(c) for c in chunks] == [3, 3, 1]
    assert chunks[0][0] == ('colorado', '148_-437')


def test_plan_rebuilds_a_cell_older_than_the_refresh():
    import datetime
    old = dict(site.manifest_entry(entry(DILLON)), built='2025-11-01')
    prev = site.build_manifest(REGION, {'colorado': {DILLON: old}})
    regions = [dict(REGION[0], only=[DILLON])]
    assert site.plan(regions, prev, 1, 48, 3, today=datetime.date(2026, 11, 23)) == [[('colorado', DILLON)]]
    assert site.plan(regions, prev, 1, 48, 3, today=datetime.date(2026, 6, 1)) == []


def test_plan_nothing_to_do():
    prev = site.build_manifest([dict(REGION[0])], {'colorado': {DILLON: site.manifest_entry(entry(DILLON))}})
    import datetime
    assert site.plan([dict(REGION[0], only=[DILLON])], prev, 1, 48, 3, today=datetime.date(2026, 11, 24)) == []


# --- assembling the site against a fake live site ---------------------------------------------

class FakeSite:
    """The live site: path -> bytes; a missing path is a 404."""
    def __init__(self, files=None):
        self.files = dict(files or {})
        self.requests = []

    def get(self, url, limit):
        path = url.split('slope.test/', 1)[1]
        self.requests.append(path)
        if path not in self.files:
            return 404, b''
        if len(self.files[path]) > limit:
            raise RuntimeError(f'{url} is over {limit} bytes')
        return 200, self.files[path]

    def publish(self, out, hashes=True):
        """What a deploy of `out` (and its state folder beside it) would leave live: the files the run
        wrote or read back, the kept files by their hash (their bytes as they were live), `_headers`,
        and `hashes.json` with a stand-in hash (the Pages hash is the Node step's, tested there)."""
        state = pathlib.Path(str(out) + '-state')
        kept = json.loads((state / 'kept.json').read_text()) if (state / 'kept.json').exists() else {}
        old = self.files
        self.files = {}
        for path in kept:
            self.files[path.lstrip('/')] = old[path.lstrip('/')]
        for root, _d, names in os.walk(out):
            for n in names:
                full = os.path.join(root, n)
                self.files[os.path.relpath(full, out).replace(os.sep, '/')] = open(full, 'rb').read()
        if (state / '_headers').exists():
            self.files['_headers'] = (state / '_headers').read_bytes()
        self.files.pop('hashes.json', None)
        if hashes:
            listed = {'/' + k: fake_hash(v, k) for k, v in self.files.items() if k != '_headers'}
            self.files['hashes.json'] = json.dumps({'format': 'slope-hashes', 'version': 1, 'files': listed}).encode()


def fake_hash(data, name):
    """A stand-in for the Pages hash (BLAKE3, which Python's standard library lacks): 32 lowercase hex."""
    import hashlib
    return hashlib.sha256(data + name.rsplit('.', 1)[-1].encode()).hexdigest()[:32]


@pytest.fixture
def live(monkeypatch):
    s = FakeSite()
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    return s


LEFT_OUT = {'bytes': 0, 'tiers': {'0': {'polygons': 0, 'points': 0}}}


def fake_cell(root, cell, tag=0, left_out=()):
    """A built cell as build_cell writes it, with one small polygon; layers in `left_out` have no file."""
    cdir = root / cell
    cdir.mkdir(parents=True)
    layers = {}
    s, w, _n, _e = grid.cell_bounds(cell)
    y, x = grid.to_units(s) + 100, grid.to_units(w) + 100
    ring = [[(y + tag, x), (y + 10, x), (y + 10, x + 10)]]
    for l in site.LAYERS:
        if l in left_out:
            layers[l] = dict(LEFT_OUT)
            continue
        tiers = {0: {30: [ring]}} if l.startswith('t0') else {4: {30: [ring]}}
        data = cellfile.dumps(cellfile.build(cell, l, tiers))
        (cdir / f'{l}.json.gz').write_bytes(data)
        layers[l] = {'bytes': len(data), 'tiers': {}}
    e = dict(entry(cell), layers=layers)
    (cdir / 'entry.json').write_text(json.dumps(e))
    return cdir


def artifact(tmp_path, n, cells, tag=0, left_out=()):
    root = tmp_path / 'artifacts' / f'cells-{n}'
    if (tmp_path / 'artifacts').exists():
        shutil.rmtree(tmp_path / 'artifacts')
    root.mkdir(parents=True)
    (root / 'jobs.txt').write_text(' '.join(f'colorado/{c}' for c in cells))
    for c in cells:
        fake_cell(root, c, tag, left_out)
    return root


def planned_jobs(tmp_path):
    """The plan's job list that matches the artifacts as written (cells-0, cells-1, ...)."""
    root = tmp_path / 'artifacts'
    names = sorted(p.name for p in root.iterdir()) if root.exists() else []
    return [(root / n / 'jobs.txt').read_text().strip() for n in names if (root / n / 'jobs.txt').exists()]


def run(tmp_path, live, name='site', jobs=None, had_manifest=None):
    out = tmp_path / name
    had = ('manifest.json' in live.files) if had_manifest is None else had_manifest
    changed = publish.assemble(str(tmp_path / 'artifacts'), str(out), planned_jobs(tmp_path) if jobs is None else jobs, had,
                               regions=REGION, site_url='https://slope.test', get=live.get, log=lambda *_: None,
                               state_dir=str(out) + '-state')
    return changed, out


def state_of(out):
    return pathlib.Path(str(out) + '-state')


def deployed(out):
    """Every path the deployment would name: the run's folder and the kept files (not `_headers`,
    which goes beside the manifest, nor `hashes.json`, which the Node step writes)."""
    kept = json.loads((state_of(out) / 'kept.json').read_text())
    here = {str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()}
    return here | {k.lstrip('/') for k in kept}


def test_first_run_assembles_the_site(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    changed, out = run(tmp_path, live)
    assert changed is True
    files = sorted(str(p.relative_to(out)) for p in out.rglob('*') if p.is_file())
    assert files == ['404.html', 'LICENSE.txt', f'colorado/{DILLON}/t0-2m.json.gz',
                     f'colorado/{DILLON}/t0-3m.json.gz', f'colorado/{DILLON}/t1-4.json.gz', 'colorado/overview.json.gz',
                     'manifest.json']
    manifest = site.validate_manifest(json.loads((out / 'manifest.json').read_text()))
    assert len(manifest['regions'][0]['coverage']) == 464


def test_second_run_keeps_the_live_cells(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    artifact(tmp_path, 0, [OTHER])
    changed, out2 = run(tmp_path, live, 'site2')
    assert changed is True
    # the kept cell's t0-3m is deployed by its live hash, unread
    kept = json.loads((state_of(out2) / 'kept.json').read_text())
    assert kept[f'/colorado/{DILLON}/t0-3m.json.gz']['hash'] == json.loads(live.files['hashes.json'])['files'][f'/colorado/{DILLON}/t0-3m.json.gz']
    manifest = json.loads((out2 / 'manifest.json').read_text())
    assert set(manifest['regions'][0]['cells']) == {DILLON, OTHER}
    # a rebuilt cell is not read back from the live site
    assert f'colorado/{OTHER}/t0-3m.json.gz' not in live.requests


def test_nothing_built_deploys_nothing(live, tmp_path):
    (tmp_path / 'artifacts').mkdir()
    changed, out = run(tmp_path, live)
    assert changed is False and not out.exists()
    assert live.requests == []


def test_failed_cell_keeps_its_live_files(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    root = artifact(tmp_path, 0, [OTHER])
    (root / 'jobs.txt').write_text(f'colorado/{OTHER} colorado/{DILLON}')  # Dillon failed this run
    (root / 'failed.json').write_text(json.dumps([DILLON]))
    _c, out2 = run(tmp_path, live, 'site2', jobs=[f'colorado/{OTHER} colorado/{DILLON}'])
    assert f'colorado/{DILLON}/t0-3m.json.gz' in deployed(out2)


def test_a_tampered_live_file_fails_the_deploy(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    live.files[f'colorado/{DILLON}/t1-4.json.gz'] = b'x' * 10
    artifact(tmp_path, 0, [OTHER])
    with pytest.raises(RuntimeError, match='bytes, not the'):
        run(tmp_path, live, 'site2')


def test_a_live_file_missing_fails_the_deploy(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    del live.files[f'colorado/{DILLON}/t1-4.json.gz']
    artifact(tmp_path, 0, [OTHER])
    with pytest.raises(RuntimeError, match='lacks'):
        run(tmp_path, live, 'site2')


def test_an_invalid_live_manifest_fails_the_deploy(live, tmp_path):
    live.files['manifest.json'] = b'{"format": "something-else"}'
    artifact(tmp_path, 0, [DILLON])
    with pytest.raises(RuntimeError, match='live manifest is not valid'):
        run(tmp_path, live)


# --- attacks: what a compromised build job could upload ---------------------------------------

def prep(tmp_path, live=None):
    return run(tmp_path, live or FakeSite())


def test_rejects_a_file_the_job_did_not_build(tmp_path):
    root = artifact(tmp_path, 0, [DILLON])
    (root / 'index.html').write_text('<script>')
    with pytest.raises(RuntimeError, match='did not build'):
        prep(tmp_path)


def test_rejects_an_extra_file_in_a_cell(tmp_path):
    root = artifact(tmp_path, 0, [DILLON])
    (root / DILLON / '_headers').write_text('/*\n  X: y\n')
    with pytest.raises(RuntimeError, match='not exactly'):
        prep(tmp_path)


def test_rejects_a_symlink(tmp_path):
    root = artifact(tmp_path, 0, [DILLON])
    os.remove(root / DILLON / 't1-4.json.gz')
    os.symlink('/etc/passwd', root / DILLON / 't1-4.json.gz')
    with pytest.raises(RuntimeError, match='regular file'):
        prep(tmp_path)


def test_rejects_a_jobs_txt_that_differs_from_the_plan(tmp_path):
    root = artifact(tmp_path, 0, [DILLON])
    (root / 'jobs.txt').write_text(f'colorado/{DILLON} colorado/{OTHER}')
    with pytest.raises(RuntimeError, match='not the list the plan gave'):
        run(tmp_path, FakeSite(), jobs=[f'colorado/{DILLON}'])


def test_rejects_an_artifact_the_plan_did_not_make(tmp_path):
    artifact(tmp_path, 0, [DILLON])
    extra = tmp_path / 'artifacts' / 'cells-99'
    extra.mkdir()
    (extra / 'jobs.txt').write_text(f'colorado/{OTHER}')
    fake_cell(extra, OTHER)
    with pytest.raises(RuntimeError, match='not a planned cells artifact'):
        run(tmp_path, FakeSite(), jobs=[f'colorado/{DILLON}'])


def test_rejects_a_plan_with_a_cell_twice(tmp_path):
    artifact(tmp_path, 0, [DILLON])
    with pytest.raises(RuntimeError, match='twice'):
        run(tmp_path, FakeSite(), jobs=[f'colorado/{DILLON}', f'colorado/{DILLON}'])


def test_rejects_a_cell_outside_the_regions(tmp_path):
    artifact(tmp_path, 0, [DILLON])
    with pytest.raises(RuntimeError, match='not a cell of a listed region'):
        run(tmp_path, FakeSite(), jobs=['colorado/0_0'])


def test_rejects_a_path_in_the_plan(tmp_path):
    artifact(tmp_path, 0, [DILLON])
    with pytest.raises(RuntimeError, match='not a cell'):
        run(tmp_path, FakeSite(), jobs=['../colorado/158_-425'])


def test_rejects_a_point_outside_the_cell(tmp_path):
    root = artifact(tmp_path, 0, [DILLON])
    doc = cellfile.build(DILLON, 't0-3m', {0: {30: [[[(0, 0), (1, 0), (1, 1)]]]}})
    rewrite_layer(root, DILLON, 't0-3m', doc)
    with pytest.raises(RuntimeError, match='outside the cell'):
        prep(tmp_path)


def test_rejects_an_extra_key_in_a_cell_file(tmp_path):
    root = artifact(tmp_path, 0, [DILLON])
    doc = dict(cellfile.build(DILLON, 't0-3m', {}), note='<script>alert(1)</script>')
    rewrite_layer(root, DILLON, 't0-3m', doc)
    with pytest.raises(RuntimeError, match='not the slope-cell file'):
        prep(tmp_path)


def test_rejects_a_class_a_tier_lacks(tmp_path):
    root = artifact(tmp_path, 0, [DILLON])
    s, w, _n, _e = grid.cell_bounds(DILLON)
    y, x = grid.to_units(s) + 100, grid.to_units(w) + 100
    doc = cellfile.build(DILLON, 't1-4', {2: {55: [[[(y, x), (y + 10, x), (y + 10, x + 10)]]]}})
    rewrite_layer(root, DILLON, 't1-4', doc)
    with pytest.raises(RuntimeError, match='has class'):
        prep(tmp_path)


def test_rejects_a_date_with_a_trailing_newline(tmp_path):
    root = artifact(tmp_path, 0, [DILLON])
    e = json.loads((root / DILLON / 'entry.json').read_text())
    e['built'] = '2026-01-01\n'
    (root / DILLON / 'entry.json').write_text(json.dumps(e))
    with pytest.raises(RuntimeError, match='entry.json is not valid'):
        prep(tmp_path)


def test_an_unchecked_layer_key_never_reaches_the_manifest(tmp_path):
    root = artifact(tmp_path, 0, [DILLON])
    e = json.loads((root / DILLON / 'entry.json').read_text())
    e['layers']['t0-3m']['href'] = 'javascript:alert(1)'
    (root / DILLON / 'entry.json').write_text(json.dumps(e))
    with pytest.raises(RuntimeError, match='exactly bytes and tiers'):
        prep(tmp_path)


def test_a_404_manifest_after_the_plan_saw_one_fails(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    with pytest.raises(RuntimeError, match='refusing to publish'):
        run(tmp_path, live, had_manifest=True)


def test_error_output_cannot_start_a_workflow_command():
    assert publish.safe('bad\n::add-mask::x') == 'bad?::add-mask::x'


def test_main_reads_the_plan_from_the_environment(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('PLAN_JOBS', 'not json')
    monkeypatch.setenv('PLAN_HAD_MANIFEST', 'true')
    assert publish.main(['assemble', '--artifacts', str(tmp_path), '--out', str(tmp_path / 'o')]) == 1


def rewrite_layer(root, cell, layer, doc):
    data = cellfile.dumps(doc)
    (root / cell / f'{layer}.json.gz').write_bytes(data)
    e = json.loads((root / cell / 'entry.json').read_text())
    e['layers'][layer]['bytes'] = len(data)
    (root / cell / 'entry.json').write_text(json.dumps(e))


def test_rejects_a_mislabelled_cell_file(tmp_path):
    root = artifact(tmp_path, 0, [DILLON])
    rewrite_layer(root, DILLON, 't0-3m', cellfile.build(OTHER, 't0-3m', {}))
    with pytest.raises(RuntimeError, match='not the slope-cell file'):
        prep(tmp_path)


def test_rejects_a_malformed_ring(tmp_path):
    root = artifact(tmp_path, 0, [DILLON])
    doc = cellfile.build(DILLON, 't0-3m', {})
    doc['tiers'] = {'0': {'30': [[[1, 2, 3, 'x', 5, 6]]]}}
    rewrite_layer(root, DILLON, 't0-3m', doc)
    with pytest.raises(RuntimeError, match='ring is malformed'):
        prep(tmp_path)


def test_rejects_an_oversized_file(tmp_path, monkeypatch):
    root = artifact(tmp_path, 0, [DILLON])
    limit = max(os.path.getsize(p) for p in (root / DILLON).iterdir())
    (root / DILLON / 't1-4.json.gz').write_bytes(b'x' * (limit + 1))
    monkeypatch.setattr(publish, 'MAX_FILE_BYTES', limit)
    with pytest.raises(RuntimeError, match='t1-4.json.gz is over'):
        prep(tmp_path)


def test_rejects_an_oversized_entry(tmp_path, monkeypatch):
    artifact(tmp_path, 0, [DILLON])
    monkeypatch.setattr(publish, 'MAX_FILE_BYTES', 10)
    with pytest.raises(RuntimeError, match='entry.json is over'):
        prep(tmp_path)


@pytest.mark.parametrize('kind', ['symlink', 'dir', 'fifo', 'absent'])
def test_rejects_an_entry_that_is_not_a_regular_file(tmp_path, kind):
    root = artifact(tmp_path, 0, [DILLON])
    ep = root / DILLON / 'entry.json'
    os.remove(ep)
    if kind == 'symlink':
        os.symlink('/etc/passwd', ep)
    elif kind == 'dir':
        ep.mkdir()
    elif kind == 'fifo':
        os.mkfifo(ep)
    with pytest.raises(RuntimeError, match='entry.json is not a regular file'):
        prep(tmp_path)


# --- site files -------------------------------------------------------------------------------

def test_site_file_count_guard(tmp_path, monkeypatch):
    artifact(tmp_path, 0, [DILLON])
    monkeypatch.setattr(site, 'MAX_SITE_FILES', 7)  # 4 fixed files + 3 layers + the overview = 8
    with pytest.raises(RuntimeError, match='file limit'):
        prep(tmp_path)


def test_headers_never_set_cache_control_twice_on_a_path():
    rules = {}
    current = None
    for line in site.HEADERS.splitlines():
        if line and not line.startswith(' '):
            current = line
            rules[current] = []
        elif line.strip():
            rules[current].append(line.split(':', 1)[0].strip())
    assert rules['/*'] == ['Access-Control-Allow-Origin', 'X-Content-Type-Options']
    assert all(v == ['Cache-Control'] for k, v in rules.items() if k != '/*')
    assert set(rules) == {'/*', '/:region/:cell/*', '/:region/overview.json.gz', '/LICENSE.txt', '/manifest.json', '/hashes.json'}


def test_license_lists_the_projects_used():
    m = site.build_manifest(REGION, {'colorado': {DILLON: dict(site.manifest_entry(entry(DILLON)),
                                                               projects=['CO_A_2016', 'CO_B_2020', 'CO_C_2023'])}})
    text = site.license_text(m)
    assert 'public domain' in text and site.REPOSITORY_URL in text
    assert all(f'- {p}' in text for p in ('CO_A_2016', 'CO_B_2020', 'CO_C_2023'))


# --- the first-deploy switch ------------------------------------------------------------------
# Spec: slope-extract, "A first deploy can replace a placeholder site" and "Files read back from the
# live site are checked".

class PlaceholderSite(FakeSite):
    """A Pages project with no 404.html: every missing path answers 200 with the placeholder's body."""
    def __init__(self, files=None, body=b''):
        super().__init__(files)
        self.body = body

    def get(self, url, limit):
        path = url.split('slope.test/', 1)[1]
        self.requests.append(path)
        return 200, self.files.get(path, self.body)


def fetch(live, first_deploy):
    return publish.fetch_manifest('https://slope.test', live.get, first_deploy=first_deploy)


@pytest.mark.parametrize('body', [b'', b'<!doctype html><title>placeholder</title>'])
def test_first_deploy_reads_a_placeholder_as_no_manifest(body):
    assert fetch(PlaceholderSite(body=body), True) is None


def test_first_deploy_publishes_a_site_with_its_own_404(tmp_path, monkeypatch):
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    live = PlaceholderSite(body=b'<html>placeholder</html>')
    artifact(tmp_path, 0, [DILLON])
    changed = publish.assemble(str(tmp_path / 'artifacts'), str(tmp_path / 'site'), planned_jobs(tmp_path), False,
                               regions=REGION, site_url='https://slope.test', get=live.get, log=lambda *_: None,
                               first_deploy=True)
    assert changed is True
    assert (tmp_path / 'site' / '404.html').read_text() == site.NOT_FOUND_HTML
    manifest = site.validate_manifest(json.loads((tmp_path / 'site' / 'manifest.json').read_text()))
    assert set(manifest['regions'][0]['cells']) == {DILLON}


@pytest.mark.parametrize('value', [None, 'false', 'True', '1', ''])
def test_the_switch_is_only_exactly_true(monkeypatch, value):
    if value is None:
        monkeypatch.delenv('FIRST_DEPLOY', raising=False)
    else:
        monkeypatch.setenv('FIRST_DEPLOY', value)
    assert publish.first_deploy_on() is False
    with pytest.raises(RuntimeError, match='the live manifest is not valid'):
        fetch(PlaceholderSite(body=b'<html>placeholder</html>'), publish.first_deploy_on())


def test_the_switch_on_reads_it_when_set_to_true(monkeypatch):
    monkeypatch.setenv('FIRST_DEPLOY', 'true')
    assert publish.first_deploy_on() is True


def test_the_switch_left_on_over_a_live_site_keeps_its_cells(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    assert fetch(live, True) == site.validate_manifest(json.loads(live.files['manifest.json']))
    artifact(tmp_path, 0, [OTHER])
    changed = publish.assemble(str(tmp_path / 'artifacts'), str(tmp_path / 'site2'), planned_jobs(tmp_path), True,
                               regions=REGION, site_url='https://slope.test', get=live.get, log=lambda *_: None,
                               first_deploy=True)
    assert changed is True
    manifest = json.loads((tmp_path / 'site2' / 'manifest.json').read_text())
    assert set(manifest['regions'][0]['cells']) == {DILLON, OTHER}


def test_a_pipeline_site_whose_manifest_answers_html_is_not_forgiven():
    live = FakeSite({'manifest.json': b'<html>an error page sent as 200</html>', '404.html': b'x'})
    with pytest.raises(RuntimeError, match='the live manifest is not valid'):
        fetch(live, True)


@pytest.mark.parametrize('body', [b'{"regions": "no"}', b'[]', b'null'])
def test_a_json_manifest_that_is_not_valid_fails_with_the_switch_on(body):
    with pytest.raises(RuntimeError, match='the live manifest is not valid'):
        fetch(PlaceholderSite({'manifest.json': body}, body=b'<html>placeholder</html>'), True)


def test_a_forgiven_manifest_after_the_plan_read_one_fails_the_deploy(tmp_path, monkeypatch):
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    live = PlaceholderSite(body=b'<html>placeholder</html>')
    artifact(tmp_path, 0, [DILLON])
    with pytest.raises(RuntimeError, match='refusing to publish'):
        publish.assemble(str(tmp_path / 'artifacts'), str(tmp_path / 'site'), planned_jobs(tmp_path), True,
                         regions=REGION, site_url='https://slope.test', get=live.get, log=lambda *_: None,
                         first_deploy=True)
    assert not (tmp_path / 'site').exists()


def test_the_plan_and_the_assembler_read_the_switch(tmp_path, monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(publish, 'fetch_manifest', lambda *a, **k: seen.append(k.get('first_deploy')) or None)
    monkeypatch.setenv('FIRST_DEPLOY', 'true')
    assert site.main_plan([]) == 0
    assert 'had_manifest=false' in capsys.readouterr().out
    monkeypatch.setattr(publish, 'assemble', lambda *a, **k: seen.append(k.get('first_deploy')))
    monkeypatch.setenv('PLAN_JOBS', '[]')
    monkeypatch.setenv('PLAN_HAD_MANIFEST', 'false')
    assert publish.main(['assemble', '--artifacts', str(tmp_path), '--out', str(tmp_path / 'o')]) == 0
    assert seen == [True, True]


# --- region overview (slope-overview) ------------------------------------------------------------

def overview_doc(out, region='colorado'):
    return cellfile_loads_overview((out / region / 'overview.json.gz').read_bytes())


def cellfile_loads_overview(data):
    import gzip
    return json.loads(gzip.decompress(data))


def covered_order(cells):
    cov = site.coverage(REGION[0])
    return sorted(cells, key=cov.index)


def tier4_polygons(cell, count, start=0):
    """`count` distinct one-ring tier-4 polygons inside `cell`, numbered from `start`."""
    s, w, _n, _e = grid.cell_bounds(cell)
    y, x = grid.to_units(s) + 100, grid.to_units(w) + 100
    return [[[(y + 20 * i, x), (y + 20 * i + 10, x), (y + 20 * i + 10, x + 10)]] for i in range(start, start + count)]


# Requirement: Each region has an overview of its built cells' tier 4
def test_overview_holds_every_built_cells_tier_4_in_coverage_order(live, tmp_path):
    first_count = 3
    second_count = 5
    first, second = covered_order([OTHER, DILLON])
    root = artifact(tmp_path, 0, [second, first])
    # Each cell's polygons in a deliberately unsorted order, to catch any re-sorting.
    rewrite_layer(root, first, 't1-4', cellfile.build(first, 't1-4', {4: {30: tier4_polygons(first, first_count)[::-1]}}))
    rewrite_layer(root, second, 't1-4', cellfile.build(second, 't1-4', {4: {30: tier4_polygons(second, second_count)[::-1]}}))
    _c, out = run(tmp_path, live)
    doc = overview_doc(out)
    assert set(doc) == {'format', 'version', 'region', 'tiers'}
    assert (doc['format'], doc['version'], doc['region']) == ('slope-overview', 1, 'colorado')
    assert set(doc['tiers']) == {'4'} and set(doc['tiers']['4']) == {'30'}
    got = doc['tiers']['4']['30']
    assert len(got) == first_count + second_count
    assert got[:first_count] == cellfile.loads((out / 'colorado' / first / 't1-4.json.gz').read_bytes())['tiers']['4']['30']
    assert got[first_count:] == cellfile.loads((out / 'colorado' / second / 't1-4.json.gz').read_bytes())['tiers']['4']['30']


# Requirement: Each region has an overview of its built cells' tier 4
def test_the_same_cells_give_the_same_overview_bytes(live, tmp_path, monkeypatch):
    import gzip
    import types
    first_clock = 1_000_000_000
    second_clock = 1_900_000_000
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    doc = overview_doc(out)
    # gzip stamps the time it compresses at: two writes far apart must still match.
    monkeypatch.setattr(gzip, 'time', types.SimpleNamespace(time=lambda: first_clock))
    first = overview.dumps(doc)
    monkeypatch.setattr(gzip, 'time', types.SimpleNamespace(time=lambda: second_clock))
    second = overview.dumps(doc)
    assert first == second == (out / 'colorado/overview.json.gz').read_bytes()


# Requirement: Each region has an overview of its built cells' tier 4
# Requirement: The manifest gives each region's overview
def test_a_region_with_no_built_cell_has_no_overview(live, tmp_path):
    regions = REGION + [{'id': 'utah', 'name': 'Utah', 'bounds': {'south': 38.0, 'west': -112.0, 'north': 38.5, 'east': -111.5}}]
    artifact(tmp_path, 0, [DILLON])
    out = tmp_path / 'site'
    publish.assemble(str(tmp_path / 'artifacts'), str(out), planned_jobs(tmp_path), False, regions=regions,
                     site_url='https://slope.test', get=live.get, log=lambda *_: None)
    manifest = json.loads((out / 'manifest.json').read_text())
    utah = next(r for r in manifest['regions'] if r['id'] == 'utah')
    assert 'overview' not in utah
    assert not (out / 'utah').exists()
    assert 'utah/overview.json.gz' not in site.site_files(manifest)
    assert overview.build('utah', []) is None


# Requirement: The deploy job writes the overview from the cells it publishes
def test_a_run_that_adds_a_cell_adds_it_to_the_overview(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    artifact(tmp_path, 0, [OTHER], tag=1)
    _c, out2 = run(tmp_path, live, 'site2')
    assert len(overview_doc(out2)['tiers']['4']['30']) == 2
    assert 'colorado/overview.json.gz' not in live.requests


# Requirement: The deploy job writes the overview from the cells it publishes
def test_an_overview_too_large_fails_the_deploy(live, tmp_path, monkeypatch):
    artifact(tmp_path, 0, [DILLON])
    monkeypatch.setattr(overview, 'MAX_FILE_BYTES', 10)
    with pytest.raises(RuntimeError, match='overview'):
        run(tmp_path, live)


# Requirement: The deploy job writes the overview from the cells it publishes
def test_an_overview_whose_json_is_too_large_fails_the_deploy(live, tmp_path, monkeypatch):
    artifact(tmp_path, 0, [DILLON])
    monkeypatch.setattr(overview, 'MAX_JSON_BYTES', 10)
    with pytest.raises(RuntimeError, match='overview'):
        run(tmp_path, live)


# Requirement: The deploy job writes the overview from the cells it publishes
def test_a_live_manifests_overview_entry_is_accepted_and_unused(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    m = json.loads(live.files['manifest.json'])
    m['regions'][0]['overview'] = 'not an entry'
    live.files['manifest.json'] = json.dumps(m).encode()
    site.validate_manifest(m)
    jobs = site.plan(REGION, m, current_recipe=1, max_cells=2, per_job=3)
    assert jobs and all(c != DILLON for job in jobs for _r, c in job)
    artifact(tmp_path, 0, [OTHER])
    _c, out2 = run(tmp_path, live, 'site2')
    new = json.loads((out2 / 'manifest.json').read_text())['regions'][0]['overview']
    assert new == {'bytes': (out2 / 'colorado/overview.json.gz').stat().st_size, 'polygons': 2, 'points': 6}


# Requirement: The manifest gives each region's overview
def test_the_manifest_gives_the_overviews_size_and_counts(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    region = json.loads((out / 'manifest.json').read_text())['regions'][0]
    assert region['overview'] == {'bytes': (out / 'colorado/overview.json.gz').stat().st_size,
                                  'polygons': 1, 'points': 3}


def header_rules():
    rules, current = {}, None
    for line in site.HEADERS.splitlines():
        if line and not line.startswith(' '):
            current = line
            rules[current] = []
        elif line.strip():
            rules[current].append(line.strip())
    return rules


def rule_matches(rule, path):
    """Cloudflare Pages _headers matching: `:name` is one segment, a trailing `*` any rest."""
    import re
    pattern = re.escape(rule).replace(r'\*', '.*')
    pattern = re.sub(r':[a-z]+', '[^/]+', pattern)
    return re.fullmatch(pattern, path) is not None


# Requirement: The site sets its CORS and cache headers
def test_each_path_matches_one_cache_rule():
    rules = {k: v for k, v in header_rules().items() if any(x.startswith('Cache-Control') for x in v)}
    for path, age in (('/colorado/overview.json.gz', 'max-age=3600'), (f'/colorado/{DILLON}/t1-4.json.gz', 'max-age=86400'),
                      ('/LICENSE.txt', 'max-age=3600'), ('/manifest.json', 'max-age=300')):
        hits = [k for k in rules if rule_matches(k, path)]
        assert len(hits) == 1, (path, hits)
        assert rules[hits[0]] == [f'Cache-Control: public, {age}']


# Requirement: The deploy job writes the overview from the cells it publishes (attack test: a build job
# can't supply its own overview)
def test_rejects_an_overview_a_build_job_uploads(tmp_path):
    root = artifact(tmp_path, 0, [DILLON])
    (root / 'overview.json.gz').write_bytes(b'not the deploy job\'s')
    with pytest.raises(RuntimeError, match='did not build'):
        prep(tmp_path)


# --- a left-out 2 m layer (requirement: The manifest marks a left-out layer) ------------------

def test_a_cell_without_its_2m_layer_is_published_with_the_marker(live, tmp_path):
    artifact(tmp_path, 0, [DILLON], left_out=('t0-2m',))
    changed, out = run(tmp_path, live)
    assert changed is True
    cell_files = sorted(str(p.relative_to(out)) for p in (out / 'colorado' / DILLON).rglob('*'))
    assert cell_files == [f'colorado/{DILLON}/t0-3m.json.gz', f'colorado/{DILLON}/t1-4.json.gz']
    manifest = site.validate_manifest(json.loads((out / 'manifest.json').read_text()))
    e = manifest['regions'][0]['cells'][DILLON]
    assert e['layers']['t0-2m'] == LEFT_OUT
    assert e['layers']['t0-3m']['bytes'] > 0 and e['layers']['t1-4']['bytes'] > 0
    assert f'colorado/{DILLON}/t0-2m.json.gz' not in site.site_files(manifest)


def test_rejects_a_left_out_layers_file_that_is_there_anyway(tmp_path):
    root = artifact(tmp_path, 0, [DILLON], left_out=('t0-2m',))
    (root / DILLON / 't0-2m.json.gz').write_bytes(cellfile.dumps(cellfile.build(DILLON, 't0-2m', {})))
    with pytest.raises(RuntimeError, match='not exactly'):
        prep(tmp_path)


def test_rejects_a_layer_missing_without_the_marker(tmp_path):
    root = artifact(tmp_path, 0, [DILLON])
    os.remove(root / DILLON / 't0-2m.json.gz')
    with pytest.raises(RuntimeError, match='not exactly'):
        prep(tmp_path)


@pytest.mark.parametrize('layer', ['t1-4', 't0-3m'])
def test_rejects_the_marker_on_another_layer(tmp_path, layer):
    root = artifact(tmp_path, 0, [DILLON], left_out=(layer,))
    with pytest.raises(RuntimeError, match='entry.json is not valid'):
        prep(tmp_path)


@pytest.mark.parametrize('tiers', [{'0': {'polygons': 12, 'points': 0}}, {'0': {'polygons': 0, 'points': 40}}, {},
                                   {'0': {'polygons': 0, 'points': 0}, '1': {'polygons': 0, 'points': 0}}])
def test_rejects_a_marker_with_other_tiers(tmp_path, tiers):
    root = artifact(tmp_path, 0, [DILLON], left_out=('t0-2m',))
    e = json.loads((root / DILLON / 'entry.json').read_text())
    e['layers']['t0-2m'] = {'bytes': 0, 'tiers': tiers}
    (root / DILLON / 'entry.json').write_text(json.dumps(e))
    with pytest.raises(RuntimeError, match='entry.json is not valid'):
        prep(tmp_path)


def test_the_marker_on_another_layer_in_the_live_manifest_fails_the_plan():
    layers = {'t0-3m': dict(LEFT_OUT), 't0-2m': {'bytes': 9, 'tiers': {'0': {'polygons': 1, 'points': 3}}},
              't1-4': {'bytes': 9, 'tiers': {'4': {'polygons': 1, 'points': 3}}}}
    e = site.manifest_entry(dict(entry(DILLON), layers=layers))
    body = json.dumps(site.build_manifest(REGION, {'colorado': {DILLON: e}})).encode()
    live = FakeSite({'manifest.json': body})
    with pytest.raises(RuntimeError, match='the live manifest is not valid'):
        publish.fetch_manifest('https://slope.test', live.get)


def test_a_live_cell_without_its_2m_layer_is_read_back_without_it(live, tmp_path):
    # "hashes.json lists none of its files": every kept file is read back
    artifact(tmp_path, 0, [DILLON], left_out=('t0-2m',))
    _c, out = run(tmp_path, live)
    live.publish(out, hashes=False)
    before = json.loads(live.files['manifest.json'])['regions'][0]['cells'][DILLON]
    live.requests.clear()
    artifact(tmp_path, 0, [OTHER])
    changed, out2 = run(tmp_path, live, 'site2')
    assert changed is True
    assert f'colorado/{DILLON}/t0-2m.json.gz' not in live.requests
    assert f'colorado/{DILLON}/t0-3m.json.gz' in live.requests and f'colorado/{DILLON}/t1-4.json.gz' in live.requests
    assert not (out2 / f'colorado/{DILLON}/t0-2m.json.gz').exists()
    after = json.loads((out2 / 'manifest.json').read_text())['regions'][0]['cells']
    assert after[DILLON] == before and set(after) == {DILLON, OTHER}


# --- split cells (change split-dense-cells) ---------------------------------------------------

QUARTERS = ['316_-850', '316_-849', '317_-850', '317_-849']  # of DILLON, qrow then qcol


def q_ring(cell, quarter, tag=0):
    s, w, _n, _e = grid.quarter_bounds(cell, quarter)
    y, x = grid.to_units(s) + 100, grid.to_units(w) + 100
    return [[(y + tag, x), (y + 10, x), (y + 10, x + 10)]]


def fake_split_cell(root, cell, tag=0, left_out=None, t4=None, projects=None):
    """A split cell as build_cell writes it; left_out: {quarter: layers}; t4: {quarter: polygon count}."""
    cdir = root / cell
    cdir.mkdir(parents=True)
    quarters = {}
    for q in grid.quarters(cell):
        (cdir / q).mkdir()
        layers = {}
        for l in site.LAYERS:
            if l in (left_out or {}).get(q, ()):
                layers[l] = dict(LEFT_OUT)
                continue
            if l.startswith('t0'):
                tiers = {0: {30: [q_ring(cell, q, tag)]}}
            else:
                n = 1 if t4 is None else t4[q]
                tiers = {4: {30: [q_ring(cell, q, 20 * i + tag) for i in range(n)]}}
            data = cellfile.dumps(cellfile.build(cell, l, tiers, quarter=q))
            (cdir / q / f'{l}.json.gz').write_bytes(data)
            layers[l] = {'bytes': len(data), 'tiers': {}}
        quarters[q] = {'layers': layers}
    e = {k: v for k, v in entry(cell).items() if k != 'layers'}
    e['quarters'] = quarters
    if projects:
        e['projects'] = projects
    (cdir / 'entry.json').write_text(json.dumps(e))
    return cdir


def split_artifact(tmp_path, n, whole=(), split=(), **kw):
    root = tmp_path / 'artifacts' / f'cells-{n}'
    if (tmp_path / 'artifacts').exists():
        shutil.rmtree(tmp_path / 'artifacts')
    root.mkdir(parents=True)
    (root / 'jobs.txt').write_text(' '.join(f'colorado/{c}' for c in covered_order(list(whole) + list(split))))
    for c in whole:
        fake_cell(root, c)
    for c in split:
        fake_split_cell(root, c, **kw)
    return root


def quarter_files(cell, layers=site.LAYERS, skip=()):
    return [f'colorado/{cell}/{q}/{l}.json.gz' for q in grid.quarters(cell) for l in layers if (q, l) not in skip]


# Requirement: The manifest lists quartered cells apart from whole ones ("A region with one split cell")
# Requirement: A quarter file names its cell and its quarter
def test_a_split_cell_is_published_under_quartered(live, tmp_path):
    split_artifact(tmp_path, 0, whole=[OTHER], split=[DILLON])
    changed, out = run(tmp_path, live)
    assert changed is True
    manifest = site.validate_manifest(json.loads((out / 'manifest.json').read_text()))
    r = manifest['regions'][0]
    assert list(r['cells']) == [OTHER]
    assert list(r['quartered']) == [DILLON]
    e = r['quartered'][DILLON]
    assert set(e) == {'recipe', 'built', 'sources', 'projects', 'quarters'}
    assert list(e['quarters']) == QUARTERS
    for q in QUARTERS:
        assert set(e['quarters'][q]) == {'layers'}
        for l in site.LAYERS:
            p = out / f'colorado/{DILLON}/{q}/{l}.json.gz'
            assert e['quarters'][q]['layers'][l]['bytes'] == p.stat().st_size
            doc = json.loads(__import__('gzip').decompress(p.read_bytes()))
            assert (doc['cell'], doc['quarter'], doc['layer']) == (DILLON, q, l)
    assert not any((out / f'colorado/{DILLON}/{l}.json.gz').exists() for l in site.LAYERS)
    files = sorted(str(p.relative_to(out)) for p in out.rglob('*') if p.is_file())
    assert sorted(set(site.site_files(manifest)) - {'hashes.json'}) == files


# Requirement: The manifest lists quartered cells apart from whole ones ("No split cell")
# Requirement: The manifest lists each region's coverage and built cells ("A pilot run")
def test_a_region_with_no_split_cell_has_an_empty_quartered(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    assert json.loads((out / 'manifest.json').read_text())['regions'][0]['quartered'] == {}


def split_manifest(extra_region=None):
    e = site.manifest_entry({**{k: v for k, v in entry(DILLON).items() if k != 'layers'},
                             'quarters': {q: {'layers': {l: {'bytes': 9, 'tiers': {}} for l in site.LAYERS}} for q in QUARTERS}})
    m = site.build_manifest(REGION, {'colorado': {DILLON: e}})
    if extra_region:
        m['regions'][0].update(extra_region)
    return m


def fetch_body(m):
    return publish.fetch_manifest('https://slope.test', FakeSite({'manifest.json': json.dumps(m).encode()}).get)


# Requirement: The manifest lists quartered cells apart from whole ones ("A live manifest from before this change")
def test_a_live_manifest_without_quartered_is_read_as_none_split():
    m = site.build_manifest(REGION, {'colorado': {DILLON: site.manifest_entry(entry(DILLON))}})
    del m['regions'][0]['quartered']
    assert fetch_body(m) is not None
    import datetime
    assert site.plan([dict(REGION[0], only=[DILLON])], m, 1, 48, 3, today=datetime.date(2026, 11, 24)) == []


# Requirement: The manifest lists quartered cells apart from whole ones (live-manifest attacks)
@pytest.mark.parametrize('bad', ['both', 'three', 'layers', 't1-4 marker', 'quarter key', 'not a cell'])
def test_an_invalid_live_quartered_entry_fails_the_plan(bad):
    m = split_manifest()
    r = m['regions'][0]
    e = r['quartered'][DILLON]
    if bad == 'both':
        r['cells'][DILLON] = site.manifest_entry(entry(DILLON))
    elif bad == 'three':
        del e['quarters'][QUARTERS[3]]
    elif bad == 'layers':
        e['layers'] = e['quarters'][QUARTERS[0]]['layers']
    elif bad == 't1-4 marker':
        e['quarters'][QUARTERS[0]]['layers']['t1-4'] = dict(LEFT_OUT)
    elif bad == 'quarter key':
        e['quarters'][QUARTERS[0]]['href'] = 'x'
    elif bad == 'not a cell':
        r['quartered'] = {'../x': e}
    with pytest.raises(RuntimeError, match='the live manifest is not valid'):
        fetch_body(m)


def test_a_cells_entry_with_quarters_fails_the_plan():
    m = site.build_manifest(REGION, {'colorado': {OTHER: site.manifest_entry(entry(OTHER))}})
    m['regions'][0]['cells'][OTHER]['quarters'] = split_manifest()['regions'][0]['quartered'][DILLON]['quarters']
    with pytest.raises(RuntimeError, match='the live manifest is not valid'):
        fetch_body(m)


# Requirement: A run builds missing and stale cells, at most 48
def test_plan_rebuilds_a_whole_cell_with_a_layer_left_out_but_not_a_split_one():
    import datetime
    today = datetime.date(2026, 11, 23)
    whole = site.manifest_entry(dict(entry(OTHER), layers={**entry(OTHER)['layers'], 't0-2m': dict(LEFT_OUT)}))
    split = split_manifest()['regions'][0]['quartered'][DILLON]
    split['quarters'][QUARTERS[0]]['layers']['t0-2m'] = dict(LEFT_OUT)
    m = site.build_manifest(REGION, {'colorado': {OTHER: whole, DILLON: split}})
    regions = [dict(REGION[0], only=[DILLON, OTHER])]
    assert site.plan(regions, m, 1, 48, 3, today=today) == [[('colorado', OTHER)]]
    # a split cell counts as built: it isn't planned again while it is current
    assert site.plan([dict(REGION[0], only=[DILLON])], split_manifest(), 1, 48, 3, today=today) == []
    # and is planned again when stale
    assert site.plan([dict(REGION[0], only=[DILLON])], split_manifest(), 2, 48, 3, today=today) == [[('colorado', DILLON)]]


# Requirement: Files read back from the live site are checked ("A live split cell")
def test_a_live_split_cell_is_read_back_by_its_quarters(live, tmp_path):
    # "hashes.json lists none of its files": every kept file is read back
    split_artifact(tmp_path, 0, split=[DILLON], left_out={QUARTERS[1]: ('t0-2m',)})
    _c, out = run(tmp_path, live)
    live.publish(out, hashes=False)
    before = json.loads(live.files['manifest.json'])['regions'][0]['quartered'][DILLON]
    live.requests.clear()
    artifact(tmp_path, 0, [OTHER])
    changed, out2 = run(tmp_path, live, 'site2')
    assert changed is True
    want = quarter_files(DILLON, skip={(QUARTERS[1], 't0-2m')})
    assert set(want) <= set(live.requests)
    assert f'colorado/{DILLON}/{QUARTERS[1]}/t0-2m.json.gz' not in live.requests
    r = json.loads((out2 / 'manifest.json').read_text())['regions'][0]
    assert r['quartered'][DILLON] == before and list(r['cells']) == [OTHER]


def test_a_tampered_live_quarter_fails_the_deploy(live, tmp_path):
    split_artifact(tmp_path, 0, split=[DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    live.files[f'colorado/{DILLON}/{QUARTERS[2]}/t1-4.json.gz'] = b'x' * 10
    artifact(tmp_path, 0, [OTHER])
    with pytest.raises(RuntimeError, match='bytes, not the'):
        run(tmp_path, live, 'site2')


def test_a_live_quarter_from_another_quarter_fails_the_deploy(live, tmp_path):
    split_artifact(tmp_path, 0, split=[DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    # t1-4 files are always read back (the overview is built from them), so the swap is read and checked
    a, b = (f'colorado/{DILLON}/{q}/t1-4.json.gz' for q in QUARTERS[:2])
    live.files[a] = live.files[b]  # and its size in the manifest: a swap only the quarter check sees
    m = json.loads(live.files['manifest.json'])
    m['regions'][0]['quartered'][DILLON]['quarters'][QUARTERS[0]]['layers']['t1-4']['bytes'] = len(live.files[b])
    live.files['manifest.json'] = json.dumps(m).encode()
    artifact(tmp_path, 0, [OTHER])
    with pytest.raises(RuntimeError, match='not the slope-cell file'):
        run(tmp_path, live, 'site2')


# Requirement: Files read back from the live site are checked ("A whole cell becomes split",
# "A split cell fits whole again")
def test_a_whole_cell_becomes_split_and_back(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    split_artifact(tmp_path, 0, split=[DILLON])
    changed, out2 = run(tmp_path, live, 'site2')
    assert changed is True
    r = json.loads((out2 / 'manifest.json').read_text())['regions'][0]
    assert r['cells'] == {} and list(r['quartered']) == [DILLON]
    assert all((out2 / p).exists() for p in quarter_files(DILLON))
    assert not any((out2 / f'colorado/{DILLON}/{l}.json.gz').exists() for l in site.LAYERS)
    live.publish(out2)
    artifact(tmp_path, 0, [DILLON])
    _c, out3 = run(tmp_path, live, 'site3')
    r = json.loads((out3 / 'manifest.json').read_text())['regions'][0]
    assert list(r['cells']) == [DILLON] and r['quartered'] == {}
    assert not (out3 / f'colorado/{DILLON}/{QUARTERS[0]}').exists()


def test_fewer_cells_counts_split_cells_too(live, tmp_path):
    split_artifact(tmp_path, 0, split=[DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    m = json.loads(live.files['manifest.json'])
    # a live manifest listing a split cell outside the regions list: the new manifest would drop it
    stray = dict(m['regions'][0]['quartered'][DILLON])
    stray['quarters'] = dict(zip(grid.quarters('0_0'), stray['quarters'].values()))
    m['regions'][0]['quartered']['0_0'] = stray
    live.files['manifest.json'] = json.dumps(m).encode()
    artifact(tmp_path, 0, [DILLON])  # 1 cell in the new manifest, 2 in the live one
    with pytest.raises(RuntimeError, match='fewer than the live'):
        run(tmp_path, live, 'site2')


# Requirement: The deploy job accepts only well-formed split cells (attack tests)
def test_rejects_a_whole_cell_file_beside_the_quarters(tmp_path):
    root = split_artifact(tmp_path, 0, split=[DILLON])
    (root / DILLON / 't1-4.json.gz').write_bytes(cellfile.dumps(cellfile.build(DILLON, 't1-4', {})))
    with pytest.raises(RuntimeError, match='not exactly'):
        prep(tmp_path)


def rewrite_quarter(root, cell, q, layer, doc):
    data = cellfile.dumps(doc)
    (root / cell / q / f'{layer}.json.gz').write_bytes(data)
    e = json.loads((root / cell / 'entry.json').read_text())
    e['quarters'][q]['layers'][layer]['bytes'] = len(data)
    (root / cell / 'entry.json').write_text(json.dumps(e))


def test_rejects_a_quarters_point_in_another_quarter(tmp_path):
    root = split_artifact(tmp_path, 0, split=[DILLON])
    s, w, _n, _e = grid.quarter_bounds(DILLON, QUARTERS[1])  # the next quarter east
    y, x = grid.to_units(s) + 100, grid.to_units(w) + 100
    doc = cellfile.build(DILLON, 't0-3m', {0: {30: [[[(y, x), (y + 10, x), (y + 10, x + 10)]]]}}, quarter=QUARTERS[0])
    rewrite_quarter(root, DILLON, QUARTERS[0], 't0-3m', doc)
    with pytest.raises(RuntimeError, match='outside the'):
        prep(tmp_path)


def test_rejects_a_quarter_file_naming_another_quarter(tmp_path):
    root = split_artifact(tmp_path, 0, split=[DILLON])
    doc = cellfile.build(DILLON, 't0-3m', {}, quarter=QUARTERS[2])
    rewrite_quarter(root, DILLON, QUARTERS[0], 't0-3m', doc)
    with pytest.raises(RuntimeError, match='not the slope-cell file'):
        prep(tmp_path)


def test_rejects_a_quarter_file_without_its_quarter_key(tmp_path):
    root = split_artifact(tmp_path, 0, split=[DILLON])
    rewrite_quarter(root, DILLON, QUARTERS[0], 't0-3m', cellfile.build(DILLON, 't0-3m', {}))
    with pytest.raises(RuntimeError, match='not the slope-cell file'):
        prep(tmp_path)


def test_rejects_a_whole_cell_file_with_a_quarter_key(tmp_path):
    root = artifact(tmp_path, 0, [DILLON])
    rewrite_layer(root, DILLON, 't0-3m', cellfile.build(DILLON, 't0-3m', {}, quarter=QUARTERS[0]))
    with pytest.raises(RuntimeError, match='not the slope-cell file'):
        prep(tmp_path)


def test_rejects_a_quarter_folder_that_is_a_link(tmp_path):
    root = split_artifact(tmp_path, 0, split=[DILLON])
    q = root / DILLON / QUARTERS[0]
    shutil.move(str(q), str(tmp_path / 'elsewhere'))
    os.symlink(tmp_path / 'elsewhere', q)
    with pytest.raises(RuntimeError, match='not a folder'):
        prep(tmp_path)


def test_rejects_a_quarter_file_that_is_a_link(tmp_path):
    root = split_artifact(tmp_path, 0, split=[DILLON])
    p = root / DILLON / QUARTERS[0] / 't1-4.json.gz'
    os.remove(p)
    os.symlink('/etc/passwd', p)
    with pytest.raises(RuntimeError, match='regular file'):
        prep(tmp_path)


@pytest.mark.parametrize('bad', ['both', 'three', 'five', 'neither'])
def test_rejects_a_split_entry_of_the_wrong_form(tmp_path, bad):
    root = split_artifact(tmp_path, 0, split=[DILLON])
    ep = root / DILLON / 'entry.json'
    e = json.loads(ep.read_text())
    if bad == 'both':
        e['layers'] = e['quarters'][QUARTERS[0]]['layers']
    elif bad == 'three':
        del e['quarters'][QUARTERS[3]]
        shutil.rmtree(root / DILLON / QUARTERS[3])
    elif bad == 'five':
        e['quarters']['318_-850'] = e['quarters'][QUARTERS[0]]
    elif bad == 'neither':
        del e['quarters']
    ep.write_text(json.dumps(e))
    with pytest.raises(RuntimeError, match='entry.json is not valid'):
        prep(tmp_path)


def test_rejects_a_quarters_left_out_file_that_is_there_anyway(tmp_path):
    root = split_artifact(tmp_path, 0, split=[DILLON], left_out={QUARTERS[0]: ('t0-2m',)})
    (root / DILLON / QUARTERS[0] / 't0-2m.json.gz').write_bytes(
        cellfile.dumps(cellfile.build(DILLON, 't0-2m', {}, quarter=QUARTERS[0])))
    with pytest.raises(RuntimeError, match='not exactly'):
        prep(tmp_path)


def test_rejects_an_oversized_quarter_file(tmp_path, monkeypatch):
    root = split_artifact(tmp_path, 0, split=[DILLON])
    p = root / DILLON / QUARTERS[0] / 't1-4.json.gz'
    monkeypatch.setattr(publish, 'MAX_FILE_BYTES', p.stat().st_size - 1)
    monkeypatch.setattr(publish, 'MAX_FILE_BYTES', 1000)
    p.write_bytes(b'x' * 1001)
    with pytest.raises(RuntimeError, match='is over'):
        prep(tmp_path)


def test_rejects_a_quarter_size_that_differs_from_its_entry(tmp_path):
    root = split_artifact(tmp_path, 0, split=[DILLON])
    e = json.loads((root / DILLON / 'entry.json').read_text())
    e['quarters'][QUARTERS[0]]['layers']['t1-4']['bytes'] += 1
    (root / DILLON / 'entry.json').write_text(json.dumps(e))
    with pytest.raises(RuntimeError, match='size differs'):
        prep(tmp_path)


# Requirement: The site sets its CORS and cache headers ("A quarter's cache")
def test_a_quarter_path_matches_one_cache_rule():
    rules = {k: v for k, v in header_rules().items() if any(x.startswith('Cache-Control') for x in v)}
    hits = [k for k in rules if rule_matches(k, f'/colorado/{DILLON}/{QUARTERS[0]}/t0-2m.json.gz')]
    assert len(hits) == 1 and rules[hits[0]] == ['Cache-Control: public, max-age=86400']


# Requirement: Each region has an overview of its built cells' tier 4 ("A split cell's tier 4")
def test_the_overview_holds_a_split_cells_quarters_in_order(live, tmp_path):
    counts = dict(zip(QUARTERS, (1, 2, 0, 4)))
    split_artifact(tmp_path, 0, split=[DILLON], t4=counts)
    _c, out = run(tmp_path, live)
    got = overview_doc(out)['tiers']['4']['30']
    assert len(got) == 7
    want = []
    for q in QUARTERS:
        want += cellfile.loads((out / f'colorado/{DILLON}/{q}/t1-4.json.gz').read_bytes())['tiers']['4']['30']
    assert got == want
    assert got[0] == want[0] and got[-4:] == cellfile.loads(
        (out / f'colorado/{DILLON}/{QUARTERS[3]}/t1-4.json.gz').read_bytes())['tiers']['4']['30']


# Requirement: The site carries its sources notice ("A split cell's projects")
def test_the_license_lists_a_split_cells_projects(live, tmp_path):
    split_artifact(tmp_path, 0, split=[DILLON], projects=['CO_Split_A_2017', 'CO_Split_B_2020'])
    _c, out = run(tmp_path, live)
    text = (out / 'LICENSE.txt').read_text()
    assert '- CO_Split_A_2017' in text and '- CO_Split_B_2020' in text


# Requirement: The site holds at most 19,000 files ("Counting a split cell's files")
def test_the_file_count_counts_a_split_cells_files(live, tmp_path, monkeypatch):
    split_artifact(tmp_path, 0, whole=[OTHER], split=[DILLON], left_out={QUARTERS[0]: ('t0-2m',)})
    # 4 fixed files + the overview + 3 whole + 11 quarter files = 19
    monkeypatch.setattr(site, 'MAX_SITE_FILES', 18)
    with pytest.raises(RuntimeError, match='19 files'):
        run(tmp_path, live)
    monkeypatch.setattr(site, 'MAX_SITE_FILES', 19)
    _c, out = run(tmp_path, live, 'site2')
    assert len(deployed(out) | {'hashes.json'}) == 19


# CLAUDE.md: the plan and deploy jobs use only the standard library (the deploy job holds the token);
# the quarter cut (shapely) stays in the build job's code.
def test_the_plan_and_deploy_code_imports_no_third_party_package():
    import subprocess
    import sys
    code = ('import sys; import slope_extracts.site, slope_extracts.publish, slope_extracts.overview; '
            'print(sorted({m.split(".")[0] for m in sys.modules} & {"numpy", "rasterio", "shapely"}))')
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run([sys.executable, '-c', code], cwd=root, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == '[]'


# Requirement: The manifest lists quartered cells apart from whole ones ("A live manifest from before this change")
def test_a_deploy_over_a_live_manifest_without_quartered(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    m = json.loads(live.files['manifest.json'])
    del m['regions'][0]['quartered']
    live.files['manifest.json'] = json.dumps(m).encode()
    split_artifact(tmp_path, 0, split=[OTHER])
    changed, out2 = run(tmp_path, live, 'site2')
    assert changed is True
    r = json.loads((out2 / 'manifest.json').read_text())['regions'][0]
    assert list(r['cells']) == [DILLON] and list(r['quartered']) == [OTHER]


# Requirement: The manifest lists quartered cells apart from whole ones ("Quarters out of order")
def test_a_live_quartered_entry_with_its_quarters_out_of_order_fails_the_plan():
    m = split_manifest()
    e = m['regions'][0]['quartered'][DILLON]
    e['quarters'] = dict(reversed(list(e['quarters'].items())))
    with pytest.raises(RuntimeError, match='the live manifest is not valid'):
        fetch_body(m)


# --- deploying from hashes (change deploy-from-hashes) -------------------------------------------

def hashes_doc(files):
    return {'format': 'slope-hashes', 'version': 1, 'files': files}


# Requirement: The live hashes belong to the live manifest
@pytest.mark.parametrize('bad', [
    [], {'format': 'slope-hashes', 'version': 1}, dict(hashes_doc({}), extra=1), hashes_doc({'/a.json': 'zz'}),
    hashes_doc({'/a.json': 'EC47DA64E7DA6749028B38BC647D8A22'}), hashes_doc({'a.json': 'ec47da64e7da6749028b38bc647d8a22'}),
    {'format': 'slope-hashes', 'version': 2, 'files': {}}, hashes_doc([]),
])
def test_a_hashes_file_not_of_its_form_is_refused(bad):
    with pytest.raises(ValueError):
        publish.validate_hashes(bad)


def test_a_hashes_file_of_its_form_is_read():
    doc = hashes_doc({'/a.json': 'ec47da64e7da6749028b38bc647d8a22'})
    assert publish.validate_hashes(doc) == {'/a.json': 'ec47da64e7da6749028b38bc647d8a22'}


# Requirement: A deploy reads back only what it needs ("A run after a run")
def test_a_run_after_a_run_reads_back_only_the_t1_4_files(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    live.requests.clear()
    artifact(tmp_path, 0, [OTHER])
    changed, out2 = run(tmp_path, live, 'site2')
    assert changed is True
    assert sorted(live.requests) == sorted(['manifest.json', 'hashes.json', f'colorado/{DILLON}/t1-4.json.gz'])
    kept = json.loads((state_of(out2) / 'kept.json').read_text())
    hashes = json.loads(live.files['hashes.json'])['files']
    assert kept == {f'/colorado/{DILLON}/{l}.json.gz': {'hash': hashes[f'/colorado/{DILLON}/{l}.json.gz'],
                                                       'bytes': len(live.files[f'colorado/{DILLON}/{l}.json.gz'])}
                    for l in ('t0-3m', 't0-2m')}
    assert not (out2 / f'colorado/{DILLON}/t0-3m.json.gz').exists()
    assert (out2 / f'colorado/{DILLON}/t1-4.json.gz').exists()
    manifest = json.loads((out2 / 'manifest.json').read_text())
    assert deployed(out2) == set(site.site_files(manifest)) - {'hashes.json'}
    # the read-back t1-4 must hash to its listed entry: the Node step checks it against this
    checks = json.loads((state_of(out2) / 'checks.json').read_text())
    assert checks['readback'] == {f'/colorado/{DILLON}/t1-4.json.gz': hashes[f'/colorado/{DILLON}/t1-4.json.gz']}
    assert checks['manifest'] == hashes['/manifest.json']
    assert (state_of(out2) / 'live-manifest.json').read_bytes() == live.files['manifest.json']


# Requirement: A deploy reads back only what it needs ("The first run after this change")
def test_the_first_run_after_this_change_reads_back_everything(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out, hashes=False)
    live.requests.clear()
    artifact(tmp_path, 0, [OTHER])
    _c, out2 = run(tmp_path, live, 'site2')
    assert set(f'colorado/{DILLON}/{l}.json.gz' for l in site.LAYERS) <= set(live.requests)
    assert json.loads((state_of(out2) / 'kept.json').read_text()) == {}
    checks = json.loads((state_of(out2) / 'checks.json').read_text())
    assert checks['manifest'] is None and set(checks['readback'].values()) == {None}
    assert all((out2 / f'colorado/{DILLON}/{l}.json.gz').exists() for l in site.LAYERS)


# Requirement: A deploy reads back only what it needs (no live manifest: no hashes.json read)
def test_with_no_live_manifest_no_hashes_file_is_read(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    run(tmp_path, live)
    assert 'hashes.json' not in live.requests
    out = tmp_path / 'site'
    assert json.loads((state_of(out) / 'checks.json').read_text()) == {'manifest': None, 'readback': {}}
    assert not (state_of(out) / 'live-manifest.json').exists()


# Requirement: The live hashes belong to the live manifest ("A hash not of its form", attack tests)
@pytest.mark.parametrize('body', [b'not json', json.dumps(hashes_doc({'/x.json': 'zz'})).encode(),
                                  b'{"format": "slope-hashes", "version": 1, "files": {}, "x": 1}'])
def test_a_live_hashes_file_not_of_its_form_fails_the_deploy(live, tmp_path, body):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    live.files['hashes.json'] = body
    artifact(tmp_path, 0, [OTHER])
    with pytest.raises(RuntimeError, match='hashes.json'):
        run(tmp_path, live, 'site2')


def test_a_live_hashes_file_over_4_mib_fails_the_deploy(live, tmp_path, monkeypatch):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    monkeypatch.setattr(publish, 'MAX_HASHES_BYTES', 100)
    artifact(tmp_path, 0, [OTHER])
    with pytest.raises(RuntimeError, match='over 100 bytes'):
        run(tmp_path, live, 'site2')


def test_a_live_hashes_file_answering_an_error_fails_the_deploy(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    real = live.get

    def get(url, limit):
        if url.endswith('/hashes.json'):
            raise RuntimeError(f'{url} answered 503')
        return real(url, limit)
    artifact(tmp_path, 0, [OTHER])
    with pytest.raises(RuntimeError, match='503'):
        publish.assemble(str(tmp_path / 'artifacts'), str(tmp_path / 'site2'), planned_jobs(tmp_path), True,
                         regions=REGION, site_url='https://slope.test', get=get, log=lambda *_: None)


# Requirement: The live hashes belong to the live manifest ("A path that is no longer kept")
def test_entries_for_paths_no_longer_kept_are_ignored(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    split_artifact(tmp_path, 0, split=[DILLON])
    _c, out2 = run(tmp_path, live, 'site2')
    kept = json.loads((state_of(out2) / 'kept.json').read_text())
    assert kept == {}
    assert not any(p.startswith(f'colorado/{DILLON}/t') for p in deployed(out2))


# Requirement: A deploy reads back only what it needs (a kept path the hashes file doesn't list)
def test_a_kept_file_the_hashes_file_does_not_list_is_read_back(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    h = json.loads(live.files['hashes.json'])
    del h['files'][f'/colorado/{DILLON}/t0-3m.json.gz']
    live.files['hashes.json'] = json.dumps(h).encode()
    live.requests.clear()
    artifact(tmp_path, 0, [OTHER])
    _c, out2 = run(tmp_path, live, 'site2')
    assert f'colorado/{DILLON}/t0-3m.json.gz' in live.requests
    assert (out2 / f'colorado/{DILLON}/t0-3m.json.gz').exists()
    checks = json.loads((state_of(out2) / 'checks.json').read_text())
    assert checks['readback'][f'/colorado/{DILLON}/t0-3m.json.gz'] is None


# Requirement: Deploying adds to the live site (`_headers` goes beside the manifest, not in the folder)
def test_headers_go_beside_the_deployment_not_in_its_folder(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    assert not (out / '_headers').exists() and not (out / 'hashes.json').exists()
    assert (state_of(out) / '_headers').read_text() == site.HEADERS


# Requirement: The site sets its CORS and cache headers ("The hashes' cache")
def test_the_hashes_file_matches_one_cache_rule():
    rules = {k: v for k, v in header_rules().items() if any(x.startswith('Cache-Control') for x in v)}
    hits = [k for k in rules if rule_matches(k, '/hashes.json')]
    assert len(hits) == 1 and rules[hits[0]] == ['Cache-Control: public, max-age=300']


# Requirement: The site holds at most 19,000 files ("Counting the hashes file")
def test_the_file_count_counts_the_hashes_file_but_not_headers(live, tmp_path, monkeypatch):
    artifact(tmp_path, 0, [DILLON])
    # manifest, hashes, 404, LICENSE, 3 layers, the overview = 8; _headers isn't named
    monkeypatch.setattr(site, 'MAX_SITE_FILES', 8)
    _c, out = run(tmp_path, live)
    m = json.loads((out / 'manifest.json').read_text())
    assert 'hashes.json' in site.site_files(m) and '_headers' not in site.site_files(m)
    monkeypatch.setattr(site, 'MAX_SITE_FILES', 7)
    with pytest.raises(RuntimeError, match='8 files'):
        run(tmp_path, live, 'site2')


def test_main_takes_the_state_folder(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(publish, 'assemble', lambda *a, **k: seen.update(k))
    monkeypatch.setenv('PLAN_JOBS', '[]')
    monkeypatch.setenv('PLAN_HAD_MANIFEST', 'false')
    assert publish.main(['assemble', '--artifacts', str(tmp_path), '--out', str(tmp_path / 'o'),
                         '--state', str(tmp_path / 's')]) == 0
    assert seen['state_dir'] == str(tmp_path / 's')


# --- the assemble step and the Node hash step together (real Pages hashes) -----------------------

NODE_MODULES = pathlib.Path(__file__).resolve().parent.parent / 'deploy' / 'node_modules' / 'blake3-wasm'


def node_hash(out):
    """deploy/pages.mjs hash on a run's folders; the test workflow installs blake3-wasm first."""
    import subprocess
    assert NODE_MODULES.exists(), 'run npm ci --ignore-scripts in deploy/ first'
    script = pathlib.Path(__file__).resolve().parent.parent / 'deploy' / 'pages.mjs'
    return subprocess.run(['node', str(script), 'hash', '--site', str(out), '--state', str(state_of(out))],
                          capture_output=True, text=True)


def publish_for_real(live, out):
    """What creating the deployment from deployment.json would leave live."""
    state = state_of(out)
    deployment = json.loads((state / 'deployment.json').read_text())
    old = live.files
    live.files = {}
    for p in deployment:
        local = out / p.lstrip('/')
        live.files[p.lstrip('/')] = local.read_bytes() if local.exists() else old[p.lstrip('/')]
    live.files['_headers'] = (state / '_headers').read_bytes()


# Requirement: A deploy reads back only what it needs; The live hashes belong to the live manifest
def test_assemble_and_hash_deploy_a_second_run_by_hash(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    r = node_hash(out)
    assert r.returncode == 0, r.stderr
    publish_for_real(live, out)
    first = json.loads(live.files['hashes.json'])['files']
    assert sorted(first) == sorted('/' + p for p in site.site_files(json.loads(live.files['manifest.json'])) if p != 'hashes.json')
    artifact(tmp_path, 0, [OTHER])
    live.requests.clear()
    _c, out2 = run(tmp_path, live, 'site2')
    assert sorted(live.requests) == sorted(['manifest.json', 'hashes.json', f'colorado/{DILLON}/t1-4.json.gz'])
    r = node_hash(out2)
    assert r.returncode == 0, r.stderr
    deployment = json.loads((state_of(out2) / 'deployment.json').read_text())
    for l in ('t0-3m', 't0-2m', 't1-4'):
        p = f'/colorado/{DILLON}/{l}.json.gz'
        assert deployment[p] == first[p]
    publish_for_real(live, out2)
    manifest = json.loads(live.files['manifest.json'])
    assert set(manifest['regions'][0]['cells']) == {DILLON, OTHER}
    assert set(live.files) == set(site.site_files(manifest)) | {'_headers'}


# Requirement: The live hashes belong to the live manifest ("Hashes from another deployment")
def test_hashes_from_another_deployment_fail_the_hash_step(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    assert node_hash(out).returncode == 0
    publish_for_real(live, out)
    m = json.loads(live.files['manifest.json'])
    m['attribution'] = 'a newer deployment'
    live.files['manifest.json'] = json.dumps(m).encode()  # hashes.json is still the older deployment's
    artifact(tmp_path, 0, [OTHER])
    _c, out2 = run(tmp_path, live, 'site2')
    r = node_hash(out2)
    assert r.returncode == 1 and 'another deployment' in r.stderr


# Requirement: A deploy reads back only what it needs ("The first run after this change")
def test_the_first_run_after_this_change_writes_hashes_for_both_cells(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out, hashes=False)  # a site deployed before this change: no hashes.json
    artifact(tmp_path, 0, [OTHER])
    _c, out2 = run(tmp_path, live, 'site2')
    r = node_hash(out2)
    assert r.returncode == 0, r.stderr
    files = json.loads((out2 / 'hashes.json').read_text())['files']
    assert {f'/colorado/{c}/{l}.json.gz' for c in (DILLON, OTHER) for l in site.LAYERS} <= set(files)


# deploy/check_cell.py: the cell-file checks for a file the upload step reads back (bytes on stdin).
# Requirement: Files read back from the live site are checked; A deploy uploads only the files Cloudflare lacks
def check_cell_cli(path, data):
    import subprocess
    import sys
    script = pathlib.Path(__file__).resolve().parent.parent / 'deploy' / 'check_cell.py'
    return subprocess.run([sys.executable, '-I', str(script), path], input=data, capture_output=True)


def test_the_read_back_checker_accepts_a_cell_file_of_its_path():
    data = cellfile.dumps(cellfile.build(DILLON, 't0-3m', {}))
    assert check_cell_cli(f'/colorado/{DILLON}/t0-3m.json.gz', data).returncode == 0
    q = cellfile.dumps(cellfile.build(DILLON, 't1-4', {}, quarter=QUARTERS[1]))
    assert check_cell_cli(f'/colorado/{DILLON}/{QUARTERS[1]}/t1-4.json.gz', q).returncode == 0


@pytest.mark.parametrize('path, data', [
    (f'/colorado/{DILLON}/t0-3m.json.gz', b'not gzip'),
    (f'/colorado/{DILLON}/t0-3m.json.gz', cellfile.dumps(cellfile.build(OTHER, 't0-3m', {}))),
    (f'/colorado/{DILLON}/t1-4.json.gz', cellfile.dumps(cellfile.build(DILLON, 't0-3m', {}))),
    (f'/colorado/{DILLON}/{QUARTERS[1]}/t1-4.json.gz', cellfile.dumps(cellfile.build(DILLON, 't1-4', {}, quarter=QUARTERS[0]))),
    ('/manifest.json', b'{}'), (f'/../{DILLON}/t0-3m.json.gz', b''), (f'/colorado/{DILLON}/x.json.gz', b''),
    (f'/colorado/{DILLON}/999_0/t1-4.json.gz', b''),
])
def test_the_read_back_checker_refuses_anything_else(path, data):
    r = check_cell_cli(path, data)
    assert r.returncode != 0 and r.stdout == b''
