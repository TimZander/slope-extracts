# Design: first-deploy-switch

## Decisions

- **A repository variable, not a workflow input.** ADR 0007 keeps `workflow_dispatch` free of
  inputs, so nothing a run's caller types steers the build. A variable is set by the repository's
  admins only, like `BUILD_ENABLED` (ADR 0008).
- **Only a non-JSON body on a site with no `404.html` is forgiven.** A placeholder's body (empty, or an
  HTML page) never parses as JSON; every manifest the pipeline publishes does. And every site the
  pipeline deploys carries a `404.html`, so a path no site holds answers 404 there; a Pages project
  with no `404.html` serves every path as 200 (its single-page-app fallback). The guard asks for
  `/.first-deploy-probe-not-a-file` and forgives only on a 200. It reads no file by name and compares no
  bytes, so it needs no redirect (Pages redirects `/404.html` to `/404`) and survives edits to the
  pipeline's 404 page (spec review round 2, D1).
- **What the guard can't catch.** It asks through the same domain it guards. A domain misrouted as a
  whole to something that answers 200 on every path would look like a placeholder, and a run would
  replace the live site with its own cells (round 2, A1). So the switch is for **one run** and is
  deleted after it (`docs/setup.md`, task 3.1); it is never "harmless to leave on". Pages keeps every
  deployment, so such a deploy is rolled back in the dashboard (Deployments → Rollback).
- **A forgiven manifest after the plan read one fails the deploy** (round 2, D2): the forgiveness lives
  in `fetch_manifest`, which returns none, so the existing check that the deploy job read a manifest
  whenever the plan job did catches it.
- **"Not JSON"** means `json.loads` fails to decode or parse the bytes (`json.JSONDecodeError` or
  `UnicodeDecodeError`). A JSON body that fails the manifest checks is never forgiven.
- **"Exactly `true`"**, as `BUILD_ENABLED` is compared; `True`, `1` or anything else is off.
- **Both jobs read the switch.** The plan job decides `had_manifest`; the deploy job reads the manifest
  again and must reach the same answer, or its 404 / invalid-manifest checks would stop it.
- **It is turned off after the first deploy.** Once the pipeline's own `404.html` is live, a missing
  manifest answers 404 again and the probe answers 404, so the switch has nothing left to do; left on,
  it would still forgive a whole-domain misroute (above), so `docs/setup.md` says to delete it.
- **Conformance review** (2026-11-24): conforms, 0 hard fails; 1 soft fail, this bullet's leftover
  "harmless", fixed here.
- **Security review** (2026-11-24, a fresh agent, on the diff): no findings. The variable reaches two
  steps through `env:` only, neither holds a secret; only admins set it. A party controlling the live
  site's answers gains nothing new: a 404 for `manifest.json` in both jobs already gave a from-scratch
  deploy, and either way only cells this run built and checked are published. The attack tests are
  the scenarios' tests (a pipeline site answering HTML, invalid JSON, a forgiven manifest after the
  plan read one, the switch in any case but `true`).

## Spec review

Round 1 (a fresh agent, 2026-11-24): 1 blocker (the deploy check's "invalid manifest" rule needed
the exception, now a MODIFIED block), 2 should-fix (the safety claim, now true through the `404.html`
guard; "exactly `true`"), 4 consider (all taken: what "not JSON" means, the plan job named, task 3.1's
reason, and the plan job's failure now specified). Round 2 follows because of the blocker.

Round 2 (2026-11-24): 0 blockers, 4 should-fix, 1 consider, all taken: the guard is a missing-path
probe, not a read of `404.html`; the deploy fails on a forgiven manifest after the plan read one; the
safety claims are narrowed to what the guard gives (one run, then delete, rollback named); task 1.1
covers every scenario. No round 3.

## Open questions

None. The owner chose a manual switch over forgiving a non-JSON manifest on every run (2026-11-24).
