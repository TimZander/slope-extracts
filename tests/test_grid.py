"""The coordinate grid (change grid-v2): areas, cells stored once, 2-degree tiles, manifest version 2,
empty layers, and the first run that moves a version 1 site onto the grid."""
import datetime
import json
import re
import pathlib

import pytest

from slope_extracts import cellfile, grid, overview, publish, site
from sitefake import (AREAS, COLORADO, DILLON, EMPTY, LEFT_OUT, NEIGHBOUR, OTHER, URL, FakeSite, artifact, deployed, entry,
                      fake_cell, planned_jobs, run, state_of, v1_site)

TODAY = datetime.date(2026, 11, 24)


@pytest.fixture
def live(monkeypatch):
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    return FakeSite()


def box(rows, cols):
    """A box covering exactly rows[0]..rows[1] and cols[0]..cols[1] (inclusive), inset from the lines."""
    return {'south': rows[0] / 4 + 0.01, 'north': (rows[1] + 1) / 4 - 0.01,
            'west': cols[0] / 4 + 0.01, 'east': (cols[1] + 1) / 4 - 0.01}


# --- the areas list -----------------------------------------------------------------------------
# Requirement: The areas list

def test_colorados_coverage():
    cov = site.area_coverage(COLORADO)
    assert len(cov) == 464 and cov[0] == '148_-437' and cov[-1] == '163_-409'


def test_an_area_of_two_boxes_covers_each_cell_once():
    a = {'id': 'two', 'name': 'Two', 'source': '3dep', 'boxes': [box((0, 4), (0, 7)), box((4, 8), (2, 7))]}
    cov = site.area_coverage(a)
    assert len(cov) == 64 and len(set(cov)) == 64
    assert cov == sorted(cov, key=grid.compare_key)


def test_an_edge_on_a_cell_line_covers_no_cell_beyond():
    a = {'id': 'edge', 'name': 'Edge', 'source': '3dep', 'boxes': [{'south': 0.0, 'west': 0.0, 'north': 1.0, 'east': 0.5}]}
    assert site.area_coverage(a) == [f'{r}_{c}' for r in range(4) for c in range(2)]


@pytest.mark.parametrize('bad', [
    [], [dict(COLORADO, boxes=[{'south': 41, 'west': -109, 'north': 37, 'east': -102}])],
    [dict(COLORADO, id='Colorado')], [COLORADO, COLORADO], [dict(COLORADO, boxes=[])],
    [{k: v for k, v in COLORADO.items() if k != 'boxes'}], [dict(COLORADO, bounds=COLORADO['boxes'][0])],
    [dict(COLORADO, name=' ')], [dict(COLORADO, boxes=[{'south': 1, 'west': 0, 'north': 2}])],
])
def test_an_invalid_areas_list_is_refused(bad):
    with pytest.raises(ValueError):
        site.validate_areas(bad)


def test_the_repositorys_areas_list_is_valid():
    areas = site.load_areas()
    assert areas[0]['id'] == 'colorado' and len(site.area_coverage(areas[0])) == 464


# Requirement: A cell is built and stored once, whatever covers it
def test_a_border_cell_is_planned_once():
    utah = {'id': 'utah', 'name': 'Utah', 'source': '3dep', 'boxes': [{'south': 37.01, 'west': -114.04, 'north': 41.99, 'east': -109.06}]}
    cov = site.site_coverage([COLORADO, utah])
    assert cov.count('152_-437') == 1
    jobs = site.plan([COLORADO, utah], None, 1, 10_000, 3, today=TODAY)
    planned = [c for j in jobs for c in j]
    assert planned.count('152_-437') == 1 and len(planned) == len(set(planned)) == len(cov)
    # areas in list order: Colorado's cells first
    assert planned[:464] == site.area_coverage(COLORADO)


def test_a_border_cell_is_stored_once(live, tmp_path):
    utah = {'id': 'utah', 'name': 'Utah', 'source': '3dep', 'boxes': [{'south': 37.01, 'west': -114.04, 'north': 41.99, 'east': -109.06}]}
    artifact(tmp_path, ['152_-437'])
    _c, out = run(tmp_path, live, areas=[COLORADO, utah])
    files = deployed(out)
    assert {p for p in files if '152_-437' in p} == {f'cells/152_-437/{l}.json.gz' for l in site.LAYERS}
    tile = json.loads((out / 'tiles/19_-55/index.json').read_text())
    assert list(tile['cells']) == ['152_-437']


# --- tiles and masks ---------------------------------------------------------------------------
# Requirement: Cells are indexed by 2-degree tiles; A tile's entry counts and masks its cells

def test_a_cells_tile():
    assert grid.tile_of(DILLON) == '19_-54'
    cells = grid.tile_cells('19_-54')
    assert len(cells) == 64 and cells[0] == '152_-432' and cells[-1] == '159_-425'
    assert grid.tile_bounds('19_-54') == (38.0, -108.0, 40.0, -106.0)


def test_one_built_cells_mask():
    assert grid.mask(['152_-432', '158_-425']) == '0080000000000001'
    assert grid.mask([]) == '0' * 16
    assert grid.mask(grid.tile_cells('19_-54')) == 'f' * 16
    with pytest.raises(ValueError):
        grid.mask(['152_-432', '160_-425'])  # two tiles


