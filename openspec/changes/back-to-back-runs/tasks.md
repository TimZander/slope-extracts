## 1. Workflow

- [ ] 1.1 Test: the workflow is scheduled every 15 minutes and keeps its runs one at a time, seen to fail
- [ ] 1.2 `build.yml`: schedule at minutes 7, 22, 37 and 52 of every hour; comments updated

## 2. Live reads

- [ ] 2.1 Tests: every live read carries its own query string (Python and Node), seen to fail
- [ ] 2.2 `publish.py` and `deploy/pages.mjs`: a query string on every live read

## 3. Records

- [ ] 3.1 ADR 0035 (back-to-back runs); ADR 0006 marked superseded in its schedule; README updated
- [ ] 3.2 Security review and attack test of the workflow change
