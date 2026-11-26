#!/usr/bin/env node
// The deploy job's Cloudflare Pages upload, from the repository (never from an artifact).
//
//   node deploy/pages.mjs hash   --site <dir> --state <dir>                   no secret
//   node deploy/pages.mjs upload --site <dir> --state <dir> --jwt-file <file> the upload JWT only
//
// `hash` hashes this run's folder as Pages does, checks the files read back and the live manifest
// against the live hashes.json (via <state>/checks.json), and writes <site>/hashes.json,
// <state>/deployment.json (Cloudflare's deployment manifest, "/<path>" -> hash) and
// <state>/upload.json. `upload` asks Cloudflare which hashes it lacks, uploads only those (a kept
// file it lacks is read back from the live site and sent only if it hashes to its entry), and
// confirms every hash. The deployment itself is created by a curl step, the only other place the
// Cloudflare token goes. This follows the upload wrangler 3.114.17 makes (src/pages/upload.tsx).
//
// Only blake3-wasm, from deploy/package-lock.json, is imported; the rest is Node's own.
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
let blake3 // loaded on first use, so a failed load can't come before the token's file is removed

const API = 'https://api.cloudflare.com/client/v4'
const SITE_URL = 'https://slope.timzander.com'
const MAX_BUCKET_BYTES = 40 * 1024 * 1024 // wrangler's MAX_BUCKET_SIZE
const MAX_BUCKET_FILES = 2000 // wrangler's MAX_BUCKET_FILE_COUNT
const TIMEOUT_MS = 120_000
const ATTEMPTS = 3
const HASH = /^[0-9a-f]{32}$/
// wrangler's content types (mime 3) for the files this site holds
const TYPES = { gz: 'application/gzip', json: 'application/json', html: 'text/html', txt: 'text/plain' }

/** The Pages hash: the first 32 hex digits of BLAKE3 over the base64 text and the extension. */
export function pagesHash (bytes, name) {
  const extension = path.posix.extname(name).substring(1)
  blake3 ??= require('blake3-wasm').hash
  return blake3(Buffer.from(bytes).toString('base64') + extension).toString('hex').slice(0, 32)
}

export function contentType (name) {
  const type = TYPES[path.posix.extname(name).substring(1)]
  if (!type) throw new Error(`${name} has no content type this site serves`)
  return type
}

function readJson (file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'))
}

/** Every file under `dir`, as "a/b.json" paths; anything but a regular file or folder is refused. */
function walk (dir, rel = '') {
  const out = []
  for (const name of fs.readdirSync(path.join(dir, rel)).sort()) {
    const r = rel ? `${rel}/${name}` : name
    const st = fs.lstatSync(path.join(dir, r))
    if (st.isDirectory()) out.push(...walk(dir, r))
    else if (st.isFile()) out.push(r)
    else throw new Error(`${r} is not a regular file`)
  }
  return out
}

function sortedObject (obj) {
  return Object.fromEntries(Object.keys(obj).sort().map(k => [k, obj[k]]))
}