def test_a_tile_index_and_its_manifest_entry(live, tmp_path):
    artifact(tmp_path, [DILLON], split=['152_-432'])
    _c, out = run(tmp_path, live)
    idx_bytes = (out / 'tiles/19_-54/index.json').read_bytes()
    idx = json.loads(idx_bytes)
    assert list(idx) == ['format', 'version', 'tile', 'coverage', 'cells', 'quartered']
    assert (idx['format'], idx['version'], idx['tile']) == ('slope-tile', 1, '19_-54')
    assert idx['coverage'] == [c for c in grid.tile_cells('19_-54') if c in set(site.area_coverage(COLORADO))]
    assert list(idx['cells']) == [DILLON] and list(idx['quartered']) == ['152_-432']
    assert set(idx['cells'][DILLON]) == {'recipe', 'built', 'sources', 'projects', 'layers'}
    assert set(idx['quartered']['152_-432']) == {'recipe', 'built', 'sources', 'projects', 'quarters'}
    m = json.loads((out / 'manifest.json').read_text())
    t = m['tiles']['19_-54']
    assert list(t) == ['covered', 'built', 'coveredMask', 'builtMask', 'indexBytes', 'overview']
    assert t['covered'] == len(idx['coverage']) and t['built'] == 2
    assert t['builtMask'] == '0080000000000001' and t['coveredMask'] == grid.mask(idx['coverage'])
    assert t['indexBytes'] == len(idx_bytes)
    ov = (out / 'tiles/19_-54/overview.json.gz').read_bytes()
    assert t['overview']['bytes'] == len(ov)


def test_a_tile_with_nothing_built_has_an_index_but_no_overview(live, tmp_path):
    artifact(tmp_path, [DILLON])
    _c, out = run(tmp_path, live)
    m = json.loads((out / 'manifest.json').read_text())
    assert len(m['tiles']) == 12
    assert (out / 'tiles/18_-55/index.json').exists() and not (out / 'tiles/18_-55/overview.json.gz').exists()
    assert 'overview' not in m['tiles']['18_-55'] and m['tiles']['18_-55']['built'] == 0
    assert not (out / 'tiles/20_-60').exists() and '20_-60' not in m['tiles']


# --- the manifest ------------------------------------------------------------------------------
# Requirement: The manifest lists tiles and areas

def test_colorados_manifest(live, tmp_path):
    artifact(tmp_path, [DILLON, OTHER])
    _c, out = run(tmp_path, live)
    m = json.loads((out / 'manifest.json').read_text())
    assert list(m) == ['format', 'version', 'attribution', 'cellFormat', 'layers', 'tiles', 'areas']
    assert (m['format'], m['version']) == ('slope-extract', 2)
    assert m['cellFormat'] == {'format': 'slope-cell', 'version': 1} and m['layers'] == list(site.LAYERS)
    assert [list(a) for a in m['areas']] == [['id', 'name', 'boxes', 'tiles']]
    a = m['areas'][0]
    assert a['id'] == 'colorado' and a['boxes'] == COLORADO['boxes'] and len(a['tiles']) == 12
    assert a['tiles'] == sorted(a['tiles'], key=grid.compare_key)
    assert sum(t['built'] for t in m['tiles'].values()) == 2
    assert list(m['tiles']) == sorted(m['tiles'], key=grid.compare_key)


def test_areas_in_their_lists_order(live, tmp_path):
    utah = {'id': 'utah', 'name': 'Utah', 'source': '3dep', 'boxes': [{'south': 37.01, 'west': -114.04, 'north': 41.99, 'east': -109.06}]}
    artifact(tmp_path, [DILLON])
    _c, out = run(tmp_path, live, areas=[COLORADO, utah])
    assert [a['id'] for a in json.loads((out / 'manifest.json').read_text())['areas']] == ['colorado', 'utah']


def test_no_region_paths_or_version_1_files(live, tmp_path):
    artifact(tmp_path, [DILLON])
    _c, out = run(tmp_path, live)
    assert not any(p.startswith('colorado/') for p in deployed(out))


# --- tile overviews ----------------------------------------------------------------------------
# Requirement: Each tile has an overview of its built cells' tier 4

def overview_of(out, tile='19_-54'):
    import gzip
    return json.loads(gzip.decompress((out / f'tiles/{tile}/overview.json.gz').read_bytes()))


def test_a_tiles_overview_holds_its_cells_in_order(live, tmp_path):
    root = artifact(tmp_path, [])
    fake_cell(root, DILLON, t4=5)
    fake_cell(root, NEIGHBOUR, t4=3)
    (root / 'jobs.txt').write_text(f'{DILLON} {NEIGHBOUR}')
    _c, out = run(tmp_path, live)
    doc = overview_of(out)
    assert list(doc) == ['format', 'version', 'tile', 'tiers']
    assert (doc['format'], doc['version'], doc['tile']) == ('slope-overview', 2, '19_-54')
    got = doc['tiers']['4']['30']
    first = cellfile.loads((out / f'cells/{NEIGHBOUR}/t1-4.json.gz').read_bytes())['tiers']['4']['30']
    second = cellfile.loads((out / f'cells/{DILLON}/t1-4.json.gz').read_bytes())['tiers']['4']['30']
    # NEIGHBOUR (column -426) comes before DILLON (column -425) in row then column order
    assert got == first + second and len(got) == 8


