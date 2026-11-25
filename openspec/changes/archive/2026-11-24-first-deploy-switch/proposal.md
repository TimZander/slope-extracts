# Proposal: first-deploy-switch

## Why

The first scheduled run with building turned on failed in its plan job: "the live manifest is not
valid". The project's placeholder deployment has no `404.html`, so Cloudflare Pages serves every
missing path, `manifest.json` included, as a 200 with the placeholder's body. The pipeline expects a
404 there before its first deploy, and rightly refuses to read anything else as "no manifest".

Asking the owner to upload a second placeholder by hand works, but needs the Cloudflare dashboard. A
switch the owner (or an agent on the owner's behalf) sets for one run gets the first deploy out with
the credentials already in the `pages-production` Environment.

## What Changes

- A repository variable `FIRST_DEPLOY`. While it is `true`, the plan and deploy jobs read a live
  `manifest.json` whose body isn't JSON as no manifest, and the run builds from scratch, but only on a
  site with no `404.html` (one the pipeline never deployed: a missing path answers 200).
- A body that is JSON is read as a manifest exactly as before, and a site the pipeline deployed answers
  404 for a missing path, so it isn't forgiven. The switch is set for one run and deleted after it.
  Without the switch nothing changes.
- `docs/setup.md`: the placeholder upload includes a `404.html`, and the switch is described for a
  placeholder that lacks one.

## Impact

- `.github/workflows/build.yml`, `slope_extracts/publish.py`, `slope_extracts/site.py`, tests,
  `docs/setup.md`, ADR 0009.
