# Tasks: skip-oversize-t0-2m

## 1. Left-out layer

- [ ] 1.1 Tests for every new and changed scenario, seen to fail, and an attack test (an artifact whose entry marks `t0-2m` left out but still holds the file, or marks another layer, or carries counts; the marker on another layer in the live manifest)
- [ ] 1.2 `build_cell.py`: leave out an oversize `t0-2m` (gzip or JSON size), warn, write the marker; fail a cell whose `t0-3m` or `t1-4` JSON is over 64 MiB; remove a failed cell's folder
- [ ] 1.3 `site.py`: the entry check allows the marker on `t0-2m` only; the file list omits a left-out layer
- [ ] 1.4 `publish.py`: the artifact check and the read-back skip a left-out layer

## 2. Records

- [ ] 2.1 ADR: skip an oversize `t0-2m`, split dense cells later (issue #10), limits not raised
- [ ] 2.2 README: a left-out layer