def test_only_empty_zoomed_out_layers_give_an_empty_overview(live, tmp_path):
    artifact(tmp_path, [DILLON], empty=('t1-4',))
    _c, out = run(tmp_path, live)
    assert overview_of(out)['tiers'] == {'4': {'30': []}}
    assert json.loads((out / 'manifest.json').read_text())['tiles']['19_-54']['overview']['polygons'] == 0


def test_a_split_cells_tier_4_in_quarter_order(live, tmp_path):
    from sitefake import fake_split_cell
    root = artifact(tmp_path, [])
    qs = grid.quarters(DILLON)
    fake_split_cell(root, DILLON, t4=dict(zip(qs, (1, 2, 0, 4))), empty={qs[2]: ('t1-4',)})
    (root / 'jobs.txt').write_text(DILLON)
    _c, out = run(tmp_path, live)
    got = overview_of(out)['tiers']['4']['30']
    assert len(got) == 7


def test_the_overview_builds_to_the_same_bytes():
    doc = overview.build_tile('19_-54', [])
    assert overview.dumps(doc) == overview.dumps(doc)


# --- empty layers ------------------------------------------------------------------------------
# Requirement: A layer with no polygons has no file

def test_a_flat_cells_layers_have_no_files(live, tmp_path):
    artifact(tmp_path, [DILLON], empty=site.LAYERS)
    _c, out = run(tmp_path, live)
    idx = json.loads((out / 'tiles/19_-54/index.json').read_text())
    assert idx['cells'][DILLON]['layers'] == {l: EMPTY for l in site.LAYERS}
    assert not any(p.startswith(f'cells/{DILLON}/') for p in deployed(out))


def test_an_empty_layers_file_there_anyway_fails(tmp_path):
    root = artifact(tmp_path, [DILLON], empty=('t1-4',))
    (root / DILLON / 't1-4.json.gz').write_bytes(cellfile.dumps(cellfile.build(DILLON, 't1-4', {4: {30: []}})))
    with pytest.raises(RuntimeError, match='not exactly'):
        run(tmp_path, FakeSite())


def test_a_file_with_no_polygons_is_invalid(tmp_path):
    root = artifact(tmp_path, [DILLON])
    doc = cellfile.build(DILLON, 't0-3m', {0: {30: []}})
    data = cellfile.dumps(doc)
    (root / DILLON / 't0-3m.json.gz').write_bytes(data)
    e = json.loads((root / DILLON / 'entry.json').read_text())
    e['layers']['t0-3m'] = {'bytes': len(data), 'tiers': cellfile.stats(doc)}
    (root / DILLON / 'entry.json').write_text(json.dumps(e))
    with pytest.raises(RuntimeError, match='entry.json is not valid'):
        run(tmp_path, FakeSite())


@pytest.mark.parametrize('layer, value, ok', [
    ('t0-2m', LEFT_OUT, True), ('t1-4', EMPTY, True), ('t0-3m', EMPTY, True),
    ('t1-4', LEFT_OUT, False), ('t0-3m', {'bytes': 0, 'tiers': {'0': {'polygons': 3, 'points': 9}}}, False),
    ('t0-2m', {'bytes': 0, 'tiers': {'1': {'polygons': 0, 'points': 0}}}, False),
])
def test_bytes_0_is_the_marker_or_empty_and_nothing_else(layer, value, ok):
    e = dict(entry(DILLON))
    e['layers'] = dict(e['layers'], **{layer: value})
    if ok:
        site.validate_entry(e, DILLON)
    else:
        with pytest.raises(ValueError):
            site.validate_entry(e, DILLON)


# --- the live manifest and its tile indexes ----------------------------------------------------
# Requirement: The live manifest is checked, with its tile indexes

def published(tmp_path, cells=(DILLON,), **kw):
    live = FakeSite()
    artifact(tmp_path, list(cells), **kw)
    _c, out = run(tmp_path, live, name='first')
    live.publish(out)
    return live


def fetch(live, **kw):
    return publish.fetch_live(URL, live.get, **kw)


def test_a_v2_live_site_is_read_with_its_tiles(tmp_path):
    live = published(tmp_path)
    got = fetch(live)
    assert got['version'] == 2 and set(got['cells']) == {DILLON}
    assert 'tiles/19_-54/index.json' in live.requests and len(got['tiles']) == 12


def tamper_tile(live, fn, tile='19_-54', fix_size=True):
    m = json.loads(live.files['manifest.json'])
    doc = json.loads(live.files[f'tiles/{tile}/index.json'])
    fn(doc, m['tiles'][tile])
    body = (json.dumps(doc, indent=1) + '\n').encode()
    live.files[f'tiles/{tile}/index.json'] = body
    if fix_size:
        m['tiles'][tile]['indexBytes'] = len(body)
    live.files['manifest.json'] = (json.dumps(m, indent=1) + '\n').encode()


