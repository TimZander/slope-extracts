"""Development check, not part of the published pipeline: turns cell files into a Polish .mp and a TYP
in the watch-tested v10 look, so a cell can be compiled with mkgmap and looked at.
garmin-map's slope layer owns the look; this copy only exists to check the cells.

    python tools/cell_to_mp.py <out.mp> <out.typ.txt> <cell dir> [<cell dir> ...] [--tier0 t0-3m|t0-2m]
"""
import argparse
import gzip
import json
import os

UNIT = 360.0 / (1 << 24)
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
# Dot slots never use Bayer values 6-9: those are the app's own polygons.
SLOT = {37: set(range(0, 6)), 50: {*range(0, 6), 10, 11}, 62: {*range(0, 6), *range(10, 14)}}
COLOUR = {'30': '#FFFF00', '35': '#FFAA00', '40': '#FF0000', '45': '#AA00FF', '55': '#000000'}
# (tier, class) -> (code, density, label)
STYLE = {
    (0, '30'): (0x10F01, 37, 'Slope 30-35'), (0, '35'): (0x10F02, 37, 'Slope 35-40'),
    (0, '40'): (0x10F03, 37, 'Slope 40-45'), (0, '45'): (0x10F04, 37, 'Slope 45-55'),
    (0, '55'): (0x10F05, 37, 'Cliff 55+'),
    (1, '35'): (0x10F07, 50, 'Slope 35-40'), (1, '40'): (0x10F08, 50, 'Slope 40-45'),
    (1, '45'): (0x10F09, 50, 'Slope 45-55'), (1, '55'): (0x10F0A, 62, 'Cliff 55+'),
    (2, '35'): (0x10F0C, 62, 'Slope 35-40'), (2, '40'): (0x10F0D, 62, 'Slope 40-45'), (2, '45'): (0x10F0E, 62, 'Slope 45+'),
    (3, '35'): (0x10F0C, 62, 'Slope 35-40'), (3, '40'): (0x10F0D, 62, 'Slope 40-45'), (3, '45'): (0x10F0E, 62, 'Slope 45+'),
    (4, '30'): (0x10F0F, 62, 'Slope 30+'),
}
LEVEL_BITS = [24, 23, 22, 21, 20, 19]


def rings(flat_rings):
    for flat in flat_rings:
        y, x = flat[0], flat[1]
        pts = [(y, x)]
        for i in range(2, len(flat), 2):
            y += flat[i]
            x += flat[i + 1]
            pts.append((y, x))
        yield ','.join(f'({py * UNIT:.6f},{px * UNIT:.6f})' for py, px in pts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mp')
    ap.add_argument('typ')
    ap.add_argument('cells', nargs='+')
    ap.add_argument('--tier0', default='t0-3m', choices=['t0-3m', 't0-2m'])
    ap.add_argument('--name', default='Slope check')
    args = ap.parse_args()
    out = ['[IMG ID]', 'ID=17990001', f'Name={args.name}', 'Transparent=Y', 'Routing=N', f'Levels={len(LEVEL_BITS)}',
           *[f'Level{i}={b}' for i, b in enumerate(LEVEL_BITS)], *[f'Zoom{i}={i}' for i in range(len(LEVEL_BITS))],
           'Codepage=1252', '[END-IMG ID]', '']
    n = 0
    for cdir in args.cells:
        for layer in (args.tier0, 't1-4'):
            doc = json.loads(gzip.decompress(open(os.path.join(cdir, f'{layer}.json.gz'), 'rb').read()))
            for t, classes in doc['tiers'].items():
                tier = int(t)
                for cls, polys in classes.items():
                    code = STYLE[(tier, cls)][0]
                    for p in polys:
                        out += ['[POLYGON]', f'Type=0x{code:X}', f'EndLevel={tier}',
                                *[f'Data{tier}={r}' for r in rings(p)], '[END]']
                        n += 1
    with open(args.mp, 'w', newline='\n') as fh:
        fh.write('\n'.join(out) + '\n')
    styles = {}
    for (tier, cls), (code, dens, label) in STYLE.items():
        styles[code] = (COLOUR[cls] if not (tier == 4) else COLOUR['35'], dens, label)
    typ = ['[_id]', 'FID=1799', 'ProductCode=1', 'CodePage=1252', '[end]', '', '[_drawOrder]',
           *[f'Type=0x{c:X},{i}' for i, c in enumerate(sorted(styles), start=1)], '[end]', '']
    for code, (colour, dens, label) in sorted(styles.items()):
        rows = [''.join('!' if BAYER[y % 4][x % 4] in SLOT[dens] else '.' for x in range(32)) for y in range(32)]
        typ += ['[_polygon]', f'Type=0x{code:X}', f'String1=0x04,{label}', 'Xpm="32 32 2 1"', f'"! c {colour}"',
                '". c none"', *[f'"{r}"' for r in rows], '[end]', '']
    with open(args.typ, 'w', newline='\n') as fh:
        fh.write('\n'.join(typ) + '\n')
    print(f'{n} polygons')


if __name__ == '__main__':
    main()
