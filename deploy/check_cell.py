"""The cell-file checks for a file the upload step read back from the live site.

    python3 -I deploy/check_cell.py /<region>/<cell>[/<quarter>]/<layer>.json.gz  < bytes

Exits 0 when the bytes are exactly the slope-cell file of that path's cell (and quarter) and layer, by
the deploy job's own checks (slope_extracts.publish.check_cell_bytes); 1 otherwise, printing only a
fixed message. Standard library only; it is never given a token.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slope_extracts import grid, publish, site  # noqa: E402

PATH = re.compile(r'^/([a-z0-9]+(?:-[a-z0-9]+)*)/(-?\d+_-?\d+)(?:/(-?\d+_-?\d+))?/(t0-3m|t0-2m|t1-4)\.json\.gz$')


def main(argv):
    m = PATH.fullmatch(argv[0]) if len(argv) == 1 else None
    if not m:
        raise SystemExit('check_cell.py: not a cell file path')
    _region, cell, quarter, layer = m.groups()
    try:
        grid.parse_cell(cell)
        if quarter is not None and quarter not in grid.quarters(cell):
            raise ValueError('not a quarter of the cell')
        if layer not in site.LAYERS:
            raise ValueError('not a layer')
        publish.check_cell_bytes(sys.stdin.buffer.read(publish.MAX_FILE_BYTES + 1), cell, layer, quarter=quarter)
    except (ValueError, RuntimeError):
        raise SystemExit(f'check_cell.py: {argv[0]} fails the cell-file checks')


if __name__ == '__main__':
    main(sys.argv[1:])
