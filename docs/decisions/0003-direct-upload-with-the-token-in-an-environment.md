---
status: accepted
date: 2026-11-23
decision-makers: the owner (Direct Upload: "i dont mind api token secret being added"; project slope-extracts on slope.timzander.com); Claude (the deploy mechanics)
---
# The site is deployed by Pages Direct Upload from one step that holds the token; the token's account-wide reach is the owner's risk to take or isolate

## Context and Problem Statement

The app reads the cells cross-origin, and reads must cost nothing whatever the traffic. Colorado's cells come to ~3–4 GB, against osm-extracts' ~100 MB. Pages' Git integration (osm-extracts
ADR 0004) would put that on a GitHub branch near GitHub's 5 GB guidance, and every Pages build would clone
it within a 20-minute limit.

## Considered Options

- Direct Upload with `wrangler pages deploy`: an API token and account id as secrets
- Git integration on an orphan `data` branch, as osm-extracts (no secret)
- R2 (rejected for having no spending cap)

## Decision Outcome

Chosen option: "Direct Upload", the owner's choice. No site data sits in GitHub, and wrangler uploads only
files whose content changed, so a run uploads its own cells. The deploy job:

1. Checks this run's cell artifacts.
2. Reads every other cell back from the live site and checks each against the live manifest.
3. Writes the whole site to a folder.
4. Installs wrangler 3.114.17 (the same version as garmin-map) from `deploy/package-lock.json` with
   `npm ci --ignore-scripts`, in a step with no secret.
5. Runs `wrangler pages deploy` on the folder. This step is the only one given the secrets, through
   `env:`.

The security review replaced `cloudflare/wrangler-action`, which ran `npm i wrangler@<version>` with no
lockfile inside the step holding the token. That let any transitive dependency's install script read the
token.

The secrets `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` live in the GitHub Environment
`pages-production`, which allows deployments from `main` only. Only the deploy job names that
Environment.

**The blast radius:** Cloudflare's Pages permission (Account → Cloudflare Pages → Edit) is account-wide,
and can't be scoped to one project. A leaked token could deploy to every Pages project on the account,
maps.timzander.com (`garmin-map-builder`) and osm.timzander.com included. **A separate Cloudflare account
for slope-extracts** is the option for real isolation. It is the owner's call, not taken here.

### Consequences

- Good, because GitHub holds only code, and runs upload only what changed.
- Good, because the plan and build jobs, which read third-party data, hold no secret.
- Bad, because a token now exists that can deploy any Pages project on the account (above).
- Bad, because each deploy reads the whole live site back (up to ~4 GB from Cloudflare). That is free,
  but takes minutes.
