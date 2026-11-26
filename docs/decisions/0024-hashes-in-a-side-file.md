---
status: accepted
date: 2026-11-26
decision-makers: the owner (the hashes in a side file or the manifest, "either"); Claude (the side file)
---
# The files' hashes live in a side file, `hashes.json`, not in `manifest.json`

## Context and Problem Statement

ADR 0023 deploys from file hashes, so the site must record each file's Pages hash for the next deploy.
`manifest.json` is the contract its readers rely on.

## Considered Options

- A side file, `hashes.json`: `format` `slope-hashes`, `version` 1, `files` of `/<path>` → hash
- A `hash` key on each layer in `manifest.json`

## Decision Outcome

Chosen option: "a side file", because `manifest.json` and its readers don't change, and only the deploy
job reads it. It lists every file of the deployment but itself and `_headers`, including
`/manifest.json`, so the deploy checks the two files come from the same deployment (both are cached
five minutes) and fails otherwise.

### Consequences

- Good, because the reader contract is untouched.
- Bad, because the site holds one more file to keep consistent with the manifest; a mismatch fails a
  run, and the next run tries again.