@pytest.mark.parametrize('bad', ['404', 'size', 'wrong tile', 'built outside coverage', 'mask', 'count',
                                 'both', 'stray key', 'empty with counts'])
def test_an_invalid_live_tile_index_fails(tmp_path, bad):
    live = published(tmp_path)
    if bad == '404':
        del live.files['tiles/19_-54/index.json']
    elif bad == 'size':
        tamper_tile(live, lambda d, t: d.update(tile='19_-54'), fix_size=False)
        m = json.loads(live.files['manifest.json'])
        m['tiles']['19_-54']['indexBytes'] += 1
        live.files['manifest.json'] = json.dumps(m).encode()
    elif bad == 'wrong tile':
        tamper_tile(live, lambda d, t: d['coverage'].append('150_-431'))
    elif bad == 'built outside coverage':
        tamper_tile(live, lambda d, t: d['coverage'].remove(DILLON))
    elif bad == 'mask':
        tamper_tile(live, lambda d, t: t.update(coveredMask='0' * 16))
    elif bad == 'count':
        tamper_tile(live, lambda d, t: t.update(built=2))
    elif bad == 'both':
        tamper_tile(live, lambda d, t: d['quartered'].update({DILLON: d['cells'][DILLON]}))
    elif bad == 'stray key':
        tamper_tile(live, lambda d, t: d.update(extra=1))
    elif bad == 'empty with counts':
        tamper_tile(live, lambda d, t: d['cells'][DILLON]['layers'].update({'t1-4': {'bytes': 0, 'tiers': {'4': {'polygons': 1, 'points': 3}}}}))
    with pytest.raises(RuntimeError, match='the live manifest is not valid'):
        fetch(live)


def test_a_tiles_overview_entry_is_used_for_nothing(tmp_path):
    live = published(tmp_path)
    m = json.loads(live.files['manifest.json'])
    m['tiles']['19_-54']['overview'] = 'anything'
    live.files['manifest.json'] = json.dumps(m).encode()
    assert set(fetch(live)['cells']) == {DILLON}


def test_the_plan_and_deploy_read_different_versions(tmp_path):
    live = published(tmp_path)
    artifact(tmp_path, [OTHER])
    with pytest.raises(RuntimeError, match='version'):
        run(tmp_path, live, name='second', version=1)


def test_a_second_run_reads_back_only_the_t1_4_and_keeps_the_rest_by_hash(tmp_path):
    live = published(tmp_path)
    live.requests.clear()
    artifact(tmp_path, [NEIGHBOUR])
    _c, out = run(tmp_path, live, name='second')
    read = [p for p in live.requests if not p.startswith('tiles/') or p == 'tiles/19_-54/index.json']
    assert sorted(set(read) - {'manifest.json', 'hashes.json', 'tiles/19_-54/index.json'}) == [f'cells/{DILLON}/t1-4.json.gz']
    kept = json.loads((state_of(out) / 'kept.json').read_text())
    assert set(kept) == {f'/cells/{DILLON}/t0-3m.json.gz', f'/cells/{DILLON}/t0-2m.json.gz'}
    checks = json.loads((state_of(out) / 'checks.json').read_text())
    names = {c['name'] for c in checks['live']}
    assert 'manifest.json' in names and 'tiles/19_-54/index.json' in names
    manifest = json.loads((out / 'manifest.json').read_text())
    assert manifest['tiles']['19_-54']['built'] == 2


# --- the plan ----------------------------------------------------------------------------------
# Requirement: A run builds missing and stale cells, at most 48

def live_with(cells):
    """A version 2 live view of {cell: entry}, as fetch_live gives it."""
    return {'version': 2, 'cells': {c: site.manifest_entry(e) for c, e in cells.items()}}


def only(cells):
    return [{'id': 'x', 'name': 'X', 'source': '3dep', 'boxes': [box((grid.parse_cell(c)[0],) * 2, (grid.parse_cell(c)[1],) * 2) for c in cells]}]


def test_plan_builds_missing_and_stale_cells_only():
    third = '158_-423'
    jobs = site.plan(only([DILLON, OTHER, third]), live_with({DILLON: entry(DILLON), OTHER: entry(OTHER, recipe=0)}), 1, 48, 3, today=TODAY)
    assert jobs == [[OTHER, third]]


def test_plan_jobs_are_plain_cells_in_jobs_of_three():
    jobs = site.plan(AREAS, None, 1, 7, 3, today=TODAY)
    assert [len(j) for j in jobs] == [3, 3, 1] and jobs[0][0] == '148_-437'


def test_plan_rebuilds_a_whole_cell_left_out_but_not_a_flat_one():
    left = dict(entry(DILLON), layers=dict(entry(DILLON)['layers'], **{'t0-2m': dict(LEFT_OUT)}))
    flat = dict(entry(OTHER), layers={l: dict(EMPTY) for l in site.LAYERS})
    assert site.plan(only([DILLON, OTHER]), live_with({DILLON: left, OTHER: flat}), 1, 48, 3, today=TODAY) == [[DILLON]]


def test_plan_nothing_left_on_version_2():
    assert site.plan(only([DILLON]), live_with({DILLON: entry(DILLON)}), 1, 48, 3, today=TODAY) == []


