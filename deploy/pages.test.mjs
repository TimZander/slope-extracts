// Tests of deploy/pages.mjs: node --test deploy/ (after npm ci --ignore-scripts in deploy/).
// Spec: slope-extract, change deploy-from-hashes. A fake Cloudflare API and a fake live site run on
// localhost; nothing reaches the network.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync, spawn } from 'node:child_process'
import zlib from 'node:zlib'
import fs from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { pagesHash, contentType, runHash, runUpload } from './pages.mjs'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const SCRIPT = path.join(HERE, 'pages.mjs')
const JWT = 'eyJhbGciOiJIUzI1NiJ9.the-upload-jwt.signature'

/** A valid slope-cell file (no polygons) of cell 158_-425 and `layer`, gzip; `extra` varies the bytes. */
function cellFile (layer, extra = 0) {
  const doc = { format: 'slope-cell', version: 1, cell: '158_-425', layer, tiers: layer.startsWith('t0') ? { 0: { 30: [] } } : {} }
  return zlib.gzipSync(Buffer.from(JSON.stringify(doc) + ' '.repeat(extra)))
}

function tmp () {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'pages-test-'))
}

function write (file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, data)
}

/** A site folder of this run's files and a state folder as the assemble step writes them. */
function fixture ({ kept = {}, checks = { readback: {}, live: [] }, liveFiles = {} } = {}) {
  const root = tmp()
  const site = path.join(root, '_site')
  const state = path.join(root, '_deploy')
  write(path.join(site, 'manifest.json'), '{"m":1}\n')
  write(path.join(site, '404.html'), '<p>no</p>')
  write(path.join(site, 'LICENSE.txt'), 'public domain')
  write(path.join(site, 'colorado/158_-425/t1-4.json.gz'), Buffer.from([31, 139, 8, 0, 1, 2, 3]))
  write(path.join(state, 'kept.json'), JSON.stringify(kept))
  write(path.join(state, 'checks.json'), JSON.stringify(checks))
  write(path.join(state, '_headers'), '/*\n  X-Content-Type-Options: nosniff\n')
  for (const [name, data] of Object.entries(liveFiles)) write(path.join(state, 'live', name), data)
  return { root, site, state }
}

// Requirement: The site lists its files' hashes ("A file's hash", "A cell file's hash")
test('the Pages hash of a file', () => {
  assert.equal(pagesHash(Buffer.from('{}'), 'a.json'), 'ec47da64e7da6749028b38bc647d8a22')
  assert.equal(pagesHash(Buffer.from('{}'), 'a.json.gz'), 'c4d46c65815aef2535f97005ed44d325')
})

// Requirement: Files keep their content types
test('content types are the ones wrangler gave', () => {
  assert.equal(contentType('colorado/158_-425/t1-4.json.gz'), 'application/gzip')
  assert.equal(contentType('manifest.json'), 'application/json')
  assert.equal(contentType('404.html'), 'text/html')
  assert.equal(contentType('LICENSE.txt'), 'text/plain')
  assert.throws(() => contentType('index.js'), /content type/)
})

