import json
import os
import pathlib
import shutil

import pytest

from slope_extracts import build_cell, cellfile, grid, overview, publish, site

import sitefake
from sitefake import (AREAS, DILLON, EMPTY, LEFT_OUT, NEIGHBOUR, OTHER, URL, FakeSite, deployed, entry, fake_hash,
                      planned_jobs, state_of)

TILE = '19_-54'  # DILLON's tile
OTHER_TILE = '19_-53'


@pytest.fixture
def live(monkeypatch):
    s = FakeSite()
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    return s


def fake_cell(root, cell, tag=0, left_out=()):
    return sitefake.fake_cell(root, cell, tag=tag, left_out=left_out)


def artifact(tmp_path, n, cells, tag=0, left_out=()):
    return sitefake.artifact(tmp_path, cells, n=n, tag=tag, left_out=left_out)


def run(tmp_path, live, name='site', jobs=None, had_manifest=None):
    return sitefake.run(tmp_path, live, name=name, jobs=jobs, had_manifest=had_manifest)


def merged(indexes):
    out = {'coverage': [], 'cells': {}, 'quartered': {}}
    for doc in indexes:
        out['coverage'] += doc['coverage']
        out['cells'].update(doc['cells'])
        out['quartered'].update(doc['quartered'])
    return out


def tiles_of(out):
    """A run's tile indexes, merged: {'coverage', 'cells', 'quartered'}."""
    return merged(json.loads(p.read_text()) for p in sorted((out / 'tiles').glob('*/index.json')))


def tile_docs(out):
    return {p.parent.name: json.loads(p.read_text()) for p in (out / 'tiles').glob('*/index.json')}


def live_tile_docs(live):
    return {k.split('/')[1]: json.loads(v) for k, v in live.files.items() if k.startswith('tiles/') and k.endswith('/index.json')}


def edit_live_tile(live, tile, fn):
    """Edits a live tile index in place, keeping the manifest's size and counts as the index has them."""
    doc = json.loads(live.files[f'tiles/{tile}/index.json'])
    fn(doc)
    body = (json.dumps(doc, indent=1) + '\n').encode()
    live.files[f'tiles/{tile}/index.json'] = body
    m = json.loads(live.files['manifest.json'])
    built = sorted({**doc['cells'], **doc['quartered']}, key=grid.compare_key)
    m['tiles'][tile].update(indexBytes=len(body), built=len(built), builtMask=grid.mask(built),
                            covered=len(doc['coverage']), coveredMask=grid.mask(doc['coverage']))
    live.files['manifest.json'] = json.dumps(m).encode()


def live_tiles(live):
    return merged(json.loads(v) for k, v in sorted(live.files.items()) if k.startswith('tiles/') and k.endswith('/index.json'))


