import gzip
import json
import os

import numpy as np
import pytest
from rasterio.transform import from_origin

from slope_extracts import build_cell, cellfile, classes, dem, grid, sources


def test_cell_bounds_dillon():
    assert grid.cell_bounds('158_-425') == (39.5, -106.25, 39.75, -106.0)
    assert grid.cell_of(39.6, -106.1) == '158_-425'


@pytest.mark.parametrize('bad', ['158-425', '01_2', '1_+2', '', '158_-425 ', '999_0'])
def test_parse_cell_rejects(bad):
    with pytest.raises(ValueError):
        grid.parse_cell(bad)


def test_colorado_coverage_count():
    cells = grid.cells_in_bounds(37.01, -109.04, 40.99, -102.06)
    assert len(cells) == 16 * 29
    assert cells[0] == '148_-437' and cells[-1] == '163_-409'


def test_utm_zone_switches_at_108_west():
    assert grid.utm_epsg('158_-433') == 'EPSG:26912'
    assert grid.utm_epsg('158_-432') == 'EPSG:26913'


def test_ring_round_trip_and_determinism():
    pts = [(100, 200), (103, 199), (101, 190)]
    assert cellfile.decode_ring(cellfile.encode_ring(pts)) == pts
    doc = cellfile.build('158_-425', 't1-4', {1: {35: [[pts]]}})
    assert cellfile.dumps(doc) == cellfile.dumps(doc)
    assert cellfile.loads(cellfile.dumps(doc))['tiers'] == {'1': {'35': [[[100, 200, 3, -1, -2, -9]]]}}


def test_decode_ring_rejects_short():
    with pytest.raises(ValueError):
        cellfile.decode_ring([1, 2, 3, 4])


def test_classify_plane_of_known_slope():
    res, deg = 2.0, 41.0
    x = np.arange(200) * res
    z = np.tile(x * np.tan(np.radians(deg)), (150, 1)).astype('float32')
    cls = classes.classify(z, res, [30, 35, 40, 45], sieve=1)
    assert (cls[5:-5, 5:-5] == 3).all()  # 40-45


def test_classify_flat_and_nan_are_class_zero():
    z = np.full((50, 50), 100.0, dtype='float32')
    z[10:20, 10:20] = np.nan
    assert (classes.classify(z, 2.0, [30], sieve=1) == 0).all()


def test_block_mean_ignores_nan():
    z = np.array([[1, np.nan], [3, 5]], dtype='float32')
    assert dem.block_mean(z, 2)[0, 0] == pytest.approx(3.0)
    assert np.isnan(dem.block_mean(np.full((2, 2), np.nan, dtype='float32'), 2)[0, 0])


def test_lidar_tiles_newest_first_and_untrusted_urls_dropped():
    page = {'total': 3, 'items': [
        {'downloadURL': 'https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/OLD_2016/TIFF/a.tif', 'publicationDate': '2020-03-30'},
        {'downloadURL': 'https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/NEW_2023/TIFF/b.tif', 'publicationDate': '2026-03-20'},
        {'downloadURL': 'https://evil.example/Elevation/1m/Projects/X/TIFF/c.tif', 'publicationDate': '2027-01-01'},
    ]}
    tiles = sources.lidar_tiles(39.5, -106.25, 39.75, -106.0, get_json=lambda url: page)
    assert [t['project'] for t in tiles] == ['NEW_2023', 'OLD_2016']


def test_dem10m_tiles_named_by_nw_corner():
    assert sources.dem10m_tiles(39.4, -106.3, 39.8, -106.0) == [
        'https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/n40w107/USGS_13_n40w107.tif']


