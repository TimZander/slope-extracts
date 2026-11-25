import json
import os
import shutil

import pytest

from slope_extracts import build_cell, cellfile, grid, overview, publish, site

REGION = [{'id': 'colorado', 'name': 'Colorado', 'bounds': {'south': 37.01, 'west': -109.04, 'north': 40.99, 'east': -102.06}}]
DILLON, OTHER = '158_-425', '158_-424'


def entry(cell, recipe=1):
    return {'cell': cell, 'recipe': recipe, 'built': '2026-11-23', 'sources': {'lidar': 1.0, 'dem10m': 0.0, 'none': 0.0},
            'projects': ['CO_Central_Western_2016'],
            'layers': {l: {'bytes': 0, 'tiers': {}} for l in site.LAYERS}}


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
        return 200, self.files[path]

    def publish(self, out):
        """What a deploy of `out` would leave live."""
        self.files = {}
        for root, _d, names in os.walk(out):
            for n in names:
                full = os.path.join(root, n)
                self.files[os.path.relpath(full, out).replace(os.sep, '/')] = open(full, 'rb').read()


@pytest.fixture
def live(monkeypatch):
    s = FakeSite()
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    return s


def fake_cell(root, cell, tag=0):
    """A built cell as build_cell writes it, with one small polygon."""
    cdir = root / cell
    cdir.mkdir(parents=True)
    layers = {}
    s, w, _n, _e = grid.cell_bounds(cell)
    y, x = grid.to_units(s) + 100, grid.to_units(w) + 100
    ring = [[(y + tag, x), (y + 10, x), (y + 10, x + 10)]]
    for l in site.LAYERS:
        tiers = {0: {30: [ring]}} if l.startswith('t0') else {4: {30: [ring]}}
        data = cellfile.dumps(cellfile.build(cell, l, tiers))
        (cdir / f'{l}.json.gz').write_bytes(data)
        layers[l] = {'bytes': len(data), 'tiers': {}}
    e = dict(entry(cell), layers=layers)
    (cdir / 'entry.json').write_text(json.dumps(e))
    return cdir


def artifact(tmp_path, n, cells, tag=0):
    root = tmp_path / 'artifacts' / f'cells-{n}'
    if (tmp_path / 'artifacts').exists():
        shutil.rmtree(tmp_path / 'artifacts')
    root.mkdir(parents=True)
    (root / 'jobs.txt').write_text(' '.join(f'colorado/{c}' for c in cells))
    for c in cells:
        fake_cell(root, c, tag)
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
                               regions=REGION, site_url='https://slope.test', get=live.get, log=lambda *_: None)
    return changed, out


def test_first_run_assembles_the_site(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    changed, out = run(tmp_path, live)
    assert changed is True
    files = sorted(str(p.relative_to(out)) for p in out.rglob('*') if p.is_file())
    assert files == ['404.html', 'LICENSE.txt', '_headers', f'colorado/{DILLON}/t0-2m.json.gz',
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
    assert (out2 / f'colorado/{DILLON}/t0-3m.json.gz').read_bytes() == (out / f'colorado/{DILLON}/t0-3m.json.gz').read_bytes()
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
    assert (out2 / f'colorado/{DILLON}/t0-3m.json.gz').exists()


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
    artifact(tmp_path, 0, [DILLON])
    monkeypatch.setattr(publish, 'MAX_FILE_BYTES', 10)
    with pytest.raises(RuntimeError, match='limit'):
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
    assert set(rules) == {'/*', '/:region/:cell/*', '/:region/overview.json.gz', '/LICENSE.txt', '/manifest.json'}


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
