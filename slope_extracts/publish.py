"""The deploy job's assembler: checks this run's cell artifacts, reads the previous site back from the
live site, and writes the whole new site to a folder, which `wrangler pages deploy` uploads (Pages'
Direct Upload sends only files whose content changed).

    python -m slope_extracts.publish assemble --artifacts <dir> --out <dir>

It holds no credential: the Cloudflare token is given only to the wrangler step after it. It writes
changed=true|false to $GITHUB_OUTPUT; false (nothing built this run, or no cell at all) skips the
deploy.

Standard library only.
"""
import argparse
import concurrent.futures
import gzip
import json
import os
import re
import shutil
import stat
import sys
import urllib.error
import urllib.request

from . import grid, overview, site

SITE_URL = os.environ.get('SLOPE_SITE_URL', 'https://slope.timzander.com')
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
ARTIFACT = re.compile(r'^cells-(\d+)$')
JOB_CELL = re.compile(r'^([a-z0-9]+(?:-[a-z0-9]+)*)/(-?\d+_-?\d+)$')
USER_AGENT = 'slope-extracts deploy (https://github.com/TimZander/slope-extracts)'


def http_get(url, limit, timeout=120):
    """(status, body) of a GET without redirects; a 404 is (404, b''). Raises on other failures."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'})
    try:
        with opener.open(req, timeout=timeout) as r:
            body = r.read(limit + 1)
            if len(body) > limit:
                raise RuntimeError(f'{url} is over {limit} bytes')
            return r.status, body
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return 404, b''
        raise RuntimeError(f'{url} answered {e.code}')


# A path no site holds. A site the pipeline deployed has a 404.html, so this answers 404 there; a Pages
# project without one (the owner's placeholder) answers every path with 200.
PROBE_PATH = '.first-deploy-probe-not-a-file'


def first_deploy_on(env=None):
    """The first-deploy switch: the repository variable FIRST_DEPLOY, on only when exactly 'true'."""
    return (os.environ if env is None else env).get('FIRST_DEPLOY') == 'true'


def fetch_manifest(site_url=SITE_URL, get=http_get, first_deploy=False):
    """The live site's manifest, or None when it has none yet (404).

    first_deploy: a manifest.json answering 200 with a body that isn't JSON is also None, when a path no
    site holds answers 200 too (a placeholder with no 404.html, never a site this pipeline deployed)."""
    status, body = get(f'{site_url}/manifest.json', MAX_MANIFEST_BYTES)
    if status == 404:
        return None
    try:
        doc = json.loads(body)
    except ValueError as e:
        if first_deploy and get(f'{site_url}/{PROBE_PATH}', MAX_MANIFEST_BYTES)[0] == 200:
            return None
        raise RuntimeError(f'the live manifest is not valid: {e}')
    try:
        return site.validate_manifest(doc)
    except ValueError as e:
        raise RuntimeError(f'the live manifest is not valid: {e}')


def fetch_previous(manifest, dest, skip, site_url=SITE_URL, get=http_get, workers=2):
    """Downloads every file the previous manifest lists, except cells in `skip` ({(region, cell)}),
    into dest, each checked against its manifest size and the cell-file rules. Returns the paths."""
    jobs = []
    for r in manifest['regions']:
        for c, e in site.region_cells(r).items():
            if (r['id'], c) in skip:
                continue
            # a split cell's quarter files; a left-out layer has no file to read back
            for path, quarter, l, size in site.files_of(r['id'], c, e):
                jobs.append((path, c, quarter, l, size))

    def one(job):
        path, cell, quarter, layer, size = job
        status, body = get(f'{site_url}/{path}', MAX_FILE_BYTES)
        if status == 404:
            raise RuntimeError(f'the live site lacks {path}, which its manifest lists')
        if len(body) != size:
            raise RuntimeError(f'the live {path} is {len(body)} bytes, not the {size} its manifest says')
        out = os.path.join(dest, path)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'wb') as fh:
            fh.write(body)
        check_cell_file(out, cell, layer, quarter=quarter)
        return path

    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        return list(ex.map(one, jobs))


def _regular(path):
    return stat.S_ISREG(os.lstat(path).st_mode)


TIER_CLASSES = {'0': {'30', '35', '40', '45', '55'}, '1': {'35', '40', '45', '55'}, '2': {'35', '40', '45'},
                '3': {'35', '40', '45'}, '4': {'30'}}
MAX_JOBS_TXT = 4096
MAX_CELL_JSON = 64 * 1024 * 1024


def read_artifacts(artifacts_dir, regions, plan_jobs):
    """{(region, cell): (entry, {layer: path})} for every cell this run built, each checked.

    `plan_jobs` is the plan job's own list, one string of "<region>/<cell>" items per build job. Artifact
    cells-<n> may exist only for a planned job n, and its jobs.txt must be that job's list exactly, so a
    build job can publish only the cells it was given. download-artifact leaves one folder per artifact;
    each holds jobs.txt, one folder per built cell, and failed.json when a cell failed.
    """
    by_id = {r['id']: r for r in regions}
    out = {}
    if not os.path.isdir(artifacts_dir):
        return out
    planned = {}
    for n, items in enumerate(plan_jobs):
        cells = []
        for item in items.split():
            m = JOB_CELL.fullmatch(item)
            if not m or m.group(1) not in by_id or m.group(2) not in set(site.coverage(by_id[m.group(1)])):
                raise RuntimeError(f'the plan lists {item!r}, which is not a cell of a listed region')
            cells.append((m.group(1), m.group(2)))
        planned[f'cells-{n}'] = cells
    all_cells = [c for cells in planned.values() for c in cells]
    if len(set(all_cells)) != len(all_cells):
        raise RuntimeError('the plan lists a cell twice')
    for name in sorted(os.listdir(artifacts_dir)):
        root = os.path.join(artifacts_dir, name)
        if name not in planned or os.path.islink(root) or not os.path.isdir(root):
            raise RuntimeError(f'the artifacts hold {name!r}, which is not a planned cells artifact')
        label = f'artifact {name}'
        # download-artifact puts each of several artifacts in a folder of its name, and the job
        # uploaded a folder of that name too: unwrap cells-<n>/cells-<n>/ to the inner one
        inner = os.listdir(root)
        if inner == [name] and os.path.isdir(os.path.join(root, name)) and not os.path.islink(os.path.join(root, name)):
            root = os.path.join(root, name)
        jobs_file = os.path.join(root, 'jobs.txt')
        if not os.path.exists(jobs_file) or not _regular(jobs_file) or os.path.getsize(jobs_file) > MAX_JOBS_TXT:
            raise RuntimeError(f'{label} has no jobs.txt of at most {MAX_JOBS_TXT} bytes')
        listed = open(jobs_file, encoding='utf-8', errors='replace').read().split()
        if listed != [f'{r}/{c}' for r, c in planned[name]]:
            raise RuntimeError(f'{label}: its jobs.txt is not the list the plan gave that job')
        jobs = {c: r for r, c in planned[name]}
        allowed = set(jobs) | {'jobs.txt', 'failed.json'}
        for e in os.listdir(root):
            if e not in allowed:
                raise RuntimeError(f'{label} holds {e!r}, which its job did not build')
        for cell, region in jobs.items():
            cdir = os.path.join(root, cell)
            if not os.path.lexists(cdir):
                continue  # the cell failed; its previous files stay
            if os.path.islink(cdir) or not os.path.isdir(cdir):
                raise RuntimeError(f'{label}: {cell} is not a folder')
            # entry.json first: it says whether the cell is split and which layers have a file
            ep = os.path.join(cdir, 'entry.json')
            if not os.path.lexists(ep) or not _regular(ep):
                raise RuntimeError(f'{label}: {cell}/entry.json is not a regular file')
            if os.path.getsize(ep) > MAX_FILE_BYTES:
                raise RuntimeError(f'{label}: {cell}/entry.json is over the {MAX_FILE_BYTES}-byte limit')
            try:
                with open(ep) as fh:
                    entry = site.validate_entry(json.load(fh), cell)
            except (ValueError, json.JSONDecodeError) as e:
                raise RuntimeError(f'{label}: {cell}/entry.json is not valid: {e!r}')
            if site.is_split(entry):
                # exactly entry.json and the four quarter folders, real folders, each its present layers
                folders = {q: (os.path.join(cdir, q), site.present_layers(qe)) for q, qe in entry['quarters'].items()}
                want = {'entry.json', *folders}
            else:
                folders = {None: (cdir, site.present_layers(entry))}
                want = {'entry.json', *(f'{l}.json.gz' for l in folders[None][1])}
            have = set(os.listdir(cdir))
            if have != want:
                raise RuntimeError(f'{label}: {cell} holds {sorted(have)!r}, not exactly {sorted(want)}')
            paths = {}
            for q, (fdir, present) in folders.items():
                where = cell if q is None else f'{cell}/{q}'
                if q is not None:
                    if os.path.islink(fdir) or not os.path.isdir(fdir):
                        raise RuntimeError(f'{label}: {where} is not a folder')
                    qwant = {f'{l}.json.gz' for l in present}
                    qhave = set(os.listdir(fdir))
                    if qhave != qwant:
                        raise RuntimeError(f'{label}: {where} holds {sorted(qhave)!r}, not exactly {sorted(qwant)}')
                sizes = (entry['layers'] if q is None else entry['quarters'][q]['layers'])
                for l in present:
                    p = os.path.join(fdir, f'{l}.json.gz')
                    if not _regular(p):
                        raise RuntimeError(f'{label}: {where}/{l}.json.gz is not a regular file')
                    if os.path.getsize(p) > MAX_FILE_BYTES:
                        raise RuntimeError(f'{label}: {where}/{l}.json.gz is over the {MAX_FILE_BYTES}-byte limit')
                    check_cell_file(p, cell, l, quarter=q)
                    if sizes[l]['bytes'] != os.path.getsize(p):
                        raise RuntimeError(f'{label}: {where}/{l} size differs from its entry')
                    paths[(q, l)] = p
            out[(region, cell)] = (entry, paths)
    return out


def check_cell_file(path, cell, layer, max_json=MAX_CELL_JSON, quarter=None):
    """The file is gzip JSON in the slope-cell form, for this cell (and quarter, of a split cell) and
    layer: exactly its keys, each tier only its classes, rings of integers whose points lie in the cell
    (or quarter)."""
    try:
        with gzip.open(path, 'rb') as fh:
            raw = fh.read(max_json + 1)
        if len(raw) > max_json:
            raise RuntimeError(f'{cell}/{layer} unpacks to more than {max_json} bytes')
        doc = json.loads(raw)
    except (OSError, EOFError, ValueError) as e:
        raise RuntimeError(f'{cell}/{layer} is not gzip JSON: {e!r}')
    keys = {'format', 'version', 'cell', 'layer', 'tiers'} | ({'quarter'} if quarter is not None else set())
    if (not isinstance(doc, dict) or set(doc) != keys
            or doc['format'] != 'slope-cell' or doc['version'] != 1 or doc['cell'] != cell or doc['layer'] != layer
            or (quarter is not None and doc['quarter'] != quarter)):
        raise RuntimeError(f'{cell}/{layer} is not the slope-cell file for this cell, quarter and layer')
    tiers = doc['tiers']
    allowed = {'0'} if layer.startswith('t0') else {'1', '2', '3', '4'}
    if not isinstance(tiers, dict) or not set(tiers) <= allowed:
        raise RuntimeError(f'{cell}/{layer} has tiers {sorted(tiers) if isinstance(tiers, dict) else tiers!r}')
    south, west, north, east = grid.cell_bounds(cell) if quarter is None else grid.quarter_bounds(cell, quarter)
    y0, y1 = grid.to_units(south) - 2, grid.to_units(north) + 2
    x0, x1 = grid.to_units(west) - 2, grid.to_units(east) + 2
    for t, classes in tiers.items():
        if not isinstance(classes, dict):
            raise RuntimeError(f'{cell}/{layer} tier {t} is not an object')
        for b, polys in classes.items():
            if b not in TIER_CLASSES[t] or not isinstance(polys, list):
                raise RuntimeError(f'{cell}/{layer} tier {t} has class {b!r}')
            for p in polys:
                if not isinstance(p, list) or not p:
                    raise RuntimeError(f'{cell}/{layer}: a polygon has no rings')
                for ring in p:
                    if (not isinstance(ring, list) or len(ring) < 6 or len(ring) % 2
                            or not all(type(v) is int for v in ring)):
                        raise RuntimeError(f'{cell}/{layer}: a ring is malformed')
                    y, x = ring[0], ring[1]
                    for i in range(0, len(ring), 2):
                        if i:
                            y += ring[i]
                            x += ring[i + 1]
                        if not (y0 <= y <= y1 and x0 <= x <= x1):
                            raise RuntimeError(f'{cell}/{layer}: a point lies outside the {"cell" if quarter is None else "quarter"}')


def assemble(artifacts_dir, out_dir, plan_jobs, plan_had_manifest, regions=None, site_url=SITE_URL, get=http_get,
             log=print, output=None, first_deploy=False):
    """plan_jobs / plan_had_manifest: what the plan job saw. A deploy that finds no live manifest when the
    plan found one fails, rather than publishing a site of this run's cells alone."""
    regions = regions or site.load_regions()
    if os.path.exists(out_dir):
        raise RuntimeError(f'{out_dir} already exists')
    built = read_artifacts(artifacts_dir, regions, plan_jobs)
    if not built:
        log('No cell was built this run: nothing to deploy.')
        return _out(output, False)
    previous = fetch_manifest(site_url, get, first_deploy)
    if previous is None and plan_had_manifest:
        raise RuntimeError('the live manifest answered 404 (or the first-deploy switch read it as none), but the '
                           'plan job read one: refusing to publish a site that would drop every earlier cell')
    cells = {r['id']: {} for r in regions}
    for r in (previous or {}).get('regions', []):
        if r['id'] in cells:
            covered = set(site.coverage(next(x for x in regions if x['id'] == r['id'])))
            cells[r['id']].update({c: e for c, e in site.region_cells(r).items() if c in covered})
    for (region, cell), (entry, _p) in built.items():
        cells[region][cell] = site.manifest_entry(entry)
    manifest = site.build_manifest(regions, cells)
    files = site.site_files(manifest)
    if len(files) > site.MAX_SITE_FILES:
        raise RuntimeError(f'the site would hold {len(files)} files, over the {site.MAX_SITE_FILES}-file limit')
    os.makedirs(out_dir)
    if previous is not None:
        fetched = fetch_previous(manifest, out_dir, set(built), site_url, get)
        live_cells = sum(len(site.region_cells(r)) for r in previous['regions'])
        new_cells = sum(len(site.region_cells(r)) for r in manifest['regions'])
        if new_cells < live_cells:
            raise RuntimeError(f'the new manifest lists {new_cells} cells, fewer than the live {live_cells}')
        log(f'{len(fetched)} file(s) read back from the live site')
    for (region, cell), (_e, paths) in built.items():
        for (q, l), p in paths.items():
            dst = os.path.join(out_dir, site.layer_path(region, cell, l) if q is None else site.quarter_path(region, cell, q, l))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(p, dst)
    # Each overview from the checked cell files now in out_dir; a live overview is never read back.
    for r in manifest['regions']:
        # cells in coverage order; a split cell's four t1-4 quarters, row then column order
        cells_r = site.region_cells(r)
        paths = [os.path.join(out_dir, f[0]) for c in r['coverage'] if c in cells_r
                 for f in site.files_of(r['id'], c, cells_r[c]) if f[2] == 't1-4']
        doc = overview.build(r['id'], paths)
        if doc is not None:
            data = overview.dumps(doc)
            with open(os.path.join(out_dir, site.overview_path(r['id'])), 'wb') as fh:
                fh.write(data)
            r['overview'] = overview.entry(doc, data)
    with open(os.path.join(out_dir, 'manifest.json'), 'w') as fh:
        fh.write(json.dumps(manifest, indent=1) + '\n')
    for name, text in (('_headers', site.HEADERS), ('404.html', site.NOT_FOUND_HTML), ('LICENSE.txt', site.license_text(manifest))):
        with open(os.path.join(out_dir, name), 'w') as fh:
            fh.write(text)
    have = set()
    for root, _dirs, names in os.walk(out_dir):
        for n in names:
            have.add(os.path.relpath(os.path.join(root, n), out_dir).replace(os.sep, '/'))
    if have != set(files):
        raise RuntimeError(f'the site folder differs from its manifest: {sorted(have ^ set(files))[:5]}')
    log(f'Site assembled: {len(built)} cell(s) built this run, {len(files)} files.')
    return _out(output, True)


def _out(output, changed):
    path = output or os.environ.get('GITHUB_OUTPUT')
    if path:
        with open(path, 'a') as fh:
            fh.write(f'changed={"true" if changed else "false"}\n')
    return changed


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['assemble'])
    ap.add_argument('--artifacts', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args(argv)
    try:
        jobs = json.loads(os.environ.get('PLAN_JOBS', ''))
        if not isinstance(jobs, list) or not all(isinstance(j, str) for j in jobs):
            raise ValueError('PLAN_JOBS is not a list of strings')
        had = os.environ.get('PLAN_HAD_MANIFEST')
        if had not in ('true', 'false'):
            raise ValueError('PLAN_HAD_MANIFEST is not true or false')
        assemble(args.artifacts, args.out, jobs, had == 'true', first_deploy=first_deploy_on())
    except (RuntimeError, ValueError, OSError) as e:
        print(f'::error::{safe(str(e))}', file=sys.stderr)
        return 1
    return 0


def safe(text):
    """One line with no control characters, so text from an artifact can't start a workflow command."""
    return ''.join(ch if ch.isprintable() else '?' for ch in text)


if __name__ == '__main__':
    sys.exit(main())
