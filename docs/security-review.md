# Security review

## 2026-11-23: the build workflow before its first PR

A fresh agent reviewed `.github/workflows/build.yml`, `slope_extracts/` and `deploy/`. The threat:
the deploy job's Cloudflare token can deploy every Pages project on the account (ADR 0003), so nothing
an outsider controls may reach the step that holds it. The review was read-only, with no network: action
SHAs and the GitHub Environment settings were not checked against GitHub.

| # | Severity | Finding | Fixed by |
|---|---|---|---|
| 1 | High | `wrangler-action` ran `npm i wrangler@…` with no lockfile inside the step holding the token, so any transitive install script could read it | `deploy/package-lock.json`, installed with `npm ci --ignore-scripts` in a step with no secret, and wrangler run directly with the token in `env:` |
| 2 | Medium | A 404 on the live manifest at deploy time would publish a site of only this run's cells | The plan passes `had_manifest`; the deploy refuses a 404 after the plan saw a manifest, and a manifest with fewer cells than the live one |
| 3 | Medium | The deploy trusted each artifact's own `jobs.txt`, so a compromised build job could upload extra artifacts with any cells | The plan's job list reaches the deploy through `env:`; only planned `cells-<n>` artifacts, each with exactly its planned list, and no cell twice |
| 4 | Low | Artifact file names reached `::error::` unescaped | Control characters are replaced before printing |
| 5 | Low | `$`-anchored regexes allowed a trailing newline, and a bad date could break every later plan | `fullmatch`, dates parsed and future dates refused, `bool` refused for ints |
| 6 | Low | Extra keys in cell files and layer objects passed through to the site | Exact key sets, entries rebuilt field by field, points bounded to the cell, `X-Content-Type-Options: nosniff` |
| 7 | Low | Up to 200 MB of unpacked JSON per file, checked 8 at a time | 64 MiB cap, 2 at a time, `jobs.txt` capped at 4 KiB |
| 8 | Low | Wrangler looks for a config file in parent folders | A test fails if any `wrangler.*` exists in the repository |
| 9 | Low | The deploy relies on download-artifact rejecting `../` zip entries | `npm ci` deletes `node_modules` and checks integrity hashes, so a planted `.npmrc` or package can't change what runs |

Attack tests for each guard are in `tests/test_site_publish.py` and `tests/test_workflow.py`.
