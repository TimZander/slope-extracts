"""british-columbia: an area's source, NRCan's HRDEM lidar, empty cells where there is none, the credit."""
import copy
import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from slope_extracts import build_cell, dem, grid, site, sources
from conftest import CRS, MINI, cone
from sitefake import COLORADO, DILLON, entry

STAC = 'https://datacube.services.geo.ca/stac/api/search'
DTM = 'https://canelevation-dem.s3.ca-central-1.amazonaws.com/hrdem-mosaic-1m/{}-mosaic-1m-dtm.tif'
BC = {'id': 'british-columbia', 'name': 'British Columbia', 'source': 'hrdem',
      'boxes': [{'south': 49.01, 'west': -117.49, 'north': 49.24, 'east': -117.26}]}  # 4 cells
CO = dict(COLORADO, source='3dep')


# --- the areas list: an area's source ------------------------------------------------------------
# Requirements: The areas list; A cell has one elevation source

def test_an_area_names_its_source():
    assert site.validate_areas([CO, BC]) == [CO, BC]


@pytest.mark.parametrize('bad', ['missing', 'usgs', 3, None])
def test_an_area_without_a_known_source_is_refused(bad):
    a = dict(BC)
    if bad == 'missing':
        del a['source']
    else:
        a['source'] = bad
    with pytest.raises(ValueError):
        site.validate_areas([a])


def test_a_cell_two_sources_cover_fails_the_plan():
    us = {'id': 'washington-edge', 'name': 'Edge', 'source': '3dep',
          'boxes': [{'south': 49.01, 'west': -117.49, 'north': 49.1, 'east': -117.4}]}
    with pytest.raises(ValueError, match='two sources'):
        site.validate_areas([BC, us])


def test_two_areas_of_one_source_may_share_a_cell():
    other = dict(BC, id='kootenay', name='Kootenay')
    site.validate_areas([BC, other])


def test_each_cell_has_its_areas_source():
    got = site.cell_sources([CO, BC])
    assert got[DILLON] == '3dep' and got['196_-470'] == 'hrdem' and len(got) == 464 + 4


def test_a_manifest_area_has_no_source():
    tiles = site.build_tiles([CO, BC], {})
    m = site.build_manifest([CO, BC], tiles, {t: 100 for t in tiles}, {})
    assert all(set(a) == {'id', 'name', 'boxes', 'tiles'} for a in m['areas'])


# --- the HRDEM source, from a fake catalogue ---------------------------------------------------
# Requirements: Elevation in an hrdem area comes from NRCan lidar only; The catalogue must answer before
# a cell is built empty

def feature(fid, href=None):
    f = {'id': fid, 'type': 'Feature', 'assets': {}}
    if href:
        f['assets']['dtm'] = {'href': href}
    return f


class Catalogue:
    """The STAC search: collection -> pages of features; a page links the next by POST."""
    def __init__(self, mosaic=None, projects=None, next_host=STAC):
        self.pages = {'hrdem-mosaic-1m': mosaic if mosaic is not None else [[feature('2_4-mosaic-1m', DTM.format('2_4'))]],
                      'hrdem-lidar': projects if projects is not None else [[feature('BC-Example_2019-1m')]]}
        self.next_host = next_host
        self.calls = []

    def post(self, url, body):
        self.calls.append((url, body))
        coll = body['collections'][0]
        page = body.get('page', 0)
        pages = self.pages[coll]
        out = {'type': 'FeatureCollection', 'features': pages[page] if page < len(pages) else [], 'links': []}
        if page + 1 < len(pages):
            out['links'].append({'rel': 'next', 'href': self.next_host, 'method': 'POST', 'body': dict(body, page=page + 1)})
        return out


BOX = (49.0, -117.5, 49.25, -117.25)


