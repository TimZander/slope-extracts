"""Where a cell's elevation comes from: USGS 3DEP, public domain.

- 1 m lidar DEM tiles, found through the TNM Access API and read over HTTP range requests from
  their own 2 m overviews.
- The 1/3 arc-second (~10 m) seamless DEM, where no lidar covers a pixel.

The API's answer is untrusted: only GeoTIFF URLs under the 3DEP staged-products prefix are used.
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
