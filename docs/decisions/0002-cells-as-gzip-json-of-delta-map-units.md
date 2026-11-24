---
status: accepted
date: 2026-11-23
decision-makers: Claude (measured on the Dillon pilot cell); the format is an open question to the owner in garmin-map's slope-layer change
---
# A cell is three gzip JSON layer files of delta-coded 24-bit map units

## Context and Problem Statement

The spike's Polish text for one cell was ~86 MB (all tiers at 3 m). Pages caps a file at 25 MiB, and
the app has to download and parse the data on a phone.

## Considered Options

- Gzip JSON: integer rings in 24-bit map units, first point absolute, then differences
- A varint binary, gzipped
- GeoJSON with degree coordinates
- One file per cell for all tiers, or one per tier

## Decision Outcome

Chosen option: "gzip JSON of delta map units, three layers per cell (`t0-3m`, `t0-2m`, `t1-4`)".

Measured on cell `158_-425`:

| Tier 0 at 3 m | Raw | Gzip |
|---|---|---|
| varint binary | 7.3 MB | 4.5 MB |
| JSON | 18.8 MB | 5.0 MB |

The ~10 % saving of the binary doesn't pay for a custom parser of untrusted bytes in the app. JSON
stays readable, and `JSON.parse` plus a shape check is the whole reader. Map units are what mkgmap
writes at 24 bits, so nothing the watch shows is lost. Splitting by tier 0 resolution means the app
downloads only the tier 0 it uses. Tiers 1–4 are small and shared by both.

### Consequences

- Good, because the files are 5.0 / 9.8 / 0.4 MB for the steepest pilot cell, under the 20 MiB guard.
- Good, because the same file can come from any builder that computes the same classes.
- Bad, because files must be stored gzipped (raw JSON at 2 m would be ~40 MB). The app unpacks them
  with `DecompressionStream`.