// Requirement: The site lists its files' hashes ("A deployed site")
test('hash writes hashes.json, the deployment manifest and the upload list', () => {
  const kept = { '/colorado/158_-425/t0-3m.json.gz': { hash: 'a'.repeat(32), bytes: 1234 } }
  const f = fixture({ kept })
  runHash({ site: f.site, state: f.state })
  const hashes = JSON.parse(fs.readFileSync(path.join(f.site, 'hashes.json')))
  assert.deepEqual(Object.keys(hashes), ['format', 'version', 'files'])
  assert.equal(hashes.format, 'slope-hashes')
  assert.equal(hashes.version, 1)
  const want = {
    '/404.html': pagesHash(Buffer.from('<p>no</p>'), '404.html'),
    '/LICENSE.txt': pagesHash(Buffer.from('public domain'), 'LICENSE.txt'),
    '/colorado/158_-425/t0-3m.json.gz': 'a'.repeat(32),
    '/colorado/158_-425/t1-4.json.gz': pagesHash(fs.readFileSync(path.join(f.site, 'colorado/158_-425/t1-4.json.gz')), 't1-4.json.gz'),
    '/manifest.json': pagesHash(Buffer.from('{"m":1}\n'), 'manifest.json')
  }
  assert.deepEqual(hashes.files, want)
  const deployment = JSON.parse(fs.readFileSync(path.join(f.state, 'deployment.json')))
  assert.deepEqual(deployment, { ...want, '/hashes.json': pagesHash(fs.readFileSync(path.join(f.site, 'hashes.json')), 'hashes.json') })
  const upload = JSON.parse(fs.readFileSync(path.join(f.state, 'upload.json')))
  const kept0 = upload.find(u => u.path === '/colorado/158_-425/t0-3m.json.gz')
  assert.deepEqual(kept0, { path: '/colorado/158_-425/t0-3m.json.gz', hash: 'a'.repeat(32), bytes: 1234, local: false, contentType: 'application/gzip' })
  assert.equal(upload.filter(u => u.local).length, 5)
})

test('the same site hashes to the same files', () => {
  const a = fixture()
  const b = fixture()
  runHash({ site: a.site, state: a.state })
  runHash({ site: b.site, state: b.state })
  assert.deepEqual(fs.readFileSync(path.join(a.site, 'hashes.json')), fs.readFileSync(path.join(b.site, 'hashes.json')))
})

// Requirement: The live hashes belong to the live manifest ("Hashes from another deployment",
// "A tile index from another deployment")
test('hash fails when a live manifest or tile index read isn\'t the one hashes.json lists', () => {
  const m = '{"live":1}\n'
  const t = '{"tile":1}\n'
  const live = [{ file: 'live/manifest.json', name: 'manifest.json', hash: pagesHash(Buffer.from(m), 'manifest.json') },
    { file: 'live/tiles/19_-54/index.json', name: 'tiles/19_-54/index.json', hash: pagesHash(Buffer.from(t), 'index.json') }]
  const liveFiles = { 'manifest.json': m, 'tiles/19_-54/index.json': t }
  const ok = fixture({ liveFiles, checks: { readback: {}, live } })
  runHash({ site: ok.site, state: ok.state })
  const badManifest = fixture({ liveFiles, checks: { readback: {}, live: [{ ...live[0], hash: 'b'.repeat(32) }, live[1]] } })
  assert.throws(() => runHash({ site: badManifest.site, state: badManifest.state }), /another deployment/)
  const badTile = fixture({ liveFiles, checks: { readback: {}, live: [live[0], { ...live[1], hash: 'b'.repeat(32) }] } })
  assert.throws(() => runHash({ site: badTile.site, state: badTile.state }), /tiles\/19_-54\/index.json/)
  const escape = fixture({ liveFiles, checks: { readback: {}, live: [{ ...live[0], file: '../kept.json' }] } })
  assert.throws(() => runHash({ site: escape.site, state: escape.state }), /live file/)
})

// Requirement: The live hashes belong to the live manifest ("A `t1-4` file that doesn't match its hash")
test('hash fails when a read-back file hashes to another value than listed', () => {
  const t14 = '/colorado/158_-425/t1-4.json.gz'
  const bad = fixture({ checks: { readback: { [t14]: 'c'.repeat(32) }, live: [] } })
  assert.throws(() => runHash({ site: bad.site, state: bad.state }), /t1-4.json.gz/)
  const unlisted = fixture({ checks: { readback: { [t14]: null }, live: [] } })
  runHash({ site: unlisted.site, state: unlisted.state })
})

test('hash refuses a kept path that is also in the folder, and a link', () => {
  const both = fixture({ kept: { '/manifest.json': { hash: 'a'.repeat(32), bytes: 1 } } })
  assert.throws(() => runHash({ site: both.site, state: both.state }), /both/)
  const link = fixture()
  fs.symlinkSync('/etc/passwd', path.join(link.site, 'x.txt'))
  assert.throws(() => runHash({ site: link.site, state: link.state }), /regular/)
})

// --- upload, against a fake Cloudflare API and a fake live site ---------------------------------