def test_build_cell_end_to_end(mini_cell, cone_dem, tmp_path):
    out = tmp_path / 'out'
    entry = build_cell.build(mini_cell, str(out), [cone_dem], log=lambda *_: None)
    cdir = out / mini_cell
    assert sorted(p.name for p in cdir.iterdir()) == ['entry.json', 't0-2m.json.gz', 't0-3m.json.gz', 't1-4.json.gz']
    assert entry['sources']['lidar'] > 0.99
    t03 = cellfile.loads((cdir / 't0-3m.json.gz').read_bytes())
    t02 = cellfile.loads((cdir / 't0-2m.json.gz').read_bytes())
    low = cellfile.loads((cdir / 't1-4.json.gz').read_bytes())
    # every ring of the cone shows at the closest zoom, cliffs included
    assert set(t03['tiers']['0']) == {'30', '35', '40', '45', '55'}
    assert all(t03['tiers']['0'][c] for c in ('30', '35', '40', '45', '55'))
    assert all(t02['tiers']['0'][c] for c in ('30', '35', '40', '45', '55'))
    # zoomed out, whole bands drop: no 30-35 at tier 1, no cliffs from tier 2, one 30+ class at tier 4
    assert set(low['tiers']['1']) == {'35', '40', '45', '55'}
    assert set(low['tiers']['2']) == {'35', '40', '45'}
    assert set(low['tiers']['4']) == {'30'}
    # every point lies in the cell
    s, w, n, e = grid.cell_bounds(mini_cell)
    for doc in (t03, t02, low):
        for cls in doc['tiers'].values():
            for polys in cls.values():
                for p in polys:
                    for ring in p:
                        pts = cellfile.decode_ring(ring)
                        assert all(grid.to_units(s) - 1 <= y <= grid.to_units(n) + 1 and
                                   grid.to_units(w) - 1 <= x <= grid.to_units(e) + 1 for y, x in pts)
    assert entry['layers']['t0-3m']['tiers']['0']['polygons'] > 0
    assert json.loads((cdir / 'entry.json').read_text())['recipe'] == 1


def test_build_cell_main_names_a_failed_cell(tmp_path, capsys):
    rc = build_cell.main(['not-a-cell', '--out', str(tmp_path), '--dem', 'x.tif'])
    assert rc == 1
    assert json.loads((tmp_path / 'failed.json').read_text()) == ['not-a-cell']


# --- an oversize layer: the cell is split into quarters ---------------------------------------
# Requirements: A cell too large to publish whole is split into its four quarters; A quarter holds its
# cell's polygons clipped to the quarter; A quarter file names its cell and its quarter; An oversize 2 m
# layer is left out of its cell.

QUARTERS = ['316_-850', '316_-849', '317_-850', '317_-849']


def _whole(raw):
    return b'"quarter":' not in raw


def _quarter(raw, quarter):
    return f'"quarter":"{quarter}"'.encode() in raw


def _pad_gzip(monkeypatch, layer, extra, where=lambda raw: True):
    """Makes `layer`'s gzip file `extra` bytes larger than it would be (a stand-in for a huge cell),
    for the documents `where` picks (whole, a quarter, or all)."""
    real = cellfile.compress

    def compress(raw):
        data = real(raw)
        return data + b'\0' * extra if f'"layer":"{layer}"'.encode() in raw and where(raw) else data
    monkeypatch.setattr(cellfile, 'compress', compress)


def _pad_json(monkeypatch, layer, extra=0, to=None, cell=None, whole_only=False):
    """Makes `layer`'s JSON `extra` bytes longer, or exactly `to` bytes (trailing whitespace: still
    valid JSON); only in `cell` when given, only the whole cell's with whole_only."""
    real = cellfile.json_bytes

    def json_bytes(doc):
        raw = real(doc)
        if doc['layer'] != layer or (cell and doc['cell'] != cell) or (whole_only and 'quarter' in doc):
            return raw
        return raw + b' ' * ((to - len(raw)) if to is not None else extra)
    monkeypatch.setattr(cellfile, 'json_bytes', json_bytes)


LEFT_OUT = {'bytes': 0, 'tiers': {'0': {'polygons': 0, 'points': 0}}}


def _points(doc):
    for cls in doc['tiers'].values():
        for polys in cls.values():
            for p in polys:
                for ring in p:
                    yield from cellfile.decode_ring(ring)


