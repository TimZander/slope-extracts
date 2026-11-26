# Tasks: deploy-from-hashes

## 1. Tests first

- [x] 1.1 Python tests for the new and changed scenarios, seen to fail: the read-back plan, `hashes.json` checks, the deploy folder and state, headers
- [x] 1.2 Node tests, seen to fail: the two hash vectors, the `/manifest.json` check against `hashes.json`, a read-back file that hashes differently, the content types, the confirmation (`upsert-hashes`) of every hash, a re-read over its manifest size, no re-read left on disk, `hashes.json` and the deployment manifest, uploading only missing hashes, a kept file re-read and hash-checked, a changed one failing, the token file removed and nothing printed
- [x] 1.3 Workflow tests: the two curl steps hold the secrets, which reach curl only through header and config files and are unset first, the mask comes first, no output or environment carries the token, the one package from the lockfile; they replace `test_secrets_only_in_the_wrangler_step` and `test_wrangler_comes_from_the_lockfile_without_install_scripts`, whose requirements this change removes

## 2. Code

- [x] 2.1 `site.py`: `hashes.json` in the file list and headers
- [x] 2.2 `publish.py`: read back only what is needed, write this run's files and the kept hashes
- [x] 2.3 `deploy/pages.mjs`: `hash` and `upload`
- [x] 2.4 `deploy/package.json` and lockfile: `blake3-wasm` 2.1.5 only
- [x] 2.5 `build.yml`: the new deploy steps; `test.yml`: the Node tests

## 3. Records

- [x] 3.1 ADRs: deploying from hashes (supersedes ADR 0003's deploy mechanics), the side file, the token in two curl calls, wrangler replaced by `blake3-wasm`
- [x] 3.2 CLAUDE.md's token rule, README, docs
- [x] 3.3 Security review and attack tests of the deploy job