def test_the_mosaic_tiles_are_its_trusted_dtm_urls():
    cat = Catalogue(mosaic=[[feature('2_4-mosaic-1m', DTM.format('2_4')),
                             feature('2_5-mosaic-1m', DTM.format('2_5').replace('-dtm.tif', '-dsm.tif')),
                             feature('3_4-mosaic-1m', 'https://evil.example/hrdem-mosaic-1m/3_4-mosaic-1m-dtm.tif'),
                             feature('3_5-mosaic-1m', DTM.format('3_5').replace('mosaic-1m/', 'mosaic-1m/../x/')),
                             feature('1_4-mosaic-1m')]])
    assert sources.hrdem_tiles(*BOX, post=cat.post) == [DTM.format('2_4')]
    assert cat.calls[0][0] == STAC and cat.calls[0][1]['collections'] == ['hrdem-mosaic-1m']
    assert cat.calls[0][1]['bbox'] == [-117.5, 49.0, -117.25, 49.25]


@pytest.mark.parametrize('mosaic', [[[]], [[feature('2_5-mosaic-1m', 'https://evil.example/x-dtm.tif')]]])
def test_an_empty_mosaic_answer_fails(mosaic):
    with pytest.raises(RuntimeError, match='no mosaic tile'):
        sources.hrdem_tiles(*BOX, post=Catalogue(mosaic=mosaic).post)


def test_the_projects_of_every_page_with_valid_ids():
    pages = [[feature('BC-B_2017-1m'), feature('bad/id')], [feature('BC-A_2015-1m'), feature('a b')],
             [feature('x' * 101), feature('BC-B_2017-1m')]]
    cat = Catalogue(projects=pages)
    assert sources.hrdem_projects(*BOX, post=cat.post) == ['BC-A_2015-1m', 'BC-B_2017-1m']
    assert len(cat.calls) == 3


def test_a_next_page_on_another_host_is_not_followed():
    cat = Catalogue(projects=[[feature('BC-A_2015-1m')], [feature('BC-B_2017-1m')]], next_host='https://evil.example/search')
    with pytest.raises(RuntimeError, match='next page'):
        sources.hrdem_projects(*BOX, post=cat.post)


def test_a_failed_catalogue_request_fails():
    def post(url, body):
        raise RuntimeError('the catalogue did not answer')
    with pytest.raises(RuntimeError):
        sources.hrdem_projects(*BOX, post=post)


# --- building an hrdem cell -----------------------------------------------------------------------