def test_quarters_of_a_cell():
    assert grid.quarters('158_-425') == QUARTERS
    assert grid.quarter_bounds('158_-425', '317_-849') == (39.625, -106.125, 39.75, -106.0)
    assert grid.quarter_bounds('158_-425', '316_-850') == (39.5, -106.25, 39.625, -106.125)
    with pytest.raises(ValueError):
        grid.quarter_bounds('158_-425', '318_-850')


def test_build_a_2m_layer_too_large_splits_the_cell(mini_cell, cone_dem, tmp_path, monkeypatch):
    _pad_gzip(monkeypatch, 't0-2m', build_cell.MAX_FILE_BYTES, where=_whole)
    logged = []
    entry = build_cell.build(mini_cell, str(tmp_path), [cone_dem], log=logged.append)
    cdir = tmp_path / mini_cell
    assert sorted(p.name for p in cdir.iterdir()) == sorted(['entry.json'] + QUARTERS)
    for q in QUARTERS:
        assert sorted(p.name for p in (cdir / q).iterdir()) == ['t0-2m.json.gz', 't0-3m.json.gz', 't1-4.json.gz']
        for layer in ('t0-3m', 't0-2m', 't1-4'):
            doc = json.loads(gzip.decompress((cdir / q / f'{layer}.json.gz').read_bytes()))
            assert list(doc) == ['format', 'version', 'cell', 'quarter', 'layer', 'tiers']
            assert (doc['format'], doc['version'], doc['cell'], doc['quarter'], doc['layer']) == \
                ('slope-cell', 1, mini_cell, q, layer)
            assert entry['quarters'][q]['layers'][layer]['bytes'] == (cdir / q / f'{layer}.json.gz').stat().st_size
    assert 'layers' not in entry and list(entry['quarters']) == QUARTERS
    assert json.loads((cdir / 'entry.json').read_text()) == entry
    warnings = [m for m in logged if m.startswith('::warning::')]
    assert len(warnings) == 1 and mini_cell in warnings[0] and 'quarters' in warnings[0]


def test_build_a_zoomed_out_layers_json_too_large_splits_the_cell(mini_cell, cone_dem, tmp_path, monkeypatch):
    monkeypatch.setattr(build_cell, 'MAX_JSON_BYTES', 2_000_000)
    _pad_json(monkeypatch, 't1-4', 2_000_001, whole_only=True)
    entry = build_cell.build(mini_cell, str(tmp_path), [cone_dem], log=lambda *_: None)
    assert list(entry['quarters']) == QUARTERS
    assert not (tmp_path / mini_cell / 't1-4.json.gz').exists()


@pytest.mark.parametrize('size, whole', [(2_000_000, True), (2_000_001, False)])
def test_build_a_cell_is_split_only_over_the_limit(mini_cell, cone_dem, tmp_path, monkeypatch, size, whole):
    monkeypatch.setattr(build_cell, 'MAX_JSON_BYTES', 2_000_000)
    _pad_json(monkeypatch, 't0-2m', to=size, whole_only=True)
    entry = build_cell.build(mini_cell, str(tmp_path), [cone_dem], log=lambda *_: None)
    assert (tmp_path / mini_cell / 't0-2m.json.gz').exists() is whole
    assert ('layers' in entry) is whole and ('quarters' in entry) is not whole


