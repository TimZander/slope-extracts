---
status: accepted
date: 2026-11-26
decision-makers: the owner (fix the deploy before adding regions; deploy "from a manifest"); Claude (the mechanics, read from wrangler 3.114.17's source)
---
# Deploy from a manifest of file hashes, uploading only what Cloudflare lacks

## Context and Problem Statement

Every deploy read the whole live site back to the runner, checked it, and handed the folder to
`wrangler pages deploy`: about 2.5 s per cell (run 45750906054: 4 min 7 s for about 100 cells), with
cells averaging 5.5 MB. Adding Wyoming, Utah and Idaho (2,048 cells) would take about 85 minutes,
against the deploy job's 90, and 11 to 16 GB, against the runner's 14 GB of disk (change
deploy-from-hashes). Pages builds a deployment from a manifest of `/<path>` → file hash, and uploads only hashes it
lacks; wrangler needed every file on disk only to compute those hashes.

## Considered Options

- Deploy from a manifest of hashes: hash only this run's files, take the others' hashes from the site
- Move the cells to an R2 bucket and upload only new objects
- One Pages project per region, so a deploy reads back one region
- Keep wrangler, read back faster (parallel checks, hash instead of parse, a longer timeout)

## Decision Outcome

Chosen option: "deploy from a manifest of hashes" (the owner's). The deploy job reads back only
`hashes.json`, every kept cell's `t1-4` (the overviews are built from them, about 2% of a cell's
bytes) and any kept file `hashes.json` doesn't list; it hashes this run's files, writes the new
`hashes.json`, asks Cloudflare which hashes it lacks, uploads only those, confirms every hash, and
creates the deployment from the manifest. A kept file Cloudflare no longer holds is read back and
uploaded only if it hashes to its entry. The first run after the change finds no `hashes.json` and
reads the site back once. Rejected: R2 (a new store, bucket and token; ADR 0003 rejected it for having
no spending cap), a project per region (a reader-contract change), faster read-back (the disk stays the
ceiling, around 2,000 to 2,500 cells). Supersedes ADR 0003's deploy mechanics; its Environment and the
token's account-wide reach still hold.

### Consequences

- Good, because a deploy's time and disk grow with its new cells, not the site: about 256 MB of
  `t1-4` read back at four states.
- Bad, because it uses Cloudflare's upload API as wrangler does, which Cloudflare doesn't document as
  public; if it changes, deploys fail with nothing deployed until the code follows.
- Bad, because a kept file isn't re-checked each run: its hash pins it to bytes a deploy checked before.
