# Design: deploy-from-hashes

## Context

- See proposal.md for why. Measured on 2026-11-26: Colorado's 144 built cells average 5.5 MB (at most
  25.7 MB); their `t1-4` files average 0.125 MB (at most 1.47 MB). The deploy of run 45750906054 spent
  4 min 7 s assembling with about 100 cells read back, then 17 s in wrangler ("Uploaded 147 files (299
  already uploaded)").
- How wrangler 3.114.17 deploys (read from its source):
  1. It gets a JWT for the project (`GET /accounts/<id>/pages/projects/<project>/upload-token`, with
     the API token).
  2. It asks which hashes are missing (`POST /pages/assets/check-missing`, with the JWT).
  3. It uploads those files as base64 with their content type (`POST /pages/assets/upload`, buckets of
     at most 40 MiB).
  4. It refreshes every hash (`POST /pages/assets/upsert-hashes`).
  5. It creates the deployment (`POST /accounts/<id>/pages/projects/<project>/deployments`, multipart:
     `manifest` JSON of `/<path>` → hash, `branch`, and `_headers` as a file).

  A file's hash is the first 32 hex digits of BLAKE3 over its base64 text followed by its extension
  (`blake3-wasm`). Content types come from `mime` 3: `.gz` → `application/gzip`, `.json` →
  `application/json`, `.html` → `text/html`, `.txt` → `text/plain`.

## Goals / Non-Goals

**Goals:** a deploy whose time and disk grow with the run's new cells, not the site; the Cloudflare
token in as little code as possible; no change for the manifest's readers.

**Non-Goals:** moving off Pages; changing the cell format or `manifest.json`; building the overview
without the `t1-4` files.

## Decisions

### The owner's (2026-11-26)

1. **Deploy from a manifest of hashes**, uploading only what Cloudflare lacks. Rejected: moving cells
   to R2, one Pages site per region, faster read-back on Pages (disk stays the ceiling).
2. **Hashes in a side file or in `manifest.json`: either.** Claude chose the side file, `hashes.json`,
   so `manifest.json`, the reader contract, keeps its form.
3. **The Cloudflare token reaches only two curl calls**: one fetches the project's upload JWT, one
   creates the deployment. Our Node script holds only the short-lived, project-scoped JWT. Rejected:
   one Node script holding the account-wide token. The owner's condition: nothing logs either token.
   - Both curl steps read the token from a header file (`-H @file`, mode 600, removed on exit) written
     with the shell's `printf` builtin, so it is on no command line.
   - curl runs with `-fsS` and `-o <file>`: no response body or header reaches the log, and an HTTP
     error prints only its status.
   - The JWT is masked with `::add-mask::` as soon as it is parsed, written to a mode-600 file under
     `$RUNNER_TEMP`, and never put in `GITHUB_OUTPUT` or `GITHUB_ENV`.

### Claude's

4. **Wrangler goes; `blake3-wasm` 2.1.5 stays** (wrangler's own hashing dependency, no dependencies of
   its own, no install script), pinned by the lockfile and installed with `npm ci --ignore-scripts` in
   a step with no secret. 105 packages become 1, and the only third-party code near the JWT is that one.
5. **Steps of the deploy job:**
   1. checkout and download the artifacts;
   2. assemble (Python, no secret): checks, read-back, this run's files into `_site/`, the kept files'
      hashes and `_headers` into `_deploy/`;
   3. install `blake3-wasm` (no secret);
   4. hash (Node, no secret): hashes `_site/`, writes `_site/hashes.json` and the deployment manifest;
   5. get the upload token (curl, the secrets);
   6. upload (Node, the JWT file only);
   7. create the deployment (curl, the secrets).
6. **A kept file Cloudflare lacks** is read back from the live site by the upload step, hashed, and
   uploaded only if the hash matches `hashes.json`. A match means the bytes are those the site
   published and checked before, so it isn't checked again; that is why "Files read back … are
   checked" covers only the reads that assemble the site. The upload step streams these reads one
   bucket (at most 40 MiB) at a time and writes none of them to disk. Cloudflare doesn't say how long
   it keeps an unreferenced asset, and runs may stop for months after the backfill.