def test_build_a_split_cells_quarters_hold_the_cells_polygons_clipped(mini_cell, cone_dem, tmp_path, monkeypatch):
    whole = build_cell.build(mini_cell, str(tmp_path / 'whole'), [cone_dem], log=lambda *_: None)
    _pad_gzip(monkeypatch, 't0-2m', build_cell.MAX_FILE_BYTES, where=_whole)
    build_cell.build(mini_cell, str(tmp_path / 'split'), [cone_dem], log=lambda *_: None)
    wdoc = cellfile.loads((tmp_path / 'whole' / mini_cell / 't0-3m.json.gz').read_bytes())
    total_q = 0
    for q in QUARTERS:
        doc = cellfile.loads((tmp_path / 'split' / mini_cell / q / 't0-3m.json.gz').read_bytes())
        # the same tiers and classes as the whole cell
        assert {t: set(c) for t, c in doc['tiers'].items()} == {t: set(c) for t, c in wdoc['tiers'].items()}
        s, w, n, e = grid.quarter_bounds(mini_cell, q)
        pts = list(_points(doc))
        assert pts, q  # the cone is centred on the quarters' meeting point: each quarter has some
        assert all(grid.to_units(s) - 1 <= y <= grid.to_units(n) + 1 and
                   grid.to_units(w) - 1 <= x <= grid.to_units(e) + 1 for y, x in pts)
        total_q += sum(len(p) for c in doc['tiers'].values() for p in c.values())
    # polygons crossing the middle lines are cut: at least as many polygons as whole
    assert total_q > sum(len(p) for c in wdoc['tiers'].values() for p in c.values())
    assert whole['layers']['t0-3m']['bytes'] > 0


def test_clip_keeps_a_polygon_inside_one_quarter_and_cuts_one_across():
    cell = '158_-425'
    s, w, n, e = grid.cell_bounds(cell)
    ymid, xmid = grid.to_units((s + n) / 2), grid.to_units((w + e) / 2)
    y0, x0 = grid.to_units(s), grid.to_units(w)
    inside = [[(y0 + 100, x0 + 100), (y0 + 100, x0 + 200), (y0 + 200, x0 + 200), (y0 + 200, x0 + 100)]]
    across = [[(ymid - 50, x0 + 100), (ymid - 50, x0 + 200), (ymid + 50, x0 + 200), (ymid + 50, x0 + 100)]]
    out = classes.clip_to_quarters(cell, {30: [inside, across], 35: []})
    assert list(out) == QUARTERS
    assert out['316_-850'][30][0] == inside
    assert len(out['316_-850'][30]) == 2 and len(out['317_-850'][30]) == 1
    # an empty class stays, empty, in every quarter; a quarter with nothing has its classes empty
    assert out['316_-849'] == {30: [], 35: []} and out['317_-849'] == {30: [], 35: []}
    for q, piece in (('316_-850', out['316_-850'][30][1]), ('317_-850', out['317_-850'][30][0])):
        qs, qw, qn, qe = grid.quarter_bounds(cell, q)
        ys = [y for y, _x in piece[0]]
        assert grid.to_units(qs) - 1 <= min(ys) and max(ys) <= grid.to_units(qn) + 1


def test_build_a_split_cell_builds_to_the_same_bytes(mini_cell, cone_dem, tmp_path, monkeypatch):
    _pad_gzip(monkeypatch, 't0-2m', build_cell.MAX_FILE_BYTES, where=_whole)
    for d in ('a', 'b'):
        build_cell.build(mini_cell, str(tmp_path / d), [cone_dem], log=lambda *_: None)
    files = sorted(p.relative_to(tmp_path / 'a') for p in (tmp_path / 'a').rglob('*.json.gz'))
    assert len(files) == 12
    assert all((tmp_path / 'a' / f).read_bytes() == (tmp_path / 'b' / f).read_bytes() for f in files)


def test_build_a_quarters_2m_layer_still_too_large_is_left_out(mini_cell, cone_dem, tmp_path, monkeypatch, capsys):
    _pad_gzip(monkeypatch, 't0-2m', build_cell.MAX_FILE_BYTES, where=lambda raw: _whole(raw) or _quarter(raw, '316_-850'))
    logged = []
    entry = build_cell.build(mini_cell, str(tmp_path / 'a'), [cone_dem], log=logged.append)
    qdir = tmp_path / 'a' / mini_cell / '316_-850'
    assert sorted(p.name for p in qdir.iterdir()) == ['t0-3m.json.gz', 't1-4.json.gz']
    assert entry['quarters']['316_-850']['layers']['t0-2m'] == LEFT_OUT
    assert all(entry['quarters'][q]['layers']['t0-2m']['bytes'] > 0 for q in QUARTERS[1:])
    assert any(m.startswith('::warning::') and mini_cell in m and '316_-850' in m and 't0-2m' in m for m in logged)
    out = tmp_path / 'out'
    assert build_cell.main([f'colorado/{mini_cell}', '--out', str(out), '--dem', cone_dem]) == 0
    assert not (out / 'failed.json').exists()


