"""Where a cell's elevation comes from, by its area's `source`.

`3dep`, USGS 3DEP, public domain:
- 1 m lidar DEM tiles, found through the TNM Access API and read over HTTP range requests from
  their own 2 m overviews.
- The 1/3 arc-second (~10 m) seamless DEM, where no lidar covers a pixel.

`hrdem`, Natural Resources Canada's HRDEM (Open Government Licence - Canada), lidar only:
- the 1 m mosaic's DTM tiles (cloud-optimised GeoTIFFs), found through NRCan's STAC catalogue;
- the catalogue's lidar projects meeting the frame, for the entry and the credit. No project means no
  lidar: the cell is built empty without reading elevation.

Every answer is untrusted: only GeoTIFF URLs of the exact trusted forms are used, and only plain ids.
"""
import json
import math
import re
import time
import urllib.parse
import urllib.request

TNM_API = 'https://tnmaccess.nationalmap.gov/api/v1/products'
LIDAR_DATASET = 'Digital Elevation Model (DEM) 1 meter'
STAGED = 'https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/'
LIDAR_URL = re.compile(r'^https://prd-tnm\.s3\.amazonaws\.com/StagedProducts/Elevation/1m/Projects/'
                       r'([A-Za-z0-9_]+)/TIFF/[A-Za-z0-9_]+\.tif$')
USER_AGENT = 'slope-extracts (https://github.com/TimZander/slope-extracts)'


def _get_json(url, attempts=4, delay=5.0, opener=urllib.request.urlopen):
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            with opener(req, timeout=60) as resp:
                return json.loads(resp.read(8 * 1024 * 1024))
        except Exception as e:  # network or parse failure: retried, then named
            last = e
            time.sleep(delay * (i + 1))
    raise RuntimeError(f'the TNM Access API did not answer after {attempts} tries: {last}')


def lidar_tiles(south, west, north, east, get_json=_get_json):
    """The 1 m tiles touching a lat/lon box, newest publication first (then by URL, for a stable order).

    Where surveys overlap, the mosaic keeps the first valid value, so the newest survey wins.
    """
    tiles, offset = {}, 0
    while True:
        q = urllib.parse.urlencode({'datasets': LIDAR_DATASET, 'bbox': f'{west},{south},{east},{north}',
                                    'prodFormats': 'GeoTIFF', 'max': 200, 'offset': offset, 'outputFormat': 'JSON'})
        page = get_json(f'{TNM_API}?{q}')
        items = page.get('items') or []
        for it in items:
            url = it.get('downloadURL')
            m = LIDAR_URL.match(url) if isinstance(url, str) else None
            if not m:
                continue
            date = it.get('publicationDate') if isinstance(it.get('publicationDate'), str) else ''
            tiles[url] = dict(url=url, project=m.group(1), published=date[:10])
        offset += len(items)
        if not items or offset >= int(page.get('total') or 0):
            break
    return sorted(tiles.values(), key=lambda t: (t['published'], t['url']), reverse=True)


def dem10m_tiles(south, west, north, east):
    """URLs of the 1x1 degree 1/3 arc-second tiles touching a box (named by their NW corner)."""
    out = []
    for top in range(math.ceil(north), math.floor(south), -1):
        for left in range(math.floor(west), math.ceil(east)):
            ns = f'n{top:02d}' if top >= 0 else f's{-top:02d}'
            ew = f'w{-left:03d}' if left < 0 else f'e{left:03d}'
            out.append(f'{STAGED}13/TIFF/current/{ns}{ew}/USGS_13_{ns}{ew}.tif')
    return out


# --- NRCan HRDEM (british-columbia) ----------------------------------------------------------------

STAC_SEARCH = 'https://datacube.services.geo.ca/stac/api/search'
HRDEM_MOSAIC = 'hrdem-mosaic-1m'
HRDEM_PROJECTS = 'hrdem-lidar'
HRDEM_DTM = re.compile(r'https://canelevation-dem\.s3\.ca-central-1\.amazonaws\.com/hrdem-mosaic-1m/'
                       r'\d{1,3}_\d{1,3}-mosaic-1m-dtm\.tif')