def test_main_plan_says_which_manifest_it_read(monkeypatch, capsys, tmp_path):
    live = published(tmp_path)
    monkeypatch.setattr(publish, 'http_get', live.get)
    monkeypatch.setattr(publish, 'SITE_URL', URL)
    assert site.main_plan([]) == 0
    out = capsys.readouterr().out
    assert 'manifest_version=2' in out and 'had_manifest=true' in out
    jobs = json.loads(next(l for l in out.splitlines() if l.startswith('jobs='))[5:])
    assert all('/' not in item for j in jobs for item in j.split())


# --- the first run on the grid -----------------------------------------------------------------
# Requirements: A version 1 manifest still deploys; The first run moves the cells onto the grid

def test_the_first_run_moves_a_version_1_site_by_hash(tmp_path, monkeypatch):
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    live = v1_site([DILLON, '150_-431'])
    live.requests.clear()
    artifact(tmp_path, [OTHER])
    changed, out = run(tmp_path, live)
    assert changed is True
    reads = {p for p in live.requests if p.endswith('.json.gz')}
    assert reads == {f'colorado/{DILLON}/t1-4.json.gz', 'colorado/150_-431/t1-4.json.gz'}
    kept = json.loads((state_of(out) / 'kept.json').read_text())
    hashes = json.loads(live.files['hashes.json'])['files']
    assert kept[f'/cells/{DILLON}/t0-3m.json.gz'] == {'hash': hashes[f'/colorado/{DILLON}/t0-3m.json.gz'],
                                                      'bytes': len(live.files[f'colorado/{DILLON}/t0-3m.json.gz']),
                                                      'from': f'/colorado/{DILLON}/t0-3m.json.gz'}
    assert (out / f'cells/{DILLON}/t1-4.json.gz').read_bytes() == live.files[f'colorado/{DILLON}/t1-4.json.gz']
    files = deployed(out)
    assert not any(p.startswith('colorado/') for p in files)
    m = json.loads((out / 'manifest.json').read_text())
    assert m['version'] == 2 and sum(t['built'] for t in m['tiles'].values()) == 3
    checks = json.loads((state_of(out) / 'checks.json').read_text())
    assert {c['name'] for c in checks['live']} == {'manifest.json'}
    live.publish(out)
    assert set(fetch(live)['cells']) == {DILLON, OTHER, '150_-431'}


def test_nothing_to_build_on_the_first_run_still_deploys(tmp_path, monkeypatch):
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    live = v1_site([DILLON])
    (tmp_path / 'artifacts').mkdir()
    changed, out = run(tmp_path, live, jobs=[])
    assert changed is True
    assert json.loads((out / 'manifest.json').read_text())['version'] == 2
    assert f'cells/{DILLON}/t0-3m.json.gz' in deployed(out)


def test_nothing_built_on_version_2_deploys_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    live = published(tmp_path)
    import shutil
    shutil.rmtree(tmp_path / 'artifacts')
    (tmp_path / 'artifacts').mkdir()
    changed, out = run(tmp_path, live, name='second', jobs=[])
    assert changed is False and not out.exists()


def test_a_version_1_cell_no_area_covers_fails_the_deploy(tmp_path):
    live = v1_site([DILLON, '0_0'])
    m = json.loads(live.files['manifest.json'])
    m['regions'][0]['coverage'].append('0_0')
    live.files['manifest.json'] = json.dumps(m).encode()
    live.set_hashes()
    artifact(tmp_path, [DILLON])  # the new site holds DILLON only; the live one held 2
    with pytest.raises(RuntimeError, match='leave out'):
        run(tmp_path, live)


def test_a_version_1_left_out_layer_stays_left_out(tmp_path, monkeypatch):
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    live = v1_site([DILLON], left_out={DILLON: ('t0-2m',)})
    artifact(tmp_path, [OTHER])
    _c, out = run(tmp_path, live)
    idx = json.loads((out / 'tiles/19_-54/index.json').read_text())
    assert idx['cells'][DILLON]['layers']['t0-2m'] == LEFT_OUT
    live.publish(out)
    assert DILLON in [c for j in site.plan(only([DILLON]), fetch(live), 1, 48, 3, today=TODAY) for c in j]


def test_a_version_1_file_with_no_polygons_becomes_empty(tmp_path, monkeypatch):
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    live = v1_site([DILLON], empty={DILLON: ('t1-4',)})
    assert set(fetch(live)['cells']) == {DILLON}  # accepted as version 1
    artifact(tmp_path, [OTHER])
    _c, out = run(tmp_path, live)
    idx = json.loads((out / 'tiles/19_-54/index.json').read_text())
    assert idx['cells'][DILLON]['layers']['t1-4'] == EMPTY
    assert f'cells/{DILLON}/t1-4.json.gz' not in deployed(out)


def test_an_invalid_version_1_manifest_fails(tmp_path):
    live = v1_site([DILLON])
    m = json.loads(live.files['manifest.json'])
    m['regions'][0]['quartered'] = {DILLON: m['regions'][0]['cells'][DILLON]}
    live.files['manifest.json'] = json.dumps(m).encode()
    with pytest.raises(RuntimeError, match='the live manifest is not valid'):
        fetch(live)


