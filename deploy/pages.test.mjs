// Tests of deploy/pages.mjs: node --test deploy/ (after npm ci --ignore-scripts in deploy/).
// Spec: slope-extract, change deploy-from-hashes. A fake Cloudflare API and a fake live site run on
// localhost; nothing reaches the network.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync, spawn } from 'node:child_process'
import fs from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { pagesHash, contentType, runHash, runUpload } from './pages.mjs'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const SCRIPT = path.join(HERE, 'pages.mjs')
const JWT = 'eyJhbGciOiJIUzI1NiJ9.the-upload-jwt.signature'

function tmp () {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'pages-test-'))
}

function write (file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, data)
}

/** A site folder of this run's files and a state folder as the assemble step writes them. */
function fixture ({ kept = {}, checks = { manifest: null, readback: {} }, liveManifest = null } = {}) {
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
  if (liveManifest !== null) write(path.join(state, 'live-manifest.json'), liveManifest)
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

// Requirement: The live hashes belong to the live manifest ("Hashes from another deployment")
test('hash fails when the live hashes were written with another manifest', () => {
  const live = '{"live":1}\n'
  const ok = fixture({ liveManifest: live, checks: { manifest: pagesHash(Buffer.from(live), 'manifest.json'), readback: {} } })
  runHash({ site: ok.site, state: ok.state })
  const bad = fixture({ liveManifest: live, checks: { manifest: 'b'.repeat(32), readback: {} } })
  assert.throws(() => runHash({ site: bad.site, state: bad.state }), /another deployment/)
})

// Requirement: The live hashes belong to the live manifest ("A `t1-4` file that doesn't match its hash")
test('hash fails when a read-back file hashes to another value than listed', () => {
  const t14 = '/colorado/158_-425/t1-4.json.gz'
  const bad = fixture({ checks: { manifest: null, readback: { [t14]: 'c'.repeat(32) } } })
  assert.throws(() => runHash({ site: bad.site, state: bad.state }), /t1-4.json.gz/)
  const unlisted = fixture({ checks: { manifest: null, readback: { [t14]: null } } })
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
test('a kept file Cloudflare lacks is read back, hash-checked and uploaded, leaving no file', async () => {
  const bytes = Buffer.from('kept bytes')
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
    assert.equal(Buffer.from(sent[0].value, 'base64').toString(), 'kept bytes')
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
  const f = fixture({ kept: { [keptPath]: { hash: pagesHash(Buffer.from('old!'), 't0-3m.json.gz'), bytes: 4 } } })
  runHash({ site: f.site, state: f.state })
  const kept = JSON.parse(fs.readFileSync(path.join(f.state, 'kept.json')))[keptPath].hash
  const cf = await fakeCloudflare({ missing: [kept], live: { [keptPath]: Buffer.from('new!') } })
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