def test_build_a_whole_cells_layer_is_never_left_out(mini_cell, cone_dem, tmp_path, monkeypatch):
    _pad_gzip(monkeypatch, 't0-2m', build_cell.MAX_FILE_BYTES, where=_whole)
    entry = build_cell.build(mini_cell, str(tmp_path), [cone_dem], log=lambda *_: None)
    assert 'layers' not in entry
    assert all(entry['quarters'][q]['layers']['t0-2m']['bytes'] > 0 for q in QUARTERS)


def test_build_a_quarters_3m_layer_too_large_fails_the_cell(mini_cell, cone_dem, tmp_path, monkeypatch, capsys):
    _pad_gzip(monkeypatch, 't0-3m', build_cell.MAX_FILE_BYTES)
    with pytest.raises(RuntimeError, match='316_-850/t0-3m is .* over the .*-byte limit per file'):
        build_cell.build(mini_cell, str(tmp_path), [cone_dem], log=lambda *_: None)
    assert not (tmp_path / mini_cell).exists()
    assert build_cell.main([f'colorado/{mini_cell}', '--out', str(tmp_path / 'o'), '--dem', cone_dem]) == 1


def test_build_a_quarters_zoomed_out_json_too_large_fails_and_leaves_no_folder(
        mini_cell, cone_dem, tmp_path, monkeypatch, capsys):
    # requirement: A failed cell keeps its previous files
    monkeypatch.setattr(build_cell, 'MAX_JSON_BYTES', 2_000_000)
    _pad_json(monkeypatch, 't1-4', 2_000_001)
    out = tmp_path / 'out'
    rc = build_cell.main([f'colorado/{mini_cell}', '--out', str(out), '--dem', cone_dem])
    assert rc == 1
    assert sorted(p.name for p in out.iterdir()) == ['failed.json', 'jobs.txt']
    assert json.loads((out / 'failed.json').read_text()) == [mini_cell]
    assert 'cell 158_-425 failed' in capsys.readouterr().err


def test_a_cell_that_fails_after_writing_a_layer_does_not_block_the_deploy(
        mini_cell, cone_dem, tmp_path, monkeypatch, capsys):
    # requirement: A failed cell keeps its previous files, "A cell fails after writing a layer"
    from slope_extracts import publish
    other = '158_-424'
    monkeypatch.setattr(build_cell, 'MAX_JSON_BYTES', 2_000_000)
    _pad_json(monkeypatch, 't1-4', 2_000_001, cell=mini_cell)
    jobs = f'colorado/{mini_cell} colorado/{other}'
    out = tmp_path / 'artifacts' / 'cells-0'
    assert build_cell.main(jobs.split() + ['--out', str(out), '--dem', cone_dem]) == 1
    region = [{'id': 'colorado', 'name': 'Colorado',
               'bounds': {'south': 37.01, 'west': -109.04, 'north': 40.99, 'east': -102.06}}]
    built = publish.read_artifacts(str(tmp_path / 'artifacts'), region, [jobs])
    assert set(built) == {('colorado', other)}


def test_a_split_cell_passes_the_deploy_checks(mini_cell, cone_dem, tmp_path, monkeypatch):
    from slope_extracts import publish
    _pad_gzip(monkeypatch, 't0-2m', build_cell.MAX_FILE_BYTES, where=_whole)
    out = tmp_path / 'artifacts' / 'cells-0'
    assert build_cell.main([f'colorado/{mini_cell}', '--out', str(out), '--dem', cone_dem]) == 0
    region = [{'id': 'colorado', 'name': 'Colorado',
               'bounds': {'south': 37.01, 'west': -109.04, 'north': 40.99, 'east': -102.06}}]
    built = publish.read_artifacts(str(tmp_path / 'artifacts'), region, [f'colorado/{mini_cell}'])
    entry, paths = built[('colorado', mini_cell)]
    assert list(entry['quarters']) == QUARTERS and len(paths) == 12


