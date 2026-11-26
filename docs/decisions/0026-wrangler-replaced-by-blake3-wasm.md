---
status: accepted
date: 2026-11-26
decision-makers: Claude (part of the deploy-from-hashes change, which the owner approved)
---
# Wrangler is replaced by its hashing package, `blake3-wasm` 2.1.5

## Context and Problem Statement

With the deploy made from hashes (ADR 0023), wrangler's only remaining use was its file hash: BLAKE3
over the base64 text and the extension. Python's standard library has no BLAKE3, and a pure-Python one
would take minutes per run.

## Considered Options

- `blake3-wasm` 2.1.5 alone (wrangler's own dependency; no dependencies, no install script)
- Keep wrangler 3.114.17 (105 packages) and import its hasher
- BLAKE3 in pure Python

## Decision Outcome

Chosen option: "`blake3-wasm` alone", pinned by `deploy/package-lock.json` (the same integrity hash
wrangler's lockfile had) and installed with `npm ci --ignore-scripts` in a step with no secret. 105
packages become 1, and that one is loaded only once the upload token's file is gone.

### Consequences

- Good, because far less third-party code runs in the deploy job.
- Bad, because the Pages upload is now our code (`deploy/pages.mjs`) and must follow wrangler if
  Cloudflare changes it.