PROJECT_ID = re.compile(r'[A-Za-z0-9_-]{1,100}')
MAX_PAGES = 20


def _post_json(url, body, attempts=4, delay=5.0, opener=urllib.request.urlopen):
    """POST `body` as JSON (GET when None) to the catalogue; retried, then named."""
    last = None
    for i in range(attempts):
        try:
            data = None if body is None else json.dumps(body).encode()
            headers = {'User-Agent': USER_AGENT, **({'Content-Type': 'application/json'} if data else {})}
            req = urllib.request.Request(url, data=data, headers=headers)
            with opener(req, timeout=60) as resp:
                return json.loads(resp.read(8 * 1024 * 1024))
        except Exception as e:  # network or parse failure: retried, then named
            last = e
            time.sleep(delay * (i + 1))
    raise RuntimeError(f'the NRCan catalogue did not answer after {attempts} tries: {last}')


def _search(collection, south, west, north, east, post):
    """Every feature of the catalogue's answer, following its `next` links on the catalogue's own host."""
    body = {'collections': [collection], 'bbox': [west, south, east, north], 'limit': 100}
    url, out = STAC_SEARCH, []
    for _ in range(MAX_PAGES):
        page = post(url, body)
        feats = page.get('features') if isinstance(page, dict) else None
        if not isinstance(feats, list):
            raise RuntimeError(f'the NRCan catalogue answered {collection} without features')
        out.extend(f for f in feats if isinstance(f, dict))
        nxt = next((l for l in page.get('links') or [] if isinstance(l, dict) and l.get('rel') == 'next'), None)
        if nxt is None:
            return out
        href = nxt.get('href')
        if not isinstance(href, str) or not (href == STAC_SEARCH or href.startswith(STAC_SEARCH + '?')):
            raise RuntimeError(f'the NRCan catalogue gave a next page off its own host: {href!r}')
        url, body = href, (nxt.get('body') if isinstance(nxt.get('body'), dict) else None)
    raise RuntimeError(f'the NRCan catalogue answered {collection} in more than {MAX_PAGES} pages')


def hrdem_tiles(south, west, north, east, post=None):
    """The 1 m mosaic's trusted DTM URLs meeting a lat/lon box, sorted. The mosaic covers all of Canada,
    so an answer with none is a failure ("The catalogue must answer before a cell is built empty")."""
    feats = _search(HRDEM_MOSAIC, south, west, north, east, post or _post_json)
    urls = set()
    for f in feats:
        href = ((f.get('assets') or {}).get('dtm') or {}).get('href') if isinstance(f.get('assets'), dict) else None
        if isinstance(href, str) and HRDEM_DTM.fullmatch(href):
            urls.add(href)
    if not urls:
        raise RuntimeError('the NRCan catalogue listed no mosaic tile with a trusted DTM for this frame')
    return sorted(urls)


# A place known to have NRCan lidar (Vancouver, one cell): before an empty projects answer may mean "no
# lidar", the projects search must find something here, or the catalogue is answering wrong.
PROBE_BOX = (49.25, -123.25, 49.5, -123.0)
_PROBED = False


def hrdem_probe(post=None):
    """Fail unless the projects search finds a project over PROBE_BOX; once per process."""
    global _PROBED
    if _PROBED:
        return
    if not hrdem_projects(*PROBE_BOX, post=post):
        raise RuntimeError('the NRCan catalogue lists no lidar project over Vancouver either: '
                           'its projects search is answering wrong, so no cell is built empty')
    _PROBED = True


def hrdem_projects(south, west, north, east, post=None):
    """The lidar projects meeting a lat/lon box with a valid id, sorted; others are dropped."""
    feats = _search(HRDEM_PROJECTS, south, west, north, east, post or _post_json)
    return sorted({f['id'] for f in feats if isinstance(f.get('id'), str) and PROJECT_ID.fullmatch(f['id'])})
