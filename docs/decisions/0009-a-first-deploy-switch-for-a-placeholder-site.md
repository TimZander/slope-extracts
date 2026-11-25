---
status: accepted
date: 2026-11-24
decision-makers: the owner (a manual switch); Claude (a variable, and the guard)
---
# A one-run switch lets the first deploy replace a placeholder site

## Context and Problem Statement

The first run with building turned on stopped in its plan job: "the live manifest is not valid". The
Pages project's placeholder upload had no `404.html`, and a Pages project without one serves every
missing path with 200 and the placeholder's body (its single-page-app fallback). The pipeline needs a
404 for `manifest.json` before its first deploy, and it refuses to read anything else as "no
manifest", so it doesn't publish a site of one run's cells over a live one.

## Considered Options

- **A one-run switch, a repository variable `FIRST_DEPLOY`**, under which a non-JSON manifest on a site
  with no `404.html` reads as no manifest.
- A `workflow_dispatch` input with the same effect.
- Read a non-JSON manifest as no manifest on every run.
- The owner uploads a second placeholder with a `404.html` in the Cloudflare dashboard.

## Decision Outcome

Chosen: the variable. The owner chose a manual step over forgiving on every run, and couldn't reach
the dashboard soon. A variable keeps ADR 0007: `workflow_dispatch` takes no input, and variables are
set by the repository's admins only, like `BUILD_ENABLED` (ADR 0008). It reaches only the plan and
assemble steps, through `env:`.

The switch forgives only a body `json.loads` can't parse, and only when a path no site holds
(`/.first-deploy-probe-not-a-file`) answers 200 too. Every site the pipeline deploys has a `404.html`,
so there that probe answers 404 and the switch does nothing. The probe reads no file by name and
compares no bytes: Pages redirects `/404.html` to `/404`, and the pipeline's 404 page may change.

### Consequences

- Good, because the first deploy goes out with the credentials already in `pages-production`.
- Good, because a JSON manifest, valid or not, is read exactly as before, and a deploy that reads no
  manifest after the plan read one still fails.
- Bad, because the probe asks through the domain it guards: a domain misrouted as a whole to something
  answering 200 everywhere looks like a placeholder. So the switch is set for one run and then
  deleted; a wrong deploy is rolled back in Pages (Deployments → Rollback).

## More Information

Evidence: run 45494185143 (2026-11-24), plan job, `::error::the live manifest is not valid: Expecting
value: line 1 column 1 (char 0)`; `https://slope.timzander.com/manifest.json` and any missing path
answered `200`, `content-type: text/html`, empty body. Spec review: two rounds (design.md). Spec:
`slope-extract`, "A first deploy can replace a placeholder site".
