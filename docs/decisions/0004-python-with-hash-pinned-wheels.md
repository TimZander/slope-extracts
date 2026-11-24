---
status: accepted
date: 2026-11-23
decision-makers: Claude
---
# The pipeline is Python; build jobs install hash-pinned wheels, and the plan and deploy jobs install nothing

## Context and Problem Statement

Slope classes need a raster library (GDAL), numpy and polygon operations. osm-extracts is Node with
built-ins only, and avoids `setup-node` because it takes the token by default.

## Considered Options

- Python with rasterio, numpy and shapely wheels, pinned by SHA-256, on the runner's own Python 3.12
- Node with GDAL bindings
- `actions/setup-python`

## Decision Outcome

Chosen option: "Python, hash-pinned wheels, runner Python", because rasterio's manylinux wheels carry
GDAL, so no system package is needed. The plan and deploy jobs use only Python's standard library, so
the job that holds the write token runs no third-party package. `--require-hashes --only-binary=:all:
--no-deps` rejects a changed or added wheel.

### Consequences

- Good, because a compromised package index can't change the build's code unnoticed.
- Bad, because `requirements.txt` holds Linux CPython 3.12 hashes only. Local work uses
  `requirements.in`, unhashed.
