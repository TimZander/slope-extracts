# Tasks: add-wyoming-utah-idaho

## 1. Tests first

- [ ] 1.1 Tests for the new and changed scenarios, seen to fail: a border cell built for each region, one region's copy stale, two copies next to each other in the plan, jobs of a whole run
- [ ] 1.2 Attack tests: a plan job list naming a cell twice fails the deploy; one region's cell in two jobs fails it; two regions' copies in two jobs publish

## 2. Code and data

- [ ] 2.1 `site.py`: the plan starts a new job when the next cell is already in the current one
- [ ] 2.2 `publish.py`: the artifact check fails a planned job that names a cell twice
- [ ] 2.3 `regions.json`: Wyoming, Utah and Idaho after Colorado, with the bounds in design decision 5; a test of each region's coverage count

## 3. Records

- [ ] 3.1 ADRs: the three regions and their bounds (Idaho's whole box, Utah to 42° N), the order, border cells built per region, and each open question the owner answers
- [ ] 3.2 README: the regions
