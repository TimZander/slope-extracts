---
status: accepted
date: 2026-11-26
decision-makers: the owner (the curl route, on condition nothing logs either token); Claude (how the secrets reach curl)
---
# The Cloudflare token reaches only two curl calls; the upload token is masked and passed in a file

## Context and Problem Statement

Deploying from hashes (ADR 0023) means our code makes the Cloudflare calls wrangler made. The account-wide
token used to reach only wrangler's step (ADR 0003). The owner asked whether curl would log it.

## Considered Options

- The token only in two curl calls: one fetches a short-lived upload token for the project, one creates
  the deployment; our Node script holds only the upload token
- One Node script holding the token for every call

## Decision Outcome

Chosen option: "two curl calls" (the owner's). In each step, shell builtins (`printf`) write the token
into curl's header file and the account id into its config file (mode 600, removed on exit), then
`unset` both before any program runs: no command line or child environment holds them. curl runs
`-fsS` with `-o`, so no answer reaches the log. `deploy/cf_answer.py` reads the answer afterwards: it
masks the upload token with `::add-mask::` before writing it to a mode-600 file, never a step output or
the environment; the upload step removes that file whatever happens. GitHub masks the stored secrets in
logs as well. Attack tests run both steps' own shell with a fake curl and check none of this leaks.

### Consequences

- Good, because the account-wide token never meets our code or a third-party package.
- Good, because the code near the upload token is ours and one locked package (ADR 0026).
- Bad, because the deploy now spans five steps, and CLAUDE.md's rule changed with them.