def test_a_cell_in_two_version_1_regions_takes_the_first(tmp_path):
    live = v1_site([DILLON])
    m = json.loads(live.files['manifest.json'])
    second = dict(m['regions'][0], id='other')
    second['cells'] = {DILLON: dict(m['regions'][0]['cells'][DILLON], recipe=7)}
    m['regions'].append(second)
    live.files['manifest.json'] = json.dumps(m).encode()
    got = fetch(live)
    assert got['cells'][DILLON]['recipe'] == 1 and got['v1_paths'][DILLON] == 'colorado'


# --- headers -----------------------------------------------------------------------------------
# Requirement: The site sets its CORS and cache headers

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
    import re
    pattern = re.escape(rule).replace(r'\*', '.*')
    pattern = re.sub(r':[a-z]+', '[^/]+', pattern)
    return re.fullmatch(pattern, path) is not None


@pytest.mark.parametrize('path, age', [
    ('/cells/158_-425/t1-4.json.gz', 86400), ('/cells/158_-425/316_-850/t0-2m.json.gz', 86400),
    ('/tiles/19_-54/overview.json.gz', 3600), ('/tiles/19_-54/index.json', 300), ('/manifest.json', 300),
    ('/hashes.json', 300), ('/LICENSE.txt', 3600),
])
def test_each_path_matches_one_cache_rule(path, age):
    rules = {k: v for k, v in header_rules().items() if any(x.startswith('Cache-Control') for x in v)}
    hits = [k for k in rules if rule_matches(k, path)]
    assert len(hits) == 1, (path, hits)
    assert rules[hits[0]] == [f'Cache-Control: public, max-age={age}']


def test_no_rule_for_regions_is_left():
    assert ':region' not in site.HEADERS


# --- conformance review round 1: scenarios the port left untested --------------------------------

# Requirement: A run builds missing and stale cells ("The first run on the grid")
def test_plan_reads_a_version_1_sites_cells_as_built():
    live = v1_site([DILLON])
    got = fetch(live)
    assert got['version'] == 1
    assert site.plan(only([DILLON]), got, 1, 48, 3, today=TODAY) == []


# Requirement: A run builds missing and stale cells ("A split cell with a quarter's 2 m layer left out")
def test_plan_doesnt_rebuild_a_split_cell_with_a_quarter_left_out():
    e = {k: v for k, v in entry(DILLON).items() if k != 'layers'}
    e['quarters'] = {q: {'layers': dict(entry(DILLON)['layers'])} for q in grid.quarters(DILLON)}
    e['quarters'][grid.quarters(DILLON)[0]]['layers']['t0-2m'] = dict(LEFT_OUT)
    assert site.plan(only([DILLON]), live_with({DILLON: e}), 1, 48, 3, today=TODAY) == []


# Requirement: A run builds missing and stale cells ("The yearly refresh")
def test_plan_rebuilds_a_cell_older_than_the_refresh():
    old = live_with({DILLON: entry(DILLON, built='2025-11-01')})
    assert site.plan(only([DILLON]), old, 1, 48, 3, today=datetime.date(2026, 11, 23)) == [[DILLON]]
    assert site.plan(only([DILLON]), old, 1, 48, 3, today=datetime.date(2026, 6, 1)) == []


# Requirement: The manifest lists quartered cells apart from whole ones ("Quarters out of order",
# "A live entry with both forms", "The marker on a quarter's zoomed-out layer", "A quartered cell missing a quarter")
@pytest.mark.parametrize('bad', ['out of order', 'both forms', 'marker on t1-4', 'three quarters', 'quarter key'])
def test_an_invalid_live_quartered_entry_fails(tmp_path, bad):
    live = published(tmp_path, cells=(), split=[DILLON])
    qs = grid.quarters(DILLON)

    def edit(d, t):
        e = d['quartered'][DILLON]
        if bad == 'out of order':
            e['quarters'] = {qs[1]: e['quarters'][qs[1]], qs[0]: e['quarters'][qs[0]], qs[2]: e['quarters'][qs[2]], qs[3]: e['quarters'][qs[3]]}
        elif bad == 'both forms':
            e['layers'] = e['quarters'][qs[0]]['layers']
        elif bad == 'marker on t1-4':
            e['quarters'][qs[0]]['layers']['t1-4'] = dict(LEFT_OUT)
        elif bad == 'three quarters':
            del e['quarters'][qs[3]]
        elif bad == 'quarter key':
            e['quarters'][qs[0]]['href'] = 'x'
    tamper_tile(live, edit)
    with pytest.raises(RuntimeError, match='the live manifest is not valid'):
        fetch(live)


# Requirement: The live manifest is checked, with its tile indexes ("isn't of its form": an area's tiles)
@pytest.mark.parametrize('tiles', [['../x'], ['19_-54', '18_-55'], ['0_0']])
def test_an_areas_tiles_must_be_its_listed_tiles_in_order(tmp_path, tiles):
    live = published(tmp_path)
    m = json.loads(live.files['manifest.json'])
    m['areas'][0]['tiles'] = tiles
    live.files['manifest.json'] = json.dumps(m).encode()
    with pytest.raises(RuntimeError, match='the live manifest is not valid'):
        fetch(live)