@pytest.fixture
def half_cone_dem(tmp_path):
    """The cone over the mini cell's west half only: the east half has no lidar (no value)."""
    from rasterio.warp import transform_bounds
    s, w, n, e = MINI
    left, bottom, right, top = transform_bounds('EPSG:4326', CRS, w, s, e, n, densify_pts=21)
    left, bottom, right, top = left - 400, bottom - 400, right + 400, top + 400
    width, height = int(right - left), int(top - bottom)
    z = cone(width, height, 1.0, left, top, (left + right) / 2, (bottom + top) / 2)
    z[:, width // 2:] = np.nan
    path = tmp_path / 'half.tif'
    with rasterio.open(path, 'w', driver='GTiff', width=width, height=height, count=1, dtype='float32', crs=CRS,
                       transform=from_origin(left, top, 1.0, 1.0), nodata=np.nan) as dst:
        dst.write(z, 1)
    return str(path)


def no_3dep(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError('an hrdem cell read a 3DEP source')
    monkeypatch.setattr(sources, 'lidar_tiles', refuse)
    monkeypatch.setattr(sources, 'dem10m_tiles', refuse)


# Requirement: Elevation in an hrdem area comes from NRCan lidar only ("A cell partly covered by lidar")
def test_an_hrdem_cell_partly_covered_reads_lidar_only(mini_cell, half_cone_dem, tmp_path, monkeypatch):
    no_3dep(monkeypatch)
    monkeypatch.setattr(sources, 'hrdem_tiles', lambda *a, **k: [half_cone_dem])
    monkeypatch.setattr(sources, 'hrdem_projects', lambda *a, **k: ['BC-Example_2019-1m'])
    e = build_cell.build(mini_cell, str(tmp_path), source='hrdem', log=lambda *_: None)
    assert e['sources']['dem10m'] == 0 and 0.3 < e['sources']['lidar'] < 0.7
    assert abs(e['sources']['lidar'] + e['sources']['none'] - 1) < 1e-3
    assert e['projects'] == ['BC-Example_2019-1m']
    assert e['layers']['t0-3m']['tiers']['0']['polygons'] > 0


# Requirement: An hrdem cell with no lidar project is built empty without reading elevation
def test_an_hrdem_cell_with_no_project_is_built_empty_without_a_read(mini_cell, tmp_path, monkeypatch):
    no_3dep(monkeypatch)
    calls = []
    monkeypatch.setattr(sources, 'hrdem_tiles', lambda *a, **k: calls.append('tiles') or [DTM.format('2_4')])
    monkeypatch.setattr(sources, 'hrdem_projects', lambda *a, **k: [])

    def no_read(*a, **k):
        raise AssertionError('elevation was read')
    monkeypatch.setattr(dem, 'elevation_2m', no_read)
    e = build_cell.build(mini_cell, str(tmp_path), source='hrdem', log=lambda *_: None)
    assert calls == ['tiles']  # the mosaic search ran: the catalogue answered
    assert e['sources'] == {'lidar': 0, 'dem10m': 0, 'none': 1}
    assert e['projects'] == []
    assert e['layers'] == {l: {'bytes': 0, 'tiers': {}} for l in ('t0-3m', 't0-2m', 't1-4')}
    assert sorted(p.name for p in (tmp_path / mini_cell).iterdir()) == ['entry.json']
    site.validate_entry(json.loads((tmp_path / mini_cell / 'entry.json').read_text()), mini_cell)


# Requirement: The catalogue must answer before a cell is built empty ("An empty answer")
def test_an_hrdem_cell_fails_when_the_mosaic_answer_is_empty(mini_cell, tmp_path, monkeypatch):
    no_3dep(monkeypatch)
    monkeypatch.setattr(sources, '_post_json', Catalogue(mosaic=[[]], projects=[[]]).post)
    with pytest.raises(RuntimeError, match='no mosaic tile'):
        build_cell.build(mini_cell, str(tmp_path), source='hrdem', log=lambda *_: None)
    assert not (tmp_path / mini_cell).exists()


def test_build_cell_main_takes_each_cells_source_from_the_areas(tmp_path, monkeypatch):
    areas = tmp_path / 'areas.json'
    areas.write_text(json.dumps([CO, BC]))
    seen = {}
    monkeypatch.setattr(build_cell, 'build', lambda c, out, dem_paths=None, source='3dep', **k: seen.setdefault(c, source))
    assert build_cell.main([DILLON, '196_-470', '--out', str(tmp_path / 'o'), '--areas', str(areas)]) == 0
    assert seen == {DILLON: '3dep', '196_-470': 'hrdem'}


@pytest.mark.parametrize('cell, epsg', [('230_-540', 'EPSG:26907'), ('220_-520', 'EPSG:26909'), ('205_-471', 'EPSG:26911')])
def test_bc_cells_have_their_nad83_utm_zone(cell, epsg):
    assert grid.utm_epsg(cell) == epsg


# --- project ids and the credit ---------------------------------------------------------------
# Requirements: A built cell's entry gives its build and its layers ("A Canadian project id"); The site
# carries its sources notice ("A Canadian cell's credit")

@pytest.mark.parametrize('pid, ok', [('BC-Example_2019-1m', True), ('CO_Central_Western_2016', True),
                                     ('a/b', False), ('a b', False), ('', False), ('x' * 101, False)])
def test_project_ids(pid, ok):
    e = dict(entry(DILLON), projects=[pid])
    if ok:
        site.validate_entry(e, DILLON)
    else:
        with pytest.raises(ValueError):
            site.validate_entry(e, DILLON)


def test_the_notice_and_attribution_credit_both_sources():
    cells = {DILLON: dict(entry(DILLON), projects=['CO_Central_Western_2016']),
             '196_-470': dict(entry('196_-470'), projects=['BC-Example_2019-1m'])}
    text = site.license_text(cells)
    assert 'USGS 3D Elevation Program' in text and 'public domain' in text
    assert 'Contains information licensed under the Open Government Licence – Canada.' in text
    assert 'https://open.canada.ca/en/open-government-licence-canada' in text
    assert '- BC-Example_2019-1m' in text and '- CO_Central_Western_2016' in text
    assert 'USGS' in site.ATTRIBUTION and 'NRCan' in site.ATTRIBUTION and 'Open Government Licence' in site.ATTRIBUTION