export function runHash ({ site, state }) {
  const kept = readJson(path.join(state, 'kept.json'))
  const checks = readJson(path.join(state, 'checks.json'))
  if (fs.existsSync(path.join(site, 'hashes.json'))) throw new Error('the site folder already holds hashes.json')
  const files = {}
  const upload = []
  for (const rel of walk(site)) {
    const p = `/${rel}`
    if (p in kept) throw new Error(`${p} is both in the folder and kept by its hash`)
    const data = fs.readFileSync(path.join(site, rel))
    files[p] = pagesHash(data, rel)
    upload.push({ path: p, hash: files[p], bytes: data.length, local: true, contentType: contentType(rel) })
  }
  for (const [p, e] of Object.entries(kept)) {
    if (!HASH.test(e.hash) || !Number.isInteger(e.bytes) || e.bytes < 0) throw new Error(`${p} has no valid hash and size`)
    files[p] = e.hash
    upload.push({ path: p, hash: e.hash, bytes: e.bytes, local: false, contentType: contentType(p) })
  }
  // Read-back files must be the bytes the live hashes.json describes, and it the live manifest's.
  for (const [p, want] of Object.entries(checks.readback)) {
    if (!(p in files)) throw new Error(`${p} was read back but isn't in the folder`)
    if (want !== null && files[p] !== want) throw new Error(`${p} read back hashes to ${files[p]}, not the ${want} hashes.json gives`)
  }
  if (checks.manifest !== null) {
    const live = fs.readFileSync(path.join(state, 'live-manifest.json'))
    if (pagesHash(live, 'manifest.json') !== checks.manifest) {
      throw new Error('the live hashes.json belongs to another deployment than the live manifest; the next run tries again')
    }
  }
  const listed = sortedObject(files)
  const doc = Buffer.from(JSON.stringify({ format: 'slope-hashes', version: 1, files: listed }, null, 1) + '\n')
  fs.writeFileSync(path.join(site, 'hashes.json'), doc)
  const own = pagesHash(doc, 'hashes.json')
  upload.push({ path: '/hashes.json', hash: own, bytes: doc.length, local: true, contentType: 'application/json' })
  const deployment = sortedObject({ ...listed, '/hashes.json': own })
  fs.writeFileSync(path.join(state, 'deployment.json'), JSON.stringify(deployment, null, 1) + '\n')
  upload.sort((a, b) => a.path < b.path ? -1 : 1)
  fs.writeFileSync(path.join(state, 'upload.json'), JSON.stringify(upload, null, 1) + '\n')
  return deployment
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

/** A POST to Cloudflare's assets API with the JWT; a network error or 5xx is retried. Nothing of an
 *  answer but its status and error codes ever reaches an error message. */
async function apiCall (api, jwt, route, body, retryDelayMs, timeoutMs) {
  for (let attempt = 1; ; attempt++) {
    let res
    try {
      res = await fetch(`${api}${route}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: `Bearer ${jwt}` },
        body: JSON.stringify(body),
        redirect: 'error',
        signal: AbortSignal.timeout(timeoutMs)
      })
    } catch (e) {
      if (attempt < ATTEMPTS) { await sleep(retryDelayMs * 2 ** attempt); continue }
      throw new Error(`${route} could not be reached (${e.name})`)
    }
    if (res.status >= 500 && attempt < ATTEMPTS) {
      await res.body?.cancel()
      await sleep(retryDelayMs * 2 ** attempt)
      continue
    }
    if (!res.ok) {
      await res.body?.cancel()
      throw new Error(`${route} answered ${res.status}`)
    }
    let doc
    try { doc = await res.json() } catch { throw new Error(`${route} answered with no JSON`) }
    if (doc?.success !== true) {
      const codes = Array.isArray(doc?.errors) ? doc.errors.map(e => Number(e?.code) || 0).join(', ') : ''
      throw new Error(`${route} refused the call (error codes ${codes || 'none'})`)
    }
    return doc.result
  }
}

const CHECKER = path.join(path.dirname(fileURLToPath(import.meta.url)), 'check_cell.py')

/** A kept file read back from the live site, uncompressed (as the Python reader asks): it must be its
 *  manifest size, hash to its hashes.json entry and pass the deploy's cell-file checks (the live site
 *  is hostile: its manifest and hashes.json could agree on any bytes). A network error or 5xx, body
 *  included, is retried. */
async function readBack (siteUrl, item, retryDelayMs, timeoutMs) {
  for (let attempt = 1; ; attempt++) {
    let data
    try {
      data = await readOnce(siteUrl, item, timeoutMs)
    } catch (e) {
      if (e.retry && attempt < ATTEMPTS) { await sleep(retryDelayMs * 2 ** attempt); continue }
      throw e
    }
    if (data.length !== item.bytes) throw new Error(`${item.path} on the live site is ${data.length} bytes, not its ${item.bytes}`)
    if (pagesHash(data, item.path) !== item.hash) throw new Error(`${item.path} changed on the live site: it doesn't hash to its hashes.json entry`)
    const check = spawnSync('python3', ['-I', CHECKER, item.path], { input: data, stdio: ['pipe', 'ignore', 'ignore'], timeout: 120_000 })
    if (check.status !== 0) throw new Error(`${item.path} read back fails the cell-file checks`)
    return data
  }
}

async function readOnce (siteUrl, item, timeoutMs) {
  const retry = message => Object.assign(new Error(message), { retry: true })
  let res
  try {
    res = await fetch(`${siteUrl}${item.path}`, {
      headers: { 'accept-encoding': 'identity' },
      redirect: 'error',
      signal: AbortSignal.timeout(timeoutMs)
    })
  } catch (e) {
    throw retry(`${item.path} could not be read back (${e.name})`)
  }
  if (res.status !== 200) {
    await res.body?.cancel()
    if (res.status >= 500) throw retry(`${item.path} answered ${res.status} on the live site`)
    throw new Error(`${item.path} answered ${res.status} on the live site`)
  }
  const chunks = []
  let size = 0
  try {
    for await (const chunk of res.body) {
      size += chunk.length
      if (size > item.bytes) {
        await res.body.cancel().catch(() => {})
        throw Object.assign(new Error(`${item.path} on the live site is over its ${item.bytes} bytes`), { final: true })
      }
      chunks.push(chunk)
    }
  } catch (e) {
    if (e.final) throw e
    throw retry(`${item.path} broke off while being read back (${e.name})`)
  }
  return Buffer.concat(chunks)
}

export async function runUpload ({ site, state, jwtFile, api = API, siteUrl = SITE_URL, log = console.log, retryDelayMs = 1000, timeoutMs = TIMEOUT_MS }) {
  let jwt
  try {
    jwt = fs.readFileSync(jwtFile, 'utf8').trim()
  } finally {
    fs.rmSync(jwtFile, { force: true }) // the token's file is gone however the upload ends
  }
  const deployment = readJson(path.join(state, 'deployment.json'))
  const items = readJson(path.join(state, 'upload.json'))
  const hashes = [...new Set(Object.values(deployment))].sort()
  const missing = await apiCall(api, jwt, '/pages/assets/check-missing', { hashes }, retryDelayMs, timeoutMs)
  if (!Array.isArray(missing)) throw new Error('check-missing answered no list')
  const lacking = new Set(missing)
  const todo = []
  const seen = new Set()
  for (const item of items) {
    if (lacking.has(item.hash) && !seen.has(item.hash)) { todo.push(item); seen.add(item.hash) }
  }
  for (const h of lacking) if (!seen.has(h)) throw new Error(`Cloudflare lacks ${h}, which no file of this deployment has`)
  // buckets of at most 40 MiB and 2,000 files, read (or read back) one at a time and then dropped
  const buckets = []
  for (const item of todo) {
    const b = buckets.at(-1)
    if (b && b.bytes + item.bytes <= MAX_BUCKET_BYTES && b.items.length < MAX_BUCKET_FILES) {
      b.items.push(item)
      b.bytes += item.bytes
    } else buckets.push({ items: [item], bytes: item.bytes })
  }
  for (const b of buckets) {
    const payload = []
    for (const item of b.items) {
      const data = item.local ? fs.readFileSync(path.join(site, item.path)) : await readBack(siteUrl, item, retryDelayMs, timeoutMs)
      if (item.local && pagesHash(data, item.path) !== item.hash) throw new Error(`${item.path} changed since it was hashed`)
      payload.push({ key: item.hash, value: data.toString('base64'), metadata: { contentType: item.contentType }, base64: true })
    }
    await apiCall(api, jwt, '/pages/assets/upload', payload, retryDelayMs, timeoutMs)
  }
  await apiCall(api, jwt, '/pages/assets/upsert-hashes', { hashes }, retryDelayMs, timeoutMs)
  log(`Uploaded ${todo.length} file(s); Cloudflare already held ${hashes.length - todo.length} of the deployment's ${hashes.length}.`)
}

function args (argv, names) {
  const out = {}
  for (let i = 0; i < argv.length; i += 2) {
    const name = argv[i]?.replace(/^--/, '')
    if (!names.includes(name) || argv[i + 1] === undefined) return null
    out[name] = argv[i + 1]
  }
  return names.every(n => n in out) ? out : null
}

/** The token's file named on the command line, removed whatever else happens to the run. */
function removeJwtFile (argv) {
  const i = argv.indexOf('--jwt-file')
  if (argv[0] === 'upload' && i > 0 && argv[i + 1]) fs.rmSync(argv[i + 1], { force: true })
}

async function main (argv) {
  const [command, ...rest] = argv
  if (command === 'hash') {
    const a = args(rest, ['site', 'state'])
    if (!a) return usage()
    runHash(a)
    console.log('Hashed the site.')
    return 0
  }
  if (command === 'upload') {
    const a = args(rest, ['site', 'state', 'jwt-file'])
    if (!a) return usage()
    await runUpload({
      site: a.site,
      state: a.state,
      jwtFile: a['jwt-file'],
      api: process.env.PAGES_API_BASE || API,
      siteUrl: process.env.SLOPE_SITE_URL || SITE_URL
    })
    return 0
  }
  return usage()
}

function usage () {
  console.error('usage: pages.mjs hash --site <dir> --state <dir> | upload --site <dir> --state <dir> --jwt-file <file>')
  return 2
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const argv = process.argv.slice(2)
  main(argv).finally(() => removeJwtFile(argv)).then(code => { process.exitCode = code }, err => {
    // only our own messages: no answer body, no token
    console.error(`::error::${String(err.message).replace(/[^\x20-\x7e]/g, '?')}`)
    process.exitCode = 1
  })
}