# Requirement: Waits on Cloudflare are bounded (a read from the live site is retried at most twice)
def test_a_tile_index_read_is_retried_after_a_transient_error(tmp_path):
    live = published(tmp_path)
    failures = {'tiles/19_-54/index.json': 2}

    def flaky(url, limit):
        path = url.split('slope.test/', 1)[1]
        if failures.get(path, 0) > 0:
            failures[path] -= 1
            raise RuntimeError(f'{url} answered 503')
        return live.get(url, limit)
    assert set(publish.fetch_live(URL, flaky, retry_delay=0)['cells']) == {DILLON}
    failures['tiles/19_-54/index.json'] = 3
    with pytest.raises(RuntimeError, match='503'):
        publish.fetch_live(URL, flaky, retry_delay=0)


# --- attack tests: what a tampered live site or a bad id could try (task 3.3) ------------------
# Requirement: The live manifest is checked, with its tile indexes; Areas are hand-drawn boxes

def retile(live, old, new):
    m = json.loads(live.files['manifest.json'])
    m['tiles'] = {(new if t == old else t): e for t, e in m['tiles'].items()}
    for a in m['areas']:
        a['tiles'] = [new if t == old else t for t in a['tiles']]
    live.files['manifest.json'] = (json.dumps(m, indent=1) + '\n').encode()
    live.files[f'tiles/{new}/index.json'] = live.files[f'tiles/{old}/index.json']


@pytest.mark.parametrize('bad', ['../../etc', '19_-54/../../x', '19_-54\n', '019_-54', '19_-54 '])
def test_attack_a_live_tile_id_that_isnt_one_is_refused(tmp_path, bad):
    live = published(tmp_path)
    retile(live, '19_-54', bad)
    with pytest.raises(RuntimeError, match='the live manifest is not valid'):
        fetch(live)
    assert not any('..' in r or '\n' in r for r in live.requests)


@pytest.mark.parametrize('bad', ['../etc', 'colorado/..', 'colorado\n', 'Colorado'])
def test_attack_a_live_region_id_that_isnt_one_is_refused(bad):
    live = v1_site([DILLON])
    m = json.loads(live.files['manifest.json'])
    m['regions'][0]['id'] = bad
    live.files['manifest.json'] = json.dumps(m).encode()
    with pytest.raises(RuntimeError, match='the live manifest is not valid'):
        fetch(live)


@pytest.mark.parametrize('bad', ['colorado\n', '../x', 'a/b', ''])
def test_attack_an_area_id_that_isnt_one_is_refused(bad):
    with pytest.raises(ValueError):
        site.validate_areas([dict(COLORADO, id=bad)])


@pytest.mark.parametrize('bad', ['158_-425\n', '158_-425/..', ' 158_-425', '158_-425 '])
def test_attack_a_cell_or_tile_id_with_anything_more_is_refused(bad):
    with pytest.raises(ValueError):
        grid.parse_cell(bad)
    with pytest.raises(ValueError):
        grid.parse_tile(bad)


def test_attack_a_live_tile_index_naming_a_cell_outside_its_tile_is_refused(tmp_path):
    live = published(tmp_path)
    tamper_tile(live, lambda d, t: d['cells'].update({'../../etc': d['cells'][DILLON]}))
    with pytest.raises(RuntimeError, match='the live manifest is not valid'):
        fetch(live)


@pytest.mark.parametrize('value', ['3', 'None', '1; rm -rf /', '', None])
def test_attack_a_plan_manifest_version_that_isnt_one_is_refused(tmp_path, monkeypatch, value):
    monkeypatch.setenv('PLAN_HAD_MANIFEST', 'false')
    monkeypatch.setenv('PLAN_JOBS', json.dumps([DILLON]))
    if value is None:
        monkeypatch.delenv('PLAN_MANIFEST_VERSION', raising=False)
    else:
        monkeypatch.setenv('PLAN_MANIFEST_VERSION', value)
    artifact(tmp_path, [DILLON])
    assert publish.main(['assemble', '--artifacts', str(tmp_path / 'artifacts'), '--out', str(tmp_path / 'out'),
                         '--state', str(tmp_path / 'state')]) == 1
    assert not (tmp_path / 'out' / 'manifest.json').exists()


