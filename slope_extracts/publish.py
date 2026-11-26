"""The deploy job's assembler: checks this run's cell artifacts and writes the files the deployment
needs that the live site can't supply by hash.

    python -m slope_extracts.publish assemble --artifacts <dir> --out <dir> --state <dir>

<out> gets this run's cells, each tile's index and overview, manifest.json (version 2), 404.html and
LICENSE.txt, and the live files read back: every kept cell's t1-4 (the overviews are built from them)
and any kept file the live hashes.json doesn't list. <state> gets kept.json (every other kept file's
path, hash and size, and on the first run on the grid the version 1 path it is read from), checks.json
(the hashes the Node step checks the read-back files and the live manifest and tile indexes against),
those live files' bytes under live/, and _headers. deploy/pages.mjs then hashes <out>, writes
hashes.json and the deployment's manifest, and uploads what Cloudflare lacks.

It holds no credential: the Cloudflare token reaches only the two curl steps after it. It writes
changed=true|false to $GITHUB_OUTPUT; false (nothing built this run on a version 2 site, or no cell at
all) skips the deploy.

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
MAX_HASHES_BYTES = 4 * 1024 * 1024
PAGES_HASH = re.compile(r'^[0-9a-f]{32}$')
ARTIFACT = re.compile(r'^cells-(\d+)$')
JOB_CELL = re.compile(r'^-?\d+_-?\d+$')
UNSET = object()
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


def _manifest_doc(site_url, get, first_deploy, keep):
    """(True, the live manifest.json's parsed JSON), or (False, None) when the site has none yet (a 404).

    first_deploy: a manifest.json answering 200 with a body that isn't JSON is also None, when a path no
    site holds answers 200 too (a placeholder with no 404.html, never a site this pipeline deployed)."""
    status, body = get(f'{site_url}/manifest.json', MAX_MANIFEST_BYTES)
    if status == 404:
        return False, None
    try:
        doc = json.loads(body)
    except ValueError as e:
        if first_deploy and get(f'{site_url}/{PROBE_PATH}', MAX_MANIFEST_BYTES)[0] == 200:
            return False, None
        raise RuntimeError(f'the live manifest is not valid: {e}')
    keep['manifest'] = body
    return True, doc


def get_retried(get, url, limit, attempts=3, delay=1.0):
    """A read from the live site, made again (at most twice) after a network error or a 5xx answer."""
    import time
    for attempt in range(1, attempts + 1):
        try:
            return get(url, limit)
        except (RuntimeError, OSError) as e:
            transient = isinstance(e, OSError) or re.search(r' answered 5\d\d$', str(e))
            if not transient or attempt == attempts:
                raise
            time.sleep(delay * 2 ** attempt)


def fetch_live(site_url=SITE_URL, get=http_get, first_deploy=False, keep=None, workers=4, retry_delay=1.0):
    """The live site as the plan and deploy read it, or None when it has none yet:
    {'version': 1 or 2, 'manifest': doc, 'cells': {cell: entry}} and, for version 1, 'v1_paths'
    ({cell: region it is read from}), for version 2, 'tiles' ({tile: index}). Every file is checked;
    `keep` receives the bytes read ('manifest', and 'tiles' {tile: bytes}) for the hash tie."""
    keep = {} if keep is None else keep
    found, doc = _manifest_doc(site_url, get, first_deploy, keep)
    if not found:
        return None
    try:
        version = doc.get('version') if isinstance(doc, dict) else None
        if version == 1:
            site.validate_manifest(doc)
            cells, paths = site.v1_cells(doc)
            return {'version': 1, 'manifest': doc, 'cells': cells, 'v1_paths': paths}
        site.validate_manifest_v2(doc)
    except ValueError as e:
        raise RuntimeError(f'the live manifest is not valid: {e}')

    def one(t):
        status, body = get_retried(get, f'{site_url}/{site.tile_index_path(t)}', MAX_MANIFEST_BYTES, delay=retry_delay)
        if status != 200:
            raise ValueError(f'{site.tile_index_path(t)} answered {status}')
        if len(body) != doc['tiles'][t]['indexBytes']:
            raise ValueError(f'{site.tile_index_path(t)} is {len(body)} bytes, not the {doc["tiles"][t]["indexBytes"]} the manifest gives')
        return t, body

    try:
        with concurrent.futures.ThreadPoolExecutor(workers) as ex:
            bodies = dict(ex.map(one, list(doc['tiles'])))
        tiles, cells = {}, {}
        for t, body in bodies.items():
            tiles[t] = json.loads(body)
            cells.update(site.validate_tile_index(tiles[t], t, doc['tiles'][t]))
    except ValueError as e:
        raise RuntimeError(f'the live manifest is not valid: {e}')
    keep['tiles'] = bodies
    return {'version': 2, 'manifest': doc, 'cells': cells, 'tiles': tiles}


def validate_hashes(doc):
    """The live hashes.json's `files`, {"/<path>": hash}, when it is of its form; ValueError otherwise."""
    if not isinstance(doc, dict) or set(doc) != {'format', 'version', 'files'}:
        raise ValueError('it must have exactly format, version and files')
    if doc['format'] != 'slope-hashes' or doc['version'] != 1:
        raise ValueError('it is not slope-hashes version 1')
    files = doc['files']
    if not isinstance(files, dict):
        raise ValueError('files is not an object')
    for k, v in files.items():
        if not k.startswith('/') or not isinstance(v, str) or not PAGES_HASH.fullmatch(v):
            raise ValueError(f'{k!r} is not a path with a 32-digit lowercase hex hash')
    return files


def fetch_hashes(site_url=SITE_URL, get=http_get):
    """The live hashes.json's files, or None when the site has none yet (a 404)."""
    status, body = get(f'{site_url}/hashes.json', MAX_HASHES_BYTES)
    if status == 404:
        return None
    try:
        return validate_hashes(json.loads(body))
    except ValueError as e:
        raise RuntimeError(f'the live hashes.json is not valid: {e}')


def read_back(jobs, dest, site_url=SITE_URL, get=http_get, workers=2):
    """Reads each (source path, site path, cell, quarter, layer, bytes) back from the live site's source
    path into dest at its site path, checked against its entry's size and the cell-file rules."""
    def one(job):
        src, path, cell, quarter, layer, size = job
        status, body = get(f'{site_url}/{src}', MAX_FILE_BYTES)
        if status == 404:
            raise RuntimeError(f'the live site lacks {src}, which its manifest lists')
        if len(body) != size:
            raise RuntimeError(f'the live {src} is {len(body)} bytes, not the {size} its entry gives')
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


def read_artifacts(artifacts_dir, covered, plan_jobs):
    """{cell: (entry, {(quarter, layer): path})} for every cell this run built, each checked.

    `plan_jobs` is the plan job's own list, one string of cell ids per build job, each in `covered`. Artifact
    cells-<n> may exist only for a planned job n, and its jobs.txt must be that job's list exactly, so a
    build job can publish only the cells it was given. download-artifact leaves one folder per artifact;
    each holds jobs.txt, one folder per built cell, and failed.json when a cell failed.
    """
    out = {}
    if not os.path.isdir(artifacts_dir):
        return out
    planned = {}
    for n, items in enumerate(plan_jobs):
        cells = []
        for item in items.split():
            if not JOB_CELL.fullmatch(item) or item not in covered:
                raise RuntimeError(f'the plan lists {item!r}, which is not a covered cell')
            cells.append(item)
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
        if listed != planned[name]:
            raise RuntimeError(f'{label}: its jobs.txt is not the list the plan gave that job')
        jobs = planned[name]
        allowed = set(jobs) | {'jobs.txt', 'failed.json'}
        for e in os.listdir(root):
            if e not in allowed:
                raise RuntimeError(f'{label} holds {e!r}, which its job did not build')
        for cell in jobs:
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
            out[cell] = (entry, paths)
    return out


def check_cell_file(path, cell, layer, max_json=MAX_CELL_JSON, quarter=None):
    """The file is gzip JSON in the slope-cell form, for this cell (and quarter, of a split cell) and
    layer: exactly its keys, each tier only its classes, rings of integers whose points lie in the cell
    (or quarter)."""
    with open(path, 'rb') as fh:
        data = fh.read()
    check_cell_bytes(data, cell, layer, max_json, quarter)


def check_cell_bytes(data, cell, layer, max_json=MAX_CELL_JSON, quarter=None):
    """check_cell_file on a file's bytes (the upload step's re-reads, through deploy/check_cell.py)."""
    import io
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as fh:
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


def assemble(artifacts_dir, out_dir, plan_jobs, plan_had_manifest, areas=None, site_url=SITE_URL, get=http_get,
             log=print, output=None, first_deploy=False, state_dir=None, plan_manifest_version=UNSET):
    """plan_jobs / plan_had_manifest / plan_manifest_version: what the plan job saw. A deploy that finds no
    live manifest when the plan found one, or another version, fails, rather than publishing a site the
    plan didn't plan for."""
    areas = areas or site.load_areas()
    state_dir = state_dir or out_dir + '-state'
    for d in (out_dir, state_dir):
        if os.path.exists(d):
            raise RuntimeError(f'{d} already exists')
    coverage = site.site_coverage(areas)
    built = read_artifacts(artifacts_dir, set(coverage), plan_jobs)
    keep = {}
    live = fetch_live(site_url, get, first_deploy, keep)
    if live is None and plan_had_manifest:
        raise RuntimeError('the live manifest answered 404 (or the first-deploy switch read it as none), but the '
                           'plan job read one: refusing to publish a site that would drop every earlier cell')
    version = live['version'] if live else None
    if plan_manifest_version is not UNSET and plan_manifest_version != version:
        raise RuntimeError(f'the deploy read manifest version {version}, the plan job {plan_manifest_version}')
    if not built and version != 1:
        log('No cell was built this run: nothing to deploy.')
        return _out(output, False)
    covered = set(coverage)
    cells = {c: e for c, e in (live['cells'] if live else {}).items() if c in covered}
    for cell, (entry, _p) in built.items():
        cells[cell] = site.manifest_entry(entry)
    dropped = sorted(set(live['cells']) - set(cells)) if live else []
    if dropped:
        raise RuntimeError(f'the new site would leave out {len(dropped)} built cells the live one holds, '
                           f'such as {dropped[0]}: removing cells needs its own change')
    tiles = site.build_tiles(areas, cells)
    files = site.site_files(tiles)
    if len(files) > site.MAX_SITE_FILES:
        raise RuntimeError(f'the site would hold {len(files)} files, over the {site.MAX_SITE_FILES}-file limit')
    os.makedirs(out_dir)
    os.makedirs(state_dir)
    kept, checks = {}, {'readback': {}, 'live': []}
    if live is not None:
        live_hashes = fetch_hashes(site_url, get)
        listed = live_hashes or {}
        if live_hashes is not None:
            # the live files read must be the ones hashes.json was written with (the Node step checks)
            ties = [('manifest.json', keep['manifest'])] + [(site.tile_index_path(t), b) for t, b in keep.get('tiles', {}).items()]
            for name, body in ties:
                if '/' + name not in live_hashes:
                    raise RuntimeError(f'the live hashes.json lists no {name}')
                f = os.path.join(state_dir, 'live', name)
                os.makedirs(os.path.dirname(f), exist_ok=True)
                with open(f, 'wb') as fh:
                    fh.write(body)
                checks['live'].append({'file': f'live/{name}', 'name': name, 'hash': live_hashes['/' + name]})
        jobs = []
        for c, e in cells.items():
            if c in built:
                continue
            for path, q, l, size in site.files_of(c, e):
                # where the live site holds it: its cells/ path, or its version 1 path on the first run
                src = site.v1_path(live['v1_paths'][c], path) if version == 1 else path
                if l == 't1-4' or '/' + src not in listed:
                    jobs.append((src, path, c, q, l, size))
                    checks['readback']['/' + path] = listed.get('/' + src)
                else:
                    kept['/' + path] = {'hash': listed['/' + src], 'bytes': size, **({'from': '/' + src} if src != path else {})}
        fetched = read_back(jobs, out_dir, site_url, get)
        log(f'{len(fetched)} file(s) read back from the live site; {len(kept)} kept by their hash')
    for cell, (_e, paths) in built.items():
        for (q, l), p in paths.items():
            dst = os.path.join(out_dir, site.cell_path(cell, l) if q is None else site.quarter_path(cell, q, l))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(p, dst)
    # Each tile's overview from the checked t1-4 files now in out_dir; a live overview is never read back.
    sizes, overviews = {}, {}
    for t, doc in tiles.items():
        built_cells = site.tile_built(doc)
        if built_cells:
            all_cells = {**doc['cells'], **doc['quartered']}
            paths = [os.path.join(out_dir, f[0]) for c in built_cells for f in site.files_of(c, all_cells[c]) if f[2] == 't1-4']
            odoc = overview.build_tile(t, paths)
            data = overview.dumps(odoc)
            os.makedirs(os.path.join(out_dir, 'tiles', t), exist_ok=True)
            with open(os.path.join(out_dir, site.tile_overview_path(t)), 'wb') as fh:
                fh.write(data)
            overviews[t] = overview.entry(odoc, data)
        body = site.tile_index_bytes(doc)
        os.makedirs(os.path.join(out_dir, 'tiles', t), exist_ok=True)
        with open(os.path.join(out_dir, site.tile_index_path(t)), 'wb') as fh:
            fh.write(body)
        sizes[t] = len(body)
    manifest = site.build_manifest(areas, tiles, sizes, overviews)
    with open(os.path.join(out_dir, 'manifest.json'), 'w') as fh:
        fh.write(json.dumps(manifest, indent=1) + '\n')
    for name, text in (('404.html', site.NOT_FOUND_HTML), ('LICENSE.txt', site.license_text(cells))):
        with open(os.path.join(out_dir, name), 'w') as fh:
            fh.write(text)
    have = set()
    for root, _dirs, names in os.walk(out_dir):
        for n in names:
            have.add(os.path.relpath(os.path.join(root, n), out_dir).replace(os.sep, '/'))
    by_hash = {k.lstrip('/') for k in kept}
    # every file the deployment names is in the folder or kept by its hash; hashes.json comes next
    want_files = set(files) - {'hashes.json'}
    if have & by_hash or (have | by_hash) != want_files:
        raise RuntimeError(f'the site differs from its manifest: {sorted((have | by_hash) ^ want_files)[:5]}')
    for name, doc in (('kept.json', kept), ('checks.json', checks)):
        with open(os.path.join(state_dir, name), 'w') as fh:
            json.dump(doc, fh, indent=1, sort_keys=True)
    with open(os.path.join(state_dir, '_headers'), 'w') as fh:
        fh.write(site.HEADERS)
    log(f'Site assembled: {len(built)} cell(s) built this run, {len(files)} files'
        + (' (moved onto the grid from version 1)' if version == 1 else '') + '.')
    return _out(output, True)


# How long the check once deployed waits for the deployment to go live, and between its reads.
LIVE_WAIT_SECONDS = 600
LIVE_READ_INTERVAL = 20
ROLL_BACK = 'roll back to the previous deployment in the Cloudflare dashboard if the site is broken'


def verify_live(site_dir, site_url=SITE_URL, get=http_get, sleep=None, clock=None,
                wait=LIVE_WAIT_SECONDS, interval=LIVE_READ_INTERVAL):
    """The check once deployed ("The deploy job checks the live site once deployed"): with no credential,
    read the live manifest until it is the one in `site_dir` (at most `wait` seconds), then check it and
    every tile index as the plan job does, the live hashes.json against the deployed one, and in each
    tile one file of its first built cell that has one. Raises RuntimeError naming what failed."""
    import time
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    with open(os.path.join(site_dir, 'manifest.json'), 'rb') as fh:
        deployed = fh.read()
    with open(os.path.join(site_dir, 'hashes.json'), 'rb') as fh:
        deployed_hashes = fh.read()
    deadline = clock() + wait
    while True:
        status, body = get_retried(get, f'{site_url}/manifest.json', MAX_MANIFEST_BYTES)
        if status == 200 and body == deployed:
            break
        if clock() >= deadline:
            raise RuntimeError(f'the live manifest.json is not the one deployed after {wait} s; {ROLL_BACK}')
        sleep(interval)
    live = fetch_live(site_url, get)
    if live is None or live['version'] != 2:
        raise RuntimeError(f'the live manifest.json is not the version 2 one deployed; {ROLL_BACK}')
    status, body = get_retried(get, f'{site_url}/hashes.json', MAX_HASHES_BYTES)
    if status != 200 or body != deployed_hashes:
        raise RuntimeError(f'the live hashes.json is not the one deployed; {ROLL_BACK}')
    checked = 0
    for t in live['tiles']:
        built = sorted((c for c in live['cells'] if grid.tile_of(c) == t), key=grid.parse_cell)
        cell = next((c for c in built if site.files_of(c, live['cells'][c])), None)
        if cell is None:
            continue
        files = site.files_of(cell, live['cells'][cell])
        path, quarter, layer, size = min(files, key=lambda f: f[3])
        status, data = get_retried(get, f'{site_url}/{path}', size)
        if status != 200:
            raise RuntimeError(f'{path} answered {status} on the live site; {ROLL_BACK}')
        if len(data) != size:
            raise RuntimeError(f'{path} is {len(data)} bytes on the live site, not its {size}; {ROLL_BACK}')
        try:
            check_cell_bytes(data, cell, layer, quarter=quarter)
        except RuntimeError as e:
            raise RuntimeError(f'{path} on the live site: {e}; {ROLL_BACK}')
        checked += 1
    return checked


def _out(output, changed):
    path = output or os.environ.get('GITHUB_OUTPUT')
    if path:
        with open(path, 'a') as fh:
            fh.write(f'changed={"true" if changed else "false"}\n')
    return changed


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['assemble', 'verify'])
    ap.add_argument('--artifacts')
    ap.add_argument('--out')
    ap.add_argument('--state')
    ap.add_argument('--site')
    args = ap.parse_args(argv)
    if args.action == 'verify':
        if not args.site:
            ap.error('verify needs --site')
        try:
            n = verify_live(args.site)
        except (RuntimeError, ValueError, OSError) as e:
            print(f'::error::{safe(str(e))}', file=sys.stderr)
            return 1
        print(f'The live site is the deployment: its manifest, every tile index and {n} cell file(s) checked.')
        return 0
    if not args.artifacts or not args.out:
        ap.error('assemble needs --artifacts and --out')
    try:
        jobs = json.loads(os.environ.get('PLAN_JOBS', ''))
        if not isinstance(jobs, list) or not all(isinstance(j, str) for j in jobs):
            raise ValueError('PLAN_JOBS is not a list of strings')
        had = os.environ.get('PLAN_HAD_MANIFEST')
        if had not in ('true', 'false'):
            raise ValueError('PLAN_HAD_MANIFEST is not true or false')
        versions = {'1': 1, '2': 2, 'none': None}
        if os.environ.get('PLAN_MANIFEST_VERSION') not in versions:
            raise ValueError('PLAN_MANIFEST_VERSION is not 1, 2 or none')
        assemble(args.artifacts, args.out, jobs, had == 'true', first_deploy=first_deploy_on(), state_dir=args.state,
                 plan_manifest_version=versions[os.environ['PLAN_MANIFEST_VERSION']])
    except (RuntimeError, ValueError, OSError) as e:
        print(f'::error::{safe(str(e))}', file=sys.stderr)
        return 1
    return 0


def safe(text):
    """One line with no control characters, so text from an artifact can't start a workflow command."""
    return ''.join(ch if ch.isprintable() else '?' for ch in text)


if __name__ == '__main__':
    sys.exit(main())