6a. **Files read back to assemble the site** (every kept `t1-4`, and kept files `hashes.json` doesn't
   list) go into `_site/` beside this run's files and are deployed from the bytes read. The hash step
   hashes all of `_site/`, and fails when a read-back file `hashes.json` lists hashes to another value.
6b. **The live `hashes.json` must belong to the live manifest.** Both are cached five minutes and
   fetched separately, so they could come from two deployments. The assemble step keeps the live
   manifest's bytes, and the hash step checks they hash to `hashes.json`'s entry for `/manifest.json`;
   a mismatch fails the run, and the next run tries again.
6c. **Every hash of the deployment is confirmed** (`upsert-hashes`) after the upload, as wrangler does,
   which keeps kept assets fresh in Cloudflare's store.
7. **`t1-4` files are read back and checked as before**, because the overviews are built from them.
   Every other kept file is never read when its hash is listed.
8. **Migration needs no step**: with no live `hashes.json` (a 404), every kept file is read back and
   checked as today, and that run writes the first `hashes.json`.
9. **The Node tests run in the `test` workflow** (`node --test`), after `npm ci --ignore-scripts` in
   `deploy/`, against a fake Cloudflare API and a fake live site on localhost.
10. **CLAUDE.md's token rule** ("reaches only the wrangler step") is updated to the two curl steps,
    with the owner's decision.

## Open Questions

1. **How long does the upload JWT last?** Assumption: longer than one upload (wrangler fetches a new one
   only on expiry, and a run uploads a few hundred files in seconds). If it expires mid-upload, the
   upload step fails, nothing is deployed, and the next run tries again.
2. **Is Cloudflare's undocumented upload API stable?** Assumption: it is the one wrangler 3 and 4 use,
   so it changes rarely. If it breaks, the deploy fails before creating a deployment and the live site
   stays as it was; the fix is to follow wrangler's change.
3. **The spec's Purpose** still says "with its deploy credential confined to one step". A delta can't
   carry a Purpose, and the workflow forbids editing `openspec/specs/` by hand, so this change leaves it.
   Assumption: the owner decides how to correct it (a hand edit they make or allow, or leaving it as a
   known stale line); the requirements below state the two steps.

## Risks / Trade-offs

- [The API is wrangler's internal one] → open question 2; the failure mode is "nothing deployed".
- [Our code now makes the Cloudflare calls] → only the JWT reaches it; the account-wide token stays in
  two curl calls. Security review and attack tests cover both steps.
- [A kept file isn't re-checked each run] → its hash pins it to bytes a deploy checked before. A live
  file changed behind the pipeline's back is not detected while Cloudflare still holds its old hash:
  the deployment names the old hash, so the change is undone, not published. One read back (a `t1-4`,
  or one Cloudflare lacks) that hashes differently fails the deploy.
- [Cloudflare drops every kept asset, say after a year without a deploy] → the upload step reads the
  whole site back once, streamed, about the time today's deploy takes per cell; the JWT may expire on a
  long upload (open question 1), and the next run goes on from what was confirmed.
- [The first run after merge still reads the whole site back] → about 2.5 s per cell, fine at today's
  size.

## Migration Plan

Merge; the next run reads the site back once and writes `hashes.json`; later runs read back only
`t1-4` files. Rollback: revert; wrangler deploys the whole folder again, and `hashes.json` drops off
the site.

## Review rounds

- Spec review, round 1 (2026-11-26): 1 blocker (the read-back check covered the upload step's hash-only
  re-reads; now only reads that assemble the site), 10 should-fix (taken: the risk line, two scenarios'
  premises, where read-back bytes go and how they're hashed, tying `hashes.json` to the manifest,
  streaming re-reads, content types, `upsert-hashes`, replacing the old tests; the stale Purpose is
  open question 3), 5 consider (all taken).