# Requirement: The site lists its files' hashes ("A deployed site")
def test_a_deployed_sites_hashes_list_exactly_its_files(live, tmp_path):
    import subprocess
    from test_site_publish import NODE_MODULES
    if not NODE_MODULES.exists():
        pytest.skip('run npm ci --ignore-scripts in deploy/ first')
    one = [{'id': 'dillon', 'name': 'Dillon', 'source': '3dep', 'boxes': [box((158, 158), (-425, -425))]}]
    artifact(tmp_path, [DILLON])
    _c, out = run(tmp_path, live, areas=one)
    script = pathlib.Path(__file__).resolve().parent.parent / 'deploy' / 'pages.mjs'
    r = subprocess.run(['node', str(script), 'hash', '--site', str(out), '--state', str(state_of(out))],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    files = json.loads((out / 'hashes.json').read_text())['files']
    assert sorted(files) == sorted([f'/cells/{DILLON}/t0-3m.json.gz', f'/cells/{DILLON}/t0-2m.json.gz',
                                    f'/cells/{DILLON}/t1-4.json.gz', '/tiles/19_-54/index.json',
                                    '/tiles/19_-54/overview.json.gz', '/manifest.json', '/404.html', '/LICENSE.txt'])
    assert all(publish.PAGES_HASH.fullmatch(h) for h in files.values())


# Requirement: Files read back from the live site are checked ("A v1 cell no area covers, while a run
# builds more")
def test_a_version_1_cell_no_area_covers_fails_even_when_more_are_built(tmp_path):
    live = v1_site([DILLON, '0_0'])
    m = json.loads(live.files['manifest.json'])
    m['regions'][0]['coverage'].append('0_0')
    live.files['manifest.json'] = json.dumps(m).encode()
    live.set_hashes()
    artifact(tmp_path, [OTHER, NEIGHBOUR])  # 3 cells after, 2 before; 0_0 is left out
    with pytest.raises(RuntimeError, match='leave out'):
        run(tmp_path, live)


# --- the check once deployed ----------------------------------------------------------------------
# Requirement: The deploy job checks the live site once deployed

class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


def deployed_live(tmp_path, cells=(DILLON, OTHER), split=()):
    """A live site with an earlier deployment, then this run's folder deployed (with its hashes.json)."""
    live = published(tmp_path, cells=(NEIGHBOUR,))
    before = dict(live.files)
    artifact(tmp_path, list(cells), split=split)
    _c, out = run(tmp_path, live, name='second')
    live.publish(out)
    (out / 'hashes.json').write_bytes(live.files['hashes.json'])
    return live, out, before


def verify(live, out, clock=None, get=None):
    clock = clock or Clock()
    return publish.verify_live(str(out), URL, get or live.get, sleep=clock.sleep, clock=lambda: clock.now)


def test_a_deployment_that_went_live_passes(tmp_path):
    live, out, _b = deployed_live(tmp_path, split=('158_-427',))
    live.requests.clear()
    verify(live, out)
    cells = [r for r in live.requests if r.startswith('cells/')]
    built_tiles = {t for t, e in json.loads(live.files['manifest.json'])['tiles'].items() if e['built']}
    assert len(cells) == len(built_tiles) == 2
    assert {grid.tile_of(r.split('/')[1]) for r in cells} == built_tiles
    assert 'hashes.json' in live.requests and all(f'tiles/{t}/index.json' in live.requests for t in built_tiles)


def test_a_deployment_slow_to_go_live_is_read_again(tmp_path):
    live, out, before = deployed_live(tmp_path)
    reads = {'n': 0}
    def get(url, limit):
        if url.endswith('/manifest.json'):
            reads['n'] += 1
            if reads['n'] <= 2:
                return 200, before['manifest.json']
        return live.get(url, limit)
    clock = Clock()
    verify(live, out, clock, get)
    assert reads['n'] >= 3 and len(clock.sleeps) == 2


def test_a_deployment_that_never_goes_live_fails(tmp_path):
    live, out, before = deployed_live(tmp_path)
    live.files['manifest.json'] = before['manifest.json']
    clock = Clock()
    with pytest.raises(RuntimeError, match='not the one deployed'):
        verify(live, out, clock)
    assert 590 <= clock.now <= 640


@pytest.mark.parametrize('broken', ['tile index', 'cell size', 'cell content', 'hashes', 'cell 404'])
def test_a_broken_live_file_fails_naming_it(tmp_path, broken):
    live, out, _b = deployed_live(tmp_path)
    live.requests.clear()
    verify(live, out)
    cell_file = next(r for r in live.requests if r.startswith('cells/') and grid.tile_of(r.split('/')[1]) == '19_-54')
    checked = cell_file.split('/')[1]
    donor = next(p for p in sorted(live.files) if p.startswith('cells/') and p.split('/')[1] != checked
                 and p.endswith(cell_file.rsplit('/', 1)[1]))
    if broken == 'tile index':
        live.files['tiles/19_-54/index.json'] += b' '
        name = 'tiles/19_-54/index.json'
    elif broken == 'cell size':
        live.files[cell_file] += b'\0'
        name = cell_file
    elif broken == 'cell content':
        # another cell's file, cut or padded to this one's size: right size, wrong cell
        other, n = live.files[donor], len(live.files[cell_file])
        live.files[cell_file] = (other + b'\0' * n)[:n]
        name = cell_file
    elif broken == 'hashes':
        live.files['hashes.json'] = live.files['hashes.json'].replace(b'"files"', b'"files" ')
        name = 'hashes.json'
    else:
        del live.files[cell_file]
        name = cell_file
    with pytest.raises(RuntimeError, match=re.escape(name)):
        verify(live, out)


def test_attack_a_live_site_answering_a_path_outside_the_site_is_never_asked(tmp_path):
    live, out, _b = deployed_live(tmp_path)
    live.requests.clear()
    verify(live, out)
    assert all(not r.startswith(('/', '.')) and '..' not in r for r in live.requests)