/** A fake Cloudflare API and live site. `missing` lists hashes Cloudflare lacks; `live` maps a path to
 *  bytes; `fail` maps an API path to a status it answers (once, or always with `failAlways`). */
async function fakeCloudflare ({ missing = [], live = {}, fail = {}, failAlways = false } = {}) {
  const calls = []
  const server = http.createServer((req, res) => {
    const chunks = []
    req.on('data', c => chunks.push(c))
    req.on('end', () => {
      const body = Buffer.concat(chunks).toString()
      const url = req.url
      calls.push({ url, method: req.method, auth: req.headers.authorization, body })
      if (url.startsWith('/site/')) {
        const p = url.slice('/site'.length)
        if (!(p in live)) { res.writeHead(404); return res.end() }
        res.writeHead(200)
        return res.end(live[p])
      }
      if (fail[url] && (failAlways || !calls.some(c => c.url === url && c.failed))) {
        calls[calls.length - 1].failed = true
        res.writeHead(fail[url], { 'content-type': 'application/json' })
        return res.end(JSON.stringify({ success: false, errors: [{ code: 8000000, message: 'SECRET-BODY' }] }))
      }
      res.writeHead(200, { 'content-type': 'application/json' })
      if (url === '/client/v4/pages/assets/check-missing') {
        return res.end(JSON.stringify({ success: true, result: missing }))
      }
      res.end(JSON.stringify({ success: true, result: null }))
    })
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const base = `http://127.0.0.1:${server.address().port}`
  return { calls, server, api: `${base}/client/v4`, site: `${base}/site` }
}

function jwtFile (root) {
  const f = path.join(root, 'pages-jwt')
  fs.writeFileSync(f, JWT, { mode: 0o600 })
  return f
}

function listTree (dir) {
  const out = []
  for (const e of fs.readdirSync(dir, { withFileTypes: true, recursive: true })) {
    out.push(path.join(e.parentPath ?? e.path, e.name))
  }
  return out.sort()
}

// Requirement: A deploy uploads only the files Cloudflare lacks ("Only new files")
test('upload sends exactly the missing files, typed, then confirms every hash', async () => {
  const f = fixture({ kept: { '/colorado/158_-425/t0-3m.json.gz': { hash: 'a'.repeat(32), bytes: 5 } } })
  runHash({ site: f.site, state: f.state })
  const deployment = JSON.parse(fs.readFileSync(path.join(f.state, 'deployment.json')))
  const want = [deployment['/manifest.json'], deployment['/colorado/158_-425/t1-4.json.gz']]
  const cf = await fakeCloudflare({ missing: want })
  try {
    const jwt = jwtFile(f.root)
    await runUpload({ site: f.site, state: f.state, jwtFile: jwt, api: cf.api, siteUrl: cf.site, log: () => {} })
    assert.equal(fs.existsSync(jwt), false)
    const uploads = cf.calls.filter(c => c.url === '/client/v4/pages/assets/upload')
    const sent = uploads.flatMap(c => JSON.parse(c.body))
    assert.deepEqual(sent.map(s => s.key).sort(), [...want].sort())
    const byKey = Object.fromEntries(sent.map(s => [s.key, s]))
    assert.equal(byKey[deployment['/manifest.json']].metadata.contentType, 'application/json')
    assert.equal(byKey[deployment['/colorado/158_-425/t1-4.json.gz']].metadata.contentType, 'application/gzip')
    assert.equal(Buffer.from(byKey[deployment['/manifest.json']].value, 'base64').toString(), '{"m":1}\n')
    assert.ok(sent.every(s => s.base64 === true))
    const upsert = cf.calls.find(c => c.url === '/client/v4/pages/assets/upsert-hashes')
    assert.deepEqual(JSON.parse(upsert.body).hashes.sort(), [...new Set(Object.values(deployment))].sort())
    assert.ok(cf.calls.filter(c => c.url.startsWith('/client/')).every(c => c.auth === `Bearer ${JWT}`))
    assert.equal(cf.calls.filter(c => c.url.startsWith('/site/')).length, 0)
  } finally {
    cf.server.close()
  }
})

// Requirement: A deploy uploads only the files Cloudflare lacks ("A kept file Cloudflare no longer holds",
// "A re-read leaves no file")
test('a kept file Cloudflare lacks is read back, checked and uploaded, leaving no file', async () => {
  const bytes = cellFile('t0-3m')
  const keptPath = '/colorado/158_-425/t0-3m.json.gz'
  const h = pagesHash(bytes, 't0-3m.json.gz')
  const f = fixture({ kept: { [keptPath]: { hash: h, bytes: bytes.length } } })
  runHash({ site: f.site, state: f.state })
  const cf = await fakeCloudflare({ missing: [h], live: { [keptPath]: bytes } })
  try {
    const before = listTree(f.root).filter(p => !p.endsWith('pages-jwt'))
    await runUpload({ site: f.site, state: f.state, jwtFile: jwtFile(f.root), api: cf.api, siteUrl: cf.site, log: () => {} })
    const sent = cf.calls.filter(c => c.url === '/client/v4/pages/assets/upload').flatMap(c => JSON.parse(c.body))
    assert.deepEqual(sent.map(s => s.key), [h])
    assert.deepEqual(Buffer.from(sent[0].value, 'base64'), bytes)
    const siteGet = cf.calls.find(c => c.url === `/site${keptPath}`)
    assert.equal(siteGet.auth, undefined)
    assert.deepEqual(listTree(f.root), before)
  } finally {
    cf.server.close()
  }
})

// Requirement: A deploy uploads only the files Cloudflare lacks ("A kept file changed on the live site")
test('a kept file that changed on the live site fails the upload', async () => {
  const keptPath = '/colorado/158_-425/t0-3m.json.gz'
  const old = cellFile('t0-3m')
  const changed = Buffer.from(old)
  changed[changed.length - 5] ^= 1 // the same size, other bytes
  const f = fixture({ kept: { [keptPath]: { hash: pagesHash(old, 't0-3m.json.gz'), bytes: old.length } } })
  runHash({ site: f.site, state: f.state })
  const kept = JSON.parse(fs.readFileSync(path.join(f.state, 'kept.json')))[keptPath].hash
  const cf = await fakeCloudflare({ missing: [kept], live: { [keptPath]: changed } })
  try {
    await assert.rejects(runUpload({ site: f.site, state: f.state, jwtFile: jwtFile(f.root), api: cf.api, siteUrl: cf.site, log: () => {} }), /changed/)
    assert.equal(cf.calls.filter(c => c.url === '/client/v4/pages/assets/upload').length, 0)
  } finally {
    cf.server.close()
  }
})

// Requirement: A deploy uploads only the files Cloudflare lacks ("A kept file read back too large")
test('a kept file read back over its manifest size fails the upload', async () => {
  const keptPath = '/colorado/158_-425/t0-3m.json.gz'
  const f = fixture({ kept: { [keptPath]: { hash: 'd'.repeat(32), bytes: 4 } } })
  runHash({ site: f.site, state: f.state })
  const cf = await fakeCloudflare({ missing: ['d'.repeat(32)], live: { [keptPath]: Buffer.alloc(1_000_000, 7) } })
  try {
    await assert.rejects(runUpload({ site: f.site, state: f.state, jwtFile: jwtFile(f.root), api: cf.api, siteUrl: cf.site, log: () => {} }), /over its 4 bytes/)
  } finally {
    cf.server.close()
  }
})

test('a transient 5xx is retried', async () => {
  const f = fixture()
  runHash({ site: f.site, state: f.state })
  const cf = await fakeCloudflare({ fail: { '/client/v4/pages/assets/check-missing': 502 } })
  try {
    await runUpload({ site: f.site, state: f.state, jwtFile: jwtFile(f.root), api: cf.api, siteUrl: cf.site, log: () => {}, retryDelayMs: 1 })
    assert.equal(cf.calls.filter(c => c.url === '/client/v4/pages/assets/check-missing').length, 2)
  } finally {
    cf.server.close()
  }
})

// Requirement: The upload token stays out of the log ("A failed upload")
test('a failed upload removes the token file and prints neither the token nor the answer', async () => {
  const f = fixture()
  runHash({ site: f.site, state: f.state })
  const deployment = JSON.parse(fs.readFileSync(path.join(f.state, 'deployment.json')))
  const cf = await fakeCloudflare({ missing: [deployment['/manifest.json']], fail: { '/client/v4/pages/assets/upload': 400 }, failAlways: true })
  try {
    const jwt = jwtFile(f.root)
    const child = spawn(process.execPath, [SCRIPT, 'upload', '--site', f.site, '--state', f.state, '--jwt-file', jwt], {
      env: { ...process.env, PAGES_API_BASE: cf.api, SLOPE_SITE_URL: cf.site }
    })
    let out = ''
    child.stdout.on('data', d => { out += d })
    child.stderr.on('data', d => { out += d })
    const code = await new Promise(resolve => child.on('close', resolve))
    assert.equal(code, 1)
    assert.equal(fs.existsSync(jwt), false)
    assert.ok(!out.includes(JWT) && !out.includes('the-upload-jwt'), out)
    assert.ok(!out.includes('SECRET-BODY'), out)
    assert.match(out, /400/)
  } finally {
    cf.server.close()
  }
})

test('the command line needs its arguments', () => {
  const r = spawnSync(process.execPath, [SCRIPT, 'upload'], { encoding: 'utf8' })
  assert.equal(r.status, 2)
})

// Requirement: The upload token stays out of the log (the token's file goes even when nothing uploads)
test('the token file is removed when the arguments are wrong', () => {
  const root = tmp()
  const jwt = jwtFile(root)
  const r = spawnSync(process.execPath, [SCRIPT, 'upload', '--jwt-file', jwt], { encoding: 'utf8' })
  assert.equal(r.status, 2)
  assert.equal(fs.existsSync(jwt), false)
})

// Requirement: Waits on Cloudflare are bounded ("A call that hangs")
test('a call that hangs times out, three times, and fails the upload', async () => {
  const f = fixture()
  runHash({ site: f.site, state: f.state })
  let calls = 0
  const server = http.createServer(() => { calls++ }) // never answers
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  try {
    const api = `http://127.0.0.1:${server.address().port}/client/v4`
    await assert.rejects(runUpload({ site: f.site, state: f.state, jwtFile: jwtFile(f.root), api, siteUrl: api, log: () => {}, retryDelayMs: 1, timeoutMs: 50 }), /could not be reached/)
    assert.equal(calls, 3)
  } finally {
    server.closeAllConnections()
    server.close()
  }
})

// Requirement: Waits on Cloudflare are bounded ("A hash no file has")
test('a missing hash no file of the deployment has fails the upload', async () => {
  const f = fixture()
  runHash({ site: f.site, state: f.state })
  const cf = await fakeCloudflare({ missing: ['e'.repeat(32)] })
  try {
    await assert.rejects(runUpload({ site: f.site, state: f.state, jwtFile: jwtFile(f.root), api: cf.api, siteUrl: cf.site, log: () => {} }), /no file of this deployment/)
    assert.equal(cf.calls.filter(c => c.url === '/client/v4/pages/assets/upload').length, 0)
  } finally {
    cf.server.close()
  }
})

test('a re-read asks the live site for its bytes uncompressed', async () => {
  const bytes = cellFile('t0-3m')
  const keptPath = '/colorado/158_-425/t0-3m.json.gz'
  const h = pagesHash(bytes, 't0-3m.json.gz')
  const f = fixture({ kept: { [keptPath]: { hash: h, bytes: bytes.length } } })
  runHash({ site: f.site, state: f.state })
  const seen = []
  const site = http.createServer((req, res) => { seen.push(req.headers['accept-encoding']); res.writeHead(200); res.end(bytes) })
  await new Promise(resolve => site.listen(0, '127.0.0.1', resolve))
  const cf = await fakeCloudflare({ missing: [h] })
  try {
    await runUpload({ site: f.site, state: f.state, jwtFile: jwtFile(f.root), api: cf.api, siteUrl: `http://127.0.0.1:${site.address().port}`, log: () => {} })
    assert.deepEqual(seen, ['identity'])
  } finally {
    cf.server.close()
    site.close()
  }
})

// Requirement: A deploy uploads only the files Cloudflare lacks ("A kept file re-read that isn't a cell file")
test('a kept file re-read that hashes right but is no cell file of its path fails the upload', async () => {
  const keptPath = '/colorado/158_-425/t0-3m.json.gz'
  for (const bad of [Buffer.from('not a gzip file at all'), cellFile('t1-4'), zlib.gzipSync(Buffer.from('{"format":"slope-cell","version":1,"cell":"158_-425","layer":"t0-3m","tiers":{},"x":1}'))]) {
    const f = fixture({ kept: { [keptPath]: { hash: pagesHash(bad, 't0-3m.json.gz'), bytes: bad.length } } })
    runHash({ site: f.site, state: f.state })
    const cf = await fakeCloudflare({ missing: [pagesHash(bad, 't0-3m.json.gz')], live: { [keptPath]: bad } })
    try {
      await assert.rejects(runUpload({ site: f.site, state: f.state, jwtFile: jwtFile(f.root), api: cf.api, siteUrl: cf.site, log: () => {} }), /cell-file checks/)
      assert.equal(cf.calls.filter(c => c.url === '/client/v4/pages/assets/upload').length, 0)
    } finally {
      cf.server.close()
    }
  }
})

// Requirement: Files read back from the live site are checked (the size the live manifest gives it)
test('a kept file re-read shorter than its manifest size fails the upload', async () => {
  const keptPath = '/colorado/158_-425/t0-3m.json.gz'
  const bytes = cellFile('t0-3m')
  const f = fixture({ kept: { [keptPath]: { hash: pagesHash(bytes, 't0-3m.json.gz'), bytes: bytes.length + 1 } } })
  runHash({ site: f.site, state: f.state })
  const cf = await fakeCloudflare({ missing: [pagesHash(bytes, 't0-3m.json.gz')], live: { [keptPath]: bytes } })
  try {
    await assert.rejects(runUpload({ site: f.site, state: f.state, jwtFile: jwtFile(f.root), api: cf.api, siteUrl: cf.site, log: () => {} }), /not its/)
  } finally {
    cf.server.close()
  }
})

// Requirement: The first run moves the cells onto the grid (a moved file Cloudflare lacks is read back
// from its version 1 path, the only one the live site serves)
test('a moved kept file Cloudflare lacks is read back from its old path', async () => {
  const bytes = cellFile('t0-3m')
  const h = pagesHash(bytes, 't0-3m.json.gz')
  const f = fixture({ kept: { '/cells/158_-425/t0-3m.json.gz': { hash: h, bytes: bytes.length, from: '/colorado/158_-425/t0-3m.json.gz' } } })
  runHash({ site: f.site, state: f.state })
  const cf = await fakeCloudflare({ missing: [h], live: { '/colorado/158_-425/t0-3m.json.gz': bytes } })
  try {
    await runUpload({ site: f.site, state: f.state, jwtFile: jwtFile(f.root), api: cf.api, siteUrl: cf.site, log: () => {} })
    assert.ok(cf.calls.some(c => c.url === '/site/colorado/158_-425/t0-3m.json.gz'))
    assert.ok(!cf.calls.some(c => c.url === '/site/cells/158_-425/t0-3m.json.gz'))
    const sent = cf.calls.filter(c => c.url === '/client/v4/pages/assets/upload').flatMap(c => JSON.parse(c.body))
    assert.deepEqual(sent.map(s => s.key), [h])
  } finally {
    cf.server.close()
  }
})

test('a kept file whose old path isn\'t a cell path is refused', () => {
  const f = fixture({ kept: { '/cells/158_-425/t0-3m.json.gz': { hash: 'a'.repeat(32), bytes: 5, from: '/../etc/passwd' } } })
  assert.throws(() => runHash({ site: f.site, state: f.state }), /from/)
})
