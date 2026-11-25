# Tasks: first-deploy-switch

## 1. Switch

- [x] 1.1 Tests for every scenario of both requirements (the five first-deploy ones and the deploy-side forgiven manifest), seen to fail
- [x] 1.2 `fetch_manifest(first_deploy=)`, read by the plan and the assembler from `FIRST_DEPLOY`
- [x] 1.3 `build.yml` passes `vars.FIRST_DEPLOY` to the plan and assemble steps through `env:`; a workflow guard test

## 2. Records

- [x] 2.1 ADR 0009 and the decisions index
- [x] 2.2 `docs/setup.md`: a `404.html` in the placeholder, and the switch
- [x] 2.3 A lesson in `docs/lessons.md`

## 3. First deploy

- [ ] 3.1 After merge: set `FIRST_DEPLOY=true`, run the workflow, check the live manifest, delete the variable — not done: after merge, an operation outside this PR
