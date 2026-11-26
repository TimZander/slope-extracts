"""The 0.25-degree cell grid, shared with TimZander/osm-extracts.

A cell id is "<row>_<col>" with row = floor(lat * 4) and col = floor(lon * 4), so cell 158_-425
covers 39.50-39.75 N, 106.25-106.00 W. Coordinates in cell files are Garmin map units at 24 bits
(360 / 2**24 degrees), the finest resolution mkgmap writes, so the app's Polish text compiles to
exactly the points the pipeline chose.
"""
import math
import re

CELL_DEG = 0.25
UNITS_PER_DEG = (1 << 24) / 360.0
CELL_ID = re.compile(r'^(0|-?[1-9]\d*)_(0|-?[1-9]\d*)$')


def parse_cell(cell_id):
    m = CELL_ID.match(cell_id)
    if not m:
        raise ValueError(f'{cell_id!r} is not a cell id')
    row, col = int(m.group(1)), int(m.group(2))
    if not (-360 <= row < 360 and -720 <= col < 720):
        raise ValueError(f'{cell_id!r} is outside the globe')
    return row, col


def cell_bounds(cell_id):
    """(south, west, north, east) in degrees."""
    row, col = parse_cell(cell_id)
    return row * CELL_DEG, col * CELL_DEG, (row + 1) * CELL_DEG, (col + 1) * CELL_DEG


def cell_of(lat, lon):
    return f'{math.floor(lat * 4)}_{math.floor(lon * 4)}'


def cells_in_bounds(south, west, north, east):
    """Every cell a bounds box touches, in row then column order."""
    rows = range(math.floor(south * 4), math.ceil(north * 4))
    cols = range(math.floor(west * 4), math.ceil(east * 4))
    return [f'{r}_{c}' for r in rows for c in cols]


def utm_epsg(cell_id):
    """NAD83 / UTM zone of the cell's centre (EPSG:269xx), valid for the conterminous US."""
    south, west, north, east = cell_bounds(cell_id)
    zone = math.floor(((west + east) / 2 + 180) / 6) + 1
    if not 10 <= zone <= 19:
        raise ValueError(f'cell {cell_id} is in UTM zone {zone}, outside the NAD83 zones 10-19 this pipeline knows')
    return f'EPSG:269{zone:02d}'


def to_units(deg):
    return round(deg * UNITS_PER_DEG)


def from_units(units):
    return units / UNITS_PER_DEG


def quarters(cell_id):
    """A cell's four 0.125-degree quarters, "<qrow>_<qcol>" with qrow = floor(lat * 8) and qcol =
    floor(lon * 8), in row then column order (south-west first), as cells are ordered."""
    row, col = parse_cell(cell_id)
    return [f'{2 * row + i}_{2 * col + j}' for i in (0, 1) for j in (0, 1)]


def quarter_bounds(cell_id, quarter):
    """(south, west, north, east) in degrees of one of the cell's quarters: the cell cut at its middle."""
    qs = quarters(cell_id)
    if quarter not in qs:
        raise ValueError(f'{quarter!r} is not a quarter of cell {cell_id}')
    i, j = divmod(qs.index(quarter), 2)
    south, west, north, east = cell_bounds(cell_id)
    ym, xm = (south + north) / 2, (west + east) / 2
    return (south, ym)[i], (west, xm)[j], (ym, north)[i], (xm, east)[j]


def compare_key(cell_id):
    return parse_cell(cell_id)