def test_build_limits_are_the_deploy_limits():
    from slope_extracts import publish
    assert build_cell.MAX_FILE_BYTES == publish.MAX_FILE_BYTES == 20 * 1024 * 1024
    assert build_cell.MAX_JSON_BYTES == publish.MAX_CELL_JSON == 64 * 1024 * 1024


# Requirement: A cell too large to publish whole is split into its four quarters ("A cell exactly at the limit")
@pytest.mark.parametrize('extra, whole', [(0, True), (1, False)])
def test_build_a_gzip_file_exactly_at_the_limit_stays_whole(mini_cell, cone_dem, tmp_path, monkeypatch, extra, whole):
    real = cellfile.compress

    def compress(raw):
        data = real(raw)
        if b'"layer":"t0-2m"' in raw and _whole(raw):
            return data + b'\0' * (build_cell.MAX_FILE_BYTES + extra - len(data))
        return data
    monkeypatch.setattr(cellfile, 'compress', compress)
    entry = build_cell.build(mini_cell, str(tmp_path), [cone_dem], log=lambda *_: None)
    assert ('layers' in entry) is whole
    if whole:
        assert (tmp_path / mini_cell / 't0-2m.json.gz').stat().st_size == build_cell.MAX_FILE_BYTES


# Requirement: An oversize 2 m layer is left out of its cell ("A 3 m layer too large to publish")
def test_build_a_3m_layer_too_large_whole_splits_the_cell(mini_cell, cone_dem, tmp_path, monkeypatch):
    _pad_gzip(monkeypatch, 't0-3m', build_cell.MAX_FILE_BYTES, where=_whole)
    out = tmp_path / 'out'
    assert build_cell.main([f'colorado/{mini_cell}', '--out', str(out), '--dem', cone_dem]) == 0
    entry = json.loads((out / mini_cell / 'entry.json').read_text())
    assert list(entry['quarters']) == QUARTERS
    assert all((out / mini_cell / q / 't0-3m.json.gz').exists() for q in QUARTERS)


# Requirement: A quarter holds its cell's polygons clipped to the quarter ("A quarter with no steep ground")
def test_a_quarter_with_no_steep_ground_is_written_with_its_classes_empty(tmp_path):
    cell = '158_-425'
    s, w, _n, _e = grid.cell_bounds(cell)
    y, x = grid.to_units(s) + 100, grid.to_units(w) + 100
    poly = [[(y, x), (y, x + 50), (y + 50, x + 50), (y + 50, x)]]  # in 316_-850 only
    tiers = {'t0-3m': {0: {30: [poly], 35: [], 40: [], 45: [], 55: []}},
             't0-2m': {0: {30: [poly], 35: [], 40: [], 45: [], 55: []}},
             't1-4': {1: {35: [], 40: [], 45: [], 55: []}, 2: {35: [], 40: [], 45: []}, 3: {35: [], 40: [], 45: []},
                      4: {30: [poly]}}}
    os.makedirs(tmp_path / cell)
    build_cell._write_quarters(cell, str(tmp_path / cell), tiers, log=lambda *_: None)
    for layer in ('t0-3m', 't0-2m', 't1-4'):
        doc = cellfile.loads((tmp_path / cell / '317_-849' / f'{layer}.json.gz').read_bytes())
        assert set(doc['tiers']) == {str(t) for t in tiers[layer]}
        assert all(polys == [] for c in doc['tiers'].values() for polys in c.values())
        assert {t: set(c) for t, c in doc['tiers'].items()} == {str(t): {str(b) for b in c} for t, c in tiers[layer].items()}