def test_first_run_assembles_the_site(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    changed, out = run(tmp_path, live)
    assert changed is True
    files = sorted(str(p.relative_to(out)) for p in out.rglob('*') if p.is_file())
    tiles = sorted(json.loads((out / 'manifest.json').read_text())['tiles'])
    assert files == sorted(['404.html', 'LICENSE.txt', f'cells/{DILLON}/t0-2m.json.gz', f'cells/{DILLON}/t0-3m.json.gz',
                            f'cells/{DILLON}/t1-4.json.gz', f'tiles/{TILE}/overview.json.gz', 'manifest.json']
                           + [f'tiles/{t}/index.json' for t in tiles])
    assert len(tiles_of(out)['coverage']) == 464 and len(tiles) == 12


def test_second_run_keeps_the_live_cells(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    artifact(tmp_path, 0, [OTHER])
    changed, out2 = run(tmp_path, live, 'site2')
    assert changed is True
    # the kept cell's t0-3m is deployed by its live hash, unread
    kept = json.loads((state_of(out2) / 'kept.json').read_text())
    assert kept[f'/cells/{DILLON}/t0-3m.json.gz']['hash'] == json.loads(live.files['hashes.json'])['files'][f'/cells/{DILLON}/t0-3m.json.gz']
    assert set(tiles_of(out2)['cells']) == {DILLON, OTHER}
    # a rebuilt cell is not read back from the live site
    assert f'cells/{OTHER}/t0-3m.json.gz' not in live.requests


def test_nothing_built_deploys_nothing(live, tmp_path):
    (tmp_path / 'artifacts').mkdir()
    changed, out = run(tmp_path, live)
    assert changed is False and not out.exists()
    # it reads the live manifest (a version 1 site would still deploy), and nothing else
    assert live.requests == ['manifest.json']


def test_failed_cell_keeps_its_live_files(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    root = artifact(tmp_path, 0, [OTHER])
    (root / 'jobs.txt').write_text(f'{OTHER} {DILLON}')  # Dillon failed this run
    (root / 'failed.json').write_text(json.dumps([DILLON]))
    _c, out2 = run(tmp_path, live, 'site2', jobs=[f'{OTHER} {DILLON}'])
    assert f'cells/{DILLON}/t0-3m.json.gz' in deployed(out2)


def test_a_tampered_live_file_fails_the_deploy(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    live.files[f'cells/{DILLON}/t1-4.json.gz'] = b'x' * 10
    artifact(tmp_path, 0, [OTHER])
    with pytest.raises(RuntimeError, match='bytes, not the'):
        run(tmp_path, live, 'site2')


def test_a_live_file_missing_fails_the_deploy(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    del live.files[f'cells/{DILLON}/t1-4.json.gz']
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
    (root / 'jobs.txt').write_text(f'{DILLON} {OTHER}')
    with pytest.raises(RuntimeError, match='not the list the plan gave'):
        run(tmp_path, FakeSite(), jobs=[DILLON])


def test_rejects_an_artifact_the_plan_did_not_make(tmp_path):
    artifact(tmp_path, 0, [DILLON])
    extra = tmp_path / 'artifacts' / 'cells-99'
    extra.mkdir()
    (extra / 'jobs.txt').write_text(OTHER)
    fake_cell(extra, OTHER)
    with pytest.raises(RuntimeError, match='not a planned cells artifact'):
        run(tmp_path, FakeSite(), jobs=[DILLON])


def test_rejects_a_plan_with_a_cell_twice(tmp_path):
    artifact(tmp_path, 0, [DILLON])
    with pytest.raises(RuntimeError, match='twice'):
        run(tmp_path, FakeSite(), jobs=[DILLON, DILLON])


def test_rejects_a_cell_outside_the_coverage(tmp_path):
    artifact(tmp_path, 0, [DILLON])
    with pytest.raises(RuntimeError, match='not a covered cell'):
        run(tmp_path, FakeSite(), jobs=['0_0'])


def test_rejects_a_path_in_the_plan(tmp_path):
    artifact(tmp_path, 0, [DILLON])
    with pytest.raises(RuntimeError, match='not a covered cell'):
        run(tmp_path, FakeSite(), jobs=['../158_-425'])


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
    monkeypatch.setattr(site, 'MAX_SITE_FILES', 19)  # 4 fixed files + 3 layers + the overview + 12 tile indexes = 20
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
    assert set(rules) == {'/*', '/cells/*', '/tiles/:tile/index.json', '/tiles/:tile/overview.json.gz', '/LICENSE.txt',
                          '/manifest.json', '/hashes.json'}


def test_license_lists_the_projects_used():
    cells = {DILLON: dict(site.manifest_entry(entry(DILLON)), projects=['CO_A_2016', 'CO_B_2020', 'CO_C_2023'])}
    text = site.license_text(cells)
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
    return publish.fetch_live('https://slope.test', live.get, first_deploy=first_deploy)


@pytest.mark.parametrize('body', [b'', b'<!doctype html><title>placeholder</title>'])
def test_first_deploy_reads_a_placeholder_as_no_manifest(body):
    assert fetch(PlaceholderSite(body=body), True) is None


def test_first_deploy_publishes_a_site_with_its_own_404(tmp_path, monkeypatch):
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    live = PlaceholderSite(body=b'<html>placeholder</html>')
    artifact(tmp_path, 0, [DILLON])
    changed = publish.assemble(str(tmp_path / 'artifacts'), str(tmp_path / 'site'), planned_jobs(tmp_path), False,
                               areas=AREAS, site_url='https://slope.test', get=live.get, log=lambda *_: None,
                               first_deploy=True)
    assert changed is True
    assert (tmp_path / 'site' / '404.html').read_text() == site.NOT_FOUND_HTML
    assert set(tiles_of(tmp_path / 'site')['cells']) == {DILLON}


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
    assert fetch(live, True)['manifest'] == json.loads(live.files['manifest.json'])
    artifact(tmp_path, 0, [OTHER])
    changed = publish.assemble(str(tmp_path / 'artifacts'), str(tmp_path / 'site2'), planned_jobs(tmp_path), True,
                               areas=AREAS, site_url='https://slope.test', get=live.get, log=lambda *_: None,
                               first_deploy=True)
    assert changed is True
    assert set(tiles_of(tmp_path / 'site2')['cells']) == {DILLON, OTHER}


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
                         areas=AREAS, site_url='https://slope.test', get=live.get, log=lambda *_: None,
                         first_deploy=True)
    assert not (tmp_path / 'site').exists()


def test_the_plan_and_the_assembler_read_the_switch(tmp_path, monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(publish, 'fetch_live', lambda *a, **k: seen.append(k.get('first_deploy')) or None)
    monkeypatch.setenv('FIRST_DEPLOY', 'true')
    assert site.main_plan([]) == 0
    assert 'had_manifest=false' in capsys.readouterr().out
    monkeypatch.setattr(publish, 'assemble', lambda *a, **k: seen.append(k.get('first_deploy')))
    monkeypatch.setenv('PLAN_JOBS', '[]')
    monkeypatch.setenv('PLAN_HAD_MANIFEST', 'false')
    monkeypatch.setenv('PLAN_MANIFEST_VERSION', 'none')
    assert publish.main(['assemble', '--artifacts', str(tmp_path), '--out', str(tmp_path / 'o')]) == 0
    assert seen == [True, True]


# --- tile overviews (slope-overview version 2) -------------------------------------------------

def overview_doc(out, tile=TILE):
    return cellfile_loads_overview((out / 'tiles' / tile / 'overview.json.gz').read_bytes())


def cellfile_loads_overview(data):
    import gzip
    return json.loads(gzip.decompress(data))


def covered_order(cells):
    cov = site.area_coverage(AREAS[0])
    return sorted(cells, key=cov.index)


def tier4_polygons(cell, count, start=0):
    """`count` distinct one-ring tier-4 polygons inside `cell`, numbered from `start`."""
    s, w, _n, _e = grid.cell_bounds(cell)
    y, x = grid.to_units(s) + 100, grid.to_units(w) + 100
    return [[[(y + 20 * i, x), (y + 20 * i + 10, x), (y + 20 * i + 10, x + 10)]] for i in range(start, start + count)]


# Requirement: Each tile has an overview of its built cells' tier 4 ("The same cells give the same bytes")
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
    assert first == second == (out / f'tiles/{TILE}/overview.json.gz').read_bytes()


# Requirement: The deploy job writes the overview from the cells it publishes ("A run adds a cell")
def test_a_run_that_adds_a_cell_adds_it_to_the_overview(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    artifact(tmp_path, 0, [NEIGHBOUR], tag=1)
    _c, out2 = run(tmp_path, live, 'site2')
    assert len(overview_doc(out2)['tiers']['4']['30']) == 2
    assert f'tiles/{TILE}/overview.json.gz' not in live.requests


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


# Requirement: A tile's entry counts and masks its cells ("A tile overview's entry")
def test_the_manifest_gives_the_overviews_size_and_counts(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    region = json.loads((out / 'manifest.json').read_text())['tiles'][TILE]
    assert region['overview'] == {'bytes': (out / f'tiles/{TILE}/overview.json.gz').stat().st_size,
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


# Requirement: The deploy job writes the overview from the cells it publishes (a build job can't supply one)
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
    cell_files = sorted(str(p.relative_to(out)) for p in (out / 'cells' / DILLON).rglob('*'))
    assert cell_files == [f'cells/{DILLON}/t0-3m.json.gz', f'cells/{DILLON}/t1-4.json.gz']
    e = tiles_of(out)['cells'][DILLON]
    assert e['layers']['t0-2m'] == LEFT_OUT
    assert e['layers']['t0-3m']['bytes'] > 0 and e['layers']['t1-4']['bytes'] > 0
    assert f'cells/{DILLON}/t0-2m.json.gz' not in site.site_files(tile_docs(out))


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


@pytest.mark.parametrize('tiers', [{'0': {'polygons': 12, 'points': 0}}, {'0': {'polygons': 0, 'points': 40}},
                                   {'0': {'polygons': 0, 'points': 0}, '1': {'polygons': 0, 'points': 0}}])
def test_rejects_a_marker_with_other_tiers(tmp_path, tiers):
    root = artifact(tmp_path, 0, [DILLON], left_out=('t0-2m',))
    e = json.loads((root / DILLON / 'entry.json').read_text())
    e['layers']['t0-2m'] = {'bytes': 0, 'tiers': tiers}
    (root / DILLON / 'entry.json').write_text(json.dumps(e))
    with pytest.raises(RuntimeError, match='entry.json is not valid'):
        prep(tmp_path)


def test_the_marker_on_another_layer_in_the_live_manifest_fails_the_plan(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    doc = json.loads(live.files[f'tiles/{TILE}/index.json'])
    doc['cells'][DILLON]['layers']['t0-3m'] = dict(LEFT_OUT)
    body = (json.dumps(doc, indent=1) + '\n').encode()
    live.files[f'tiles/{TILE}/index.json'] = body
    m = json.loads(live.files['manifest.json'])
    m['tiles'][TILE]['indexBytes'] = len(body)
    live.files['manifest.json'] = json.dumps(m).encode()
    with pytest.raises(RuntimeError, match='the live manifest is not valid'):
        publish.fetch_live('https://slope.test', live.get)


def test_a_live_cell_without_its_2m_layer_is_read_back_without_it(live, tmp_path):
    # "hashes.json lists none of its files": every kept file is read back
    artifact(tmp_path, 0, [DILLON], left_out=('t0-2m',))
    _c, out = run(tmp_path, live)
    live.publish(out, hashes=False)
    before = live_tiles(live)['cells'][DILLON]
    live.requests.clear()
    artifact(tmp_path, 0, [OTHER])
    changed, out2 = run(tmp_path, live, 'site2')
    assert changed is True
    assert f'cells/{DILLON}/t0-2m.json.gz' not in live.requests
    assert f'cells/{DILLON}/t0-3m.json.gz' in live.requests and f'cells/{DILLON}/t1-4.json.gz' in live.requests
    assert not (out2 / f'cells/{DILLON}/t0-2m.json.gz').exists()
    after = tiles_of(out2)['cells']
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
                if n == 0:
                    layers[l] = dict(EMPTY)  # no polygon: no file
                    continue
                tiers = {4: {30: [q_ring(cell, q, 20 * i + tag) for i in range(n)]}}
            doc = cellfile.build(cell, l, tiers, quarter=q)
            data = cellfile.dumps(doc)
            (cdir / q / f'{l}.json.gz').write_bytes(data)
            layers[l] = {'bytes': len(data), 'tiers': cellfile.stats(doc)}
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
    (root / 'jobs.txt').write_text(' '.join(covered_order(list(whole) + list(split))))
    for c in whole:
        fake_cell(root, c)
    for c in split:
        fake_split_cell(root, c, **kw)
    return root


def quarter_files(cell, layers=site.LAYERS, skip=()):
    return [f'cells/{cell}/{q}/{l}.json.gz' for q in grid.quarters(cell) for l in layers if (q, l) not in skip]


# Requirement: The manifest lists quartered cells apart from whole ones ("A region with one split cell")
# Requirement: A quarter file names its cell and its quarter
def test_a_split_cell_is_published_under_quartered(live, tmp_path):
    split_artifact(tmp_path, 0, whole=[OTHER], split=[DILLON])
    changed, out = run(tmp_path, live)
    assert changed is True
    r = tiles_of(out)
    assert list(r['cells']) == [OTHER]
    assert list(r['quartered']) == [DILLON]
    e = r['quartered'][DILLON]
    assert set(e) == {'recipe', 'built', 'sources', 'projects', 'quarters'}
    assert list(e['quarters']) == QUARTERS
    for q in QUARTERS:
        assert set(e['quarters'][q]) == {'layers'}
        for l in site.LAYERS:
            p = out / f'cells/{DILLON}/{q}/{l}.json.gz'
            assert e['quarters'][q]['layers'][l]['bytes'] == p.stat().st_size
            doc = json.loads(__import__('gzip').decompress(p.read_bytes()))
            assert (doc['cell'], doc['quarter'], doc['layer']) == (DILLON, q, l)
    assert not any((out / f'cells/{DILLON}/{l}.json.gz').exists() for l in site.LAYERS)
    files = sorted(str(p.relative_to(out)) for p in out.rglob('*') if p.is_file())
    assert sorted(set(site.site_files(tile_docs(out))) - {'hashes.json'}) == files


# Requirement: The manifest lists quartered cells apart from whole ones ("No split cell")
# Requirement: The manifest lists quartered cells apart from whole ones ("No split cell")
def test_a_region_with_no_split_cell_has_an_empty_quartered(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    assert tiles_of(out)['quartered'] == {}


# Requirement: The manifest lists quartered cells apart from whole ones ("A live manifest from before this change")
def test_a_live_split_cell_is_read_back_by_its_quarters(live, tmp_path):
    # "hashes.json lists none of its files": every kept file is read back
    split_artifact(tmp_path, 0, split=[DILLON], left_out={QUARTERS[1]: ('t0-2m',)})
    _c, out = run(tmp_path, live)
    live.publish(out, hashes=False)
    before = live_tiles(live)['quartered'][DILLON]
    live.requests.clear()
    artifact(tmp_path, 0, [OTHER])
    changed, out2 = run(tmp_path, live, 'site2')
    assert changed is True
    want = quarter_files(DILLON, skip={(QUARTERS[1], 't0-2m')})
    assert set(want) <= set(live.requests)
    assert f'cells/{DILLON}/{QUARTERS[1]}/t0-2m.json.gz' not in live.requests
    r = tiles_of(out2)
    assert r['quartered'][DILLON] == before and list(r['cells']) == [OTHER]


def test_a_tampered_live_quarter_fails_the_deploy(live, tmp_path):
    split_artifact(tmp_path, 0, split=[DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    live.files[f'cells/{DILLON}/{QUARTERS[2]}/t1-4.json.gz'] = b'x' * 10
    artifact(tmp_path, 0, [OTHER])
    with pytest.raises(RuntimeError, match='bytes, not the'):
        run(tmp_path, live, 'site2')


def test_a_live_quarter_from_another_quarter_fails_the_deploy(live, tmp_path):
    split_artifact(tmp_path, 0, split=[DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    # t1-4 files are always read back (the overview is built from them), so the swap is read and checked
    a, b = (f'cells/{DILLON}/{q}/t1-4.json.gz' for q in QUARTERS[:2])
    live.files[a] = live.files[b]  # and its size in the manifest: a swap only the quarter check sees
    edit_live_tile(live, TILE, lambda d: d['quartered'][DILLON]['quarters'][QUARTERS[0]]['layers']['t1-4'].update(bytes=len(live.files[b])))
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
    r = tiles_of(out2)
    assert r['cells'] == {} and list(r['quartered']) == [DILLON]
    assert all((out2 / p).exists() for p in quarter_files(DILLON))
    assert not any((out2 / f'cells/{DILLON}/{l}.json.gz').exists() for l in site.LAYERS)
    live.publish(out2)
    artifact(tmp_path, 0, [DILLON])
    _c, out3 = run(tmp_path, live, 'site3')
    r = tiles_of(out3)
    assert list(r['cells']) == [DILLON] and r['quartered'] == {}
    assert not (out3 / f'cells/{DILLON}/{QUARTERS[0]}').exists()


def test_a_left_out_live_split_cell_fails_too(live, tmp_path):
    split_artifact(tmp_path, 0, split=[DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    # a live tile listing a split cell no area covers: the new site would drop it
    stray_cell = '152_-432'
    def add(d):
        stray = dict(d['quartered'][DILLON])
        stray['quarters'] = dict(zip(grid.quarters(stray_cell), stray['quarters'].values()))
        d['quartered'][stray_cell] = stray
    edit_live_tile(live, TILE, add)
    import sitefake as sf
    # the areas cover every cell but the stray one
    one_box = {'south': 39.51, 'west': -106.24, 'north': 39.74, 'east': -106.01}
    artifact(tmp_path, 0, [DILLON])  # 1 cell in the new site, 2 in the live one
    with pytest.raises(RuntimeError, match='leave out 1 built cells'):
        sf.run(tmp_path, live, name='site2', areas=[{'id': 'dillon', 'name': 'Dillon', 'boxes': [one_box]}])


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


# Requirement: Each tile has an overview of its built cells' tier 4 ("A split cell's tier 4")
def test_the_overview_holds_a_split_cells_quarters_in_order(live, tmp_path):
    counts = dict(zip(QUARTERS, (1, 2, 0, 4)))
    split_artifact(tmp_path, 0, split=[DILLON], t4=counts)
    _c, out = run(tmp_path, live)
    got = overview_doc(out)['tiers']['4']['30']
    assert len(got) == 7
    want = []
    for q in QUARTERS:
        f = out / f'cells/{DILLON}/{q}/t1-4.json.gz'
        if f.exists():  # the quarter of 0 tier-4 polygons is empty: no file
            want += cellfile.loads(f.read_bytes())['tiers']['4']['30']
    assert got == want
    assert got[0] == want[0] and got[-4:] == cellfile.loads(
        (out / f'cells/{DILLON}/{QUARTERS[3]}/t1-4.json.gz').read_bytes())['tiers']['4']['30']


# Requirement: The site carries its sources notice ("A split cell's projects")
def test_the_license_lists_a_split_cells_projects(live, tmp_path):
    split_artifact(tmp_path, 0, split=[DILLON], projects=['CO_Split_A_2017', 'CO_Split_B_2020'])
    _c, out = run(tmp_path, live)
    text = (out / 'LICENSE.txt').read_text()
    assert '- CO_Split_A_2017' in text and '- CO_Split_B_2020' in text


# Requirement: The site holds at most 19,000 files ("Counting a split cell's files")
def test_the_file_count_counts_a_split_cells_files(live, tmp_path, monkeypatch):
    split_artifact(tmp_path, 0, whole=[OTHER], split=[DILLON], left_out={QUARTERS[0]: ('t0-2m',)})
    # 4 fixed files + 12 tile indexes + 2 tile overviews (DILLON's and OTHER's tiles) + 3 whole + 11 quarter files = 32
    monkeypatch.setattr(site, 'MAX_SITE_FILES', 31)
    with pytest.raises(RuntimeError, match='32 files'):
        run(tmp_path, live)
    monkeypatch.setattr(site, 'MAX_SITE_FILES', 32)
    _c, out = run(tmp_path, live, 'site2')
    assert len(deployed(out) | {'hashes.json'}) == 32


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
def test_a_deploy_over_a_live_manifest_without_quartered(tmp_path, monkeypatch):
    # a version 1 site from before split cells: its regions have no `quartered`
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    live = sitefake.v1_site([DILLON])
    m = json.loads(live.files['manifest.json'])
    del m['regions'][0]['quartered']
    live.files['manifest.json'] = json.dumps(m).encode()
    live.set_hashes()
    split_artifact(tmp_path, 0, split=[OTHER])
    changed, out2 = run(tmp_path, live, 'site2')
    assert changed is True
    r = tiles_of(out2)
    assert list(r['cells']) == [DILLON] and list(r['quartered']) == [OTHER]


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
    tiles = [f'tiles/{t}/index.json' for t in live_tile_docs(live)]
    assert sorted(live.requests) == sorted(['manifest.json', 'hashes.json', f'cells/{DILLON}/t1-4.json.gz'] + tiles)
    kept = json.loads((state_of(out2) / 'kept.json').read_text())
    hashes = json.loads(live.files['hashes.json'])['files']
    assert kept == {f'/cells/{DILLON}/{l}.json.gz': {'hash': hashes[f'/cells/{DILLON}/{l}.json.gz'],
                                                       'bytes': len(live.files[f'cells/{DILLON}/{l}.json.gz'])}
                    for l in ('t0-3m', 't0-2m')}
    assert not (out2 / f'cells/{DILLON}/t0-3m.json.gz').exists()
    assert (out2 / f'cells/{DILLON}/t1-4.json.gz').exists()
    manifest = json.loads((out2 / 'manifest.json').read_text())
    assert deployed(out2) == set(site.site_files(tile_docs(out2))) - {'hashes.json'}
    # the read-back t1-4 must hash to its listed entry: the Node step checks it against this
    checks = json.loads((state_of(out2) / 'checks.json').read_text())
    assert checks['readback'] == {f'/cells/{DILLON}/t1-4.json.gz': hashes[f'/cells/{DILLON}/t1-4.json.gz']}
    live_names = {c['name']: c['hash'] for c in checks['live']}
    assert live_names['manifest.json'] == hashes['/manifest.json'] and len(live_names) == 13
    assert (state_of(out2) / 'live' / 'manifest.json').read_bytes() == live.files['manifest.json']


# Requirement: A deploy reads back only what it needs ("The first run after this change")
def test_the_first_run_after_this_change_reads_back_everything(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out, hashes=False)
    live.requests.clear()
    artifact(tmp_path, 0, [OTHER])
    _c, out2 = run(tmp_path, live, 'site2')
    assert set(f'cells/{DILLON}/{l}.json.gz' for l in site.LAYERS) <= set(live.requests)
    assert json.loads((state_of(out2) / 'kept.json').read_text()) == {}
    checks = json.loads((state_of(out2) / 'checks.json').read_text())
    assert checks['live'] == [] and set(checks['readback'].values()) == {None}
    assert all((out2 / f'cells/{DILLON}/{l}.json.gz').exists() for l in site.LAYERS)


# Requirement: A deploy reads back only what it needs (no live manifest: no hashes.json read)
def test_with_no_live_manifest_no_hashes_file_is_read(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    run(tmp_path, live)
    assert 'hashes.json' not in live.requests
    out = tmp_path / 'site'
    assert json.loads((state_of(out) / 'checks.json').read_text()) == {'live': [], 'readback': {}}
    assert not (state_of(out) / 'live').exists()


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
                         areas=AREAS, site_url='https://slope.test', get=get, log=lambda *_: None)


# Requirement: The live hashes belong to the live manifest ("A path that is no longer kept")
def test_entries_for_paths_no_longer_kept_are_ignored(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    split_artifact(tmp_path, 0, split=[DILLON])
    _c, out2 = run(tmp_path, live, 'site2')
    kept = json.loads((state_of(out2) / 'kept.json').read_text())
    assert kept == {}
    assert not any(p.startswith(f'cells/{DILLON}/t') for p in deployed(out2))


# Requirement: A deploy reads back only what it needs (a kept path the hashes file doesn't list)
def test_a_kept_file_the_hashes_file_does_not_list_is_read_back(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    live.publish(out)
    h = json.loads(live.files['hashes.json'])
    del h['files'][f'/cells/{DILLON}/t0-3m.json.gz']
    live.files['hashes.json'] = json.dumps(h).encode()
    live.requests.clear()
    artifact(tmp_path, 0, [OTHER])
    _c, out2 = run(tmp_path, live, 'site2')
    assert f'cells/{DILLON}/t0-3m.json.gz' in live.requests
    assert (out2 / f'cells/{DILLON}/t0-3m.json.gz').exists()
    checks = json.loads((state_of(out2) / 'checks.json').read_text())
    assert checks['readback'][f'/cells/{DILLON}/t0-3m.json.gz'] is None


# Requirement: Deploying adds to the live site (`_headers` goes beside the manifest, not in the folder)
def test_headers_go_beside_the_deployment_not_in_its_folder(live, tmp_path):
    artifact(tmp_path, 0, [DILLON])
    _c, out = run(tmp_path, live)
    assert not (out / '_headers').exists() and not (out / 'hashes.json').exists()
    assert (state_of(out) / '_headers').read_text() == site.HEADERS


# Requirement: The site holds at most 19,000 files ("Counting the hashes file")
def test_the_file_count_counts_the_hashes_file_but_not_headers(live, tmp_path, monkeypatch):
    artifact(tmp_path, 0, [DILLON])
    # manifest, hashes, 404, LICENSE, 3 layers, the tile's overview, 12 tile indexes = 20; _headers isn't named
    monkeypatch.setattr(site, 'MAX_SITE_FILES', 20)
    _c, out = run(tmp_path, live)
    files = site.site_files(tile_docs(out))
    assert 'hashes.json' in files and '_headers' not in files
    monkeypatch.setattr(site, 'MAX_SITE_FILES', 19)
    with pytest.raises(RuntimeError, match='20 files'):
        run(tmp_path, live, 'site2')


def test_main_takes_the_state_folder(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(publish, 'assemble', lambda *a, **k: seen.update(k))
    monkeypatch.setenv('PLAN_JOBS', '[]')
    monkeypatch.setenv('PLAN_HAD_MANIFEST', 'false')
    monkeypatch.setenv('PLAN_MANIFEST_VERSION', 'none')
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
    assert sorted(first) == sorted('/' + p for p in site.site_files(live_tile_docs(live)) if p != 'hashes.json')
    artifact(tmp_path, 0, [OTHER])
    live.requests.clear()
    _c, out2 = run(tmp_path, live, 'site2')
    tiles = [f'tiles/{t}/index.json' for t in live_tile_docs(live)]
    assert sorted(live.requests) == sorted(['manifest.json', 'hashes.json', f'cells/{DILLON}/t1-4.json.gz'] + tiles)
    r = node_hash(out2)
    assert r.returncode == 0, r.stderr
    deployment = json.loads((state_of(out2) / 'deployment.json').read_text())
    for l in ('t0-3m', 't0-2m', 't1-4'):
        p = f'/cells/{DILLON}/{l}.json.gz'
        assert deployment[p] == first[p]
    publish_for_real(live, out2)
    assert set(live_tiles(live)['cells']) == {DILLON, OTHER}
    assert set(live.files) == set(site.site_files(live_tile_docs(live))) | {'_headers'}


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
    assert {f'/cells/{c}/{l}.json.gz' for c in (DILLON, OTHER) for l in site.LAYERS} <= set(files)


# deploy/check_cell.py: the cell-file checks for a file the upload step reads back (bytes on stdin).
# Requirement: Files read back from the live site are checked; A deploy uploads only the files Cloudflare lacks
def check_cell_cli(path, data):
    import subprocess
    import sys
    script = pathlib.Path(__file__).resolve().parent.parent / 'deploy' / 'check_cell.py'
    return subprocess.run([sys.executable, '-I', str(script), path], input=data, capture_output=True)


def test_the_read_back_checker_accepts_a_cell_file_of_its_path():
    data = cellfile.dumps(cellfile.build(DILLON, 't0-3m', {}))
    assert check_cell_cli(f'/cells/{DILLON}/t0-3m.json.gz', data).returncode == 0
    q = cellfile.dumps(cellfile.build(DILLON, 't1-4', {}, quarter=QUARTERS[1]))
    assert check_cell_cli(f'/cells/{DILLON}/{QUARTERS[1]}/t1-4.json.gz', q).returncode == 0


@pytest.mark.parametrize('path, data', [
    (f'/cells/{DILLON}/t0-3m.json.gz', b'not gzip'),
    (f'/cells/{DILLON}/t0-3m.json.gz', cellfile.dumps(cellfile.build(OTHER, 't0-3m', {}))),
    (f'/cells/{DILLON}/t1-4.json.gz', cellfile.dumps(cellfile.build(DILLON, 't0-3m', {}))),
    (f'/cells/{DILLON}/{QUARTERS[1]}/t1-4.json.gz', cellfile.dumps(cellfile.build(DILLON, 't1-4', {}, quarter=QUARTERS[0]))),
    ('/manifest.json', b'{}'), (f'/../{DILLON}/t0-3m.json.gz', b''), (f'/cells/{DILLON}/x.json.gz', b''),
    (f'/cells/{DILLON}/999_0/t1-4.json.gz', b''),
])
def test_the_read_back_checker_refuses_anything_else(path, data):
    r = check_cell_cli(path, data)
    assert r.returncode != 0 and r.stdout == b''
