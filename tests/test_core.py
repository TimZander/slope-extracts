import gzip
import json

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


# --- an oversize layer (requirement: An oversize 2 m layer is left out of its cell) ------------

def _pad_gzip(monkeypatch, layer, extra):
    """Makes `layer`'s gzip file `extra` bytes larger than it would be (a stand-in for a huge cell)."""
    real = cellfile.compress

    def compress(raw):
        data = real(raw)
        return data + b'\0' * extra if f'"layer":"{layer}"'.encode() in raw else data
    monkeypatch.setattr(cellfile, 'compress', compress)


def _pad_json(monkeypatch, layer, extra=0, to=None, cell=None):
    """Makes `layer`'s JSON `extra` bytes longer, or exactly `to` bytes (trailing whitespace: still
    valid JSON); only in `cell` when given."""
    real = cellfile.json_bytes

    def json_bytes(doc):
        raw = real(doc)
        if doc['layer'] != layer or (cell and doc['cell'] != cell):
            return raw
        return raw + b' ' * ((to - len(raw)) if to is not None else extra)
    monkeypatch.setattr(cellfile, 'json_bytes', json_bytes)


LEFT_OUT = {'bytes': 0, 'tiers': {'0': {'polygons': 0, 'points': 0}}}


def test_build_an_oversize_2m_layer_is_left_out(mini_cell, cone_dem, tmp_path, monkeypatch):
    _pad_gzip(monkeypatch, 't0-2m', build_cell.MAX_FILE_BYTES)
    logged = []
    entry = build_cell.build(mini_cell, str(tmp_path), [cone_dem], log=logged.append)
    cdir = tmp_path / mini_cell
    assert sorted(p.name for p in cdir.iterdir()) == ['entry.json', 't0-3m.json.gz', 't1-4.json.gz']
    assert entry['layers']['t0-2m'] == LEFT_OUT
    assert json.loads((cdir / 'entry.json').read_text())['layers']['t0-2m'] == LEFT_OUT
    assert entry['layers']['t0-3m']['bytes'] > 0 and entry['layers']['t1-4']['bytes'] > 0
    warnings = [m for m in logged if m.startswith('::warning::')]
    assert len(warnings) == 1 and mini_cell in warnings[0] and 't0-2m' in warnings[0]


def test_build_main_does_not_fail_for_a_left_out_2m_layer(mini_cell, cone_dem, tmp_path, monkeypatch, capsys):
    _pad_gzip(monkeypatch, 't0-2m', build_cell.MAX_FILE_BYTES)
    out = tmp_path / 'out'
    assert build_cell.main([f'colorado/{mini_cell}', '--out', str(out), '--dem', cone_dem]) == 0
    assert not (out / 'failed.json').exists()
    assert f'::warning::cell {mini_cell}' in capsys.readouterr().out


@pytest.mark.parametrize('size, kept', [(2_000_000, True), (2_000_001, False)])
def test_build_a_2m_layer_is_left_out_only_over_the_limit(mini_cell, cone_dem, tmp_path, monkeypatch, size, kept):
    monkeypatch.setattr(build_cell, 'MAX_JSON_BYTES', 2_000_000)
    _pad_json(monkeypatch, 't0-2m', to=size)
    entry = build_cell.build(mini_cell, str(tmp_path), [cone_dem], log=lambda *_: None)
    assert (tmp_path / mini_cell / 't0-2m.json.gz').exists() is kept
    assert (entry['layers']['t0-2m']['bytes'] > 0) is kept


def test_build_a_2m_layer_whose_json_is_too_large_is_left_out(mini_cell, cone_dem, tmp_path, monkeypatch):
    monkeypatch.setattr(build_cell, 'MAX_JSON_BYTES', 2_000_000)
    _pad_json(monkeypatch, 't0-2m', 2_000_001)
    logged = []
    entry = build_cell.build(mini_cell, str(tmp_path), [cone_dem], log=logged.append)
    assert not (tmp_path / mini_cell / 't0-2m.json.gz').exists()
    assert entry['layers']['t0-2m'] == LEFT_OUT
    assert any(m.startswith('::warning::') and 't0-2m' in m for m in logged)


def test_build_an_oversize_3m_layer_fails_the_cell(mini_cell, cone_dem, tmp_path, monkeypatch, capsys):
    _pad_gzip(monkeypatch, 't0-3m', build_cell.MAX_FILE_BYTES)
    with pytest.raises(RuntimeError, match='t0-3m is .* over the .*-byte limit per file'):
        build_cell.build(mini_cell, str(tmp_path), [cone_dem], log=lambda *_: None)
    assert build_cell.main([f'colorado/{mini_cell}', '--out', str(tmp_path / 'o'), '--dem', cone_dem]) == 1


def test_build_a_zoomed_out_layer_whose_json_is_too_large_fails_and_leaves_no_folder(
        mini_cell, cone_dem, tmp_path, monkeypatch, capsys):
    # requirement: A failed cell keeps its previous files (t1-4 is written after t0-3m)
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


def test_build_limits_are_the_deploy_limits():
    from slope_extracts import publish
    assert build_cell.MAX_FILE_BYTES == publish.MAX_FILE_BYTES == 20 * 1024 * 1024
    assert build_cell.MAX_JSON_BYTES == publish.MAX_CELL_JSON == 64 * 1024 * 1024
