# Tasks: deploy-from-hashes

## 1. Tests first

- [ ] 1.1 Python tests for the new and changed scenarios, seen to fail: the read-back plan, `hashes.json` checks, the deploy folder and state, headers
- [ ] 1.2 Node tests, seen to fail: the hash vector, `hashes.json` and the deployment manifest, uploading only missing hashes, a kept file re-read and hash-checked, a changed one failing, the token file removed and nothing printed
- [ ] 1.3 Workflow tests: the two curl steps hold the secrets, the mask comes first, no output or environment carries the token, the one package from the lockfile

## 2. Code

- [ ] 2.1 `site.py`: `hashes.json` in the file list and headers
- [ ] 2.2 `publish.py`: read back only what is needed, write this run's files and the kept hashes
- [ ] 2.3 `deploy/pages.mjs`: `hash` and `upload`
- [ ] 2.4 `deploy/package.json` and lockfile: `blake3-wasm` 2.1.5 only
- [ ] 2.5 `build.yml`: the new deploy steps; `test.yml`: the Node tests

## 3. Records

- [ ] 3.1 ADRs: deploying from hashes (supersedes ADR 0003's deploy mechanics), the side file, the token in two curl calls, wrangler replaced by `blake3-wasm`
- [ ] 3.2 CLAUDE.md's token rule, README, docs
- [ ] 3.3 Security review and attack tests of the deploy job
