# Design: skip-oversize-t0-2m

## Context

- Runs 45678249820, 45707211254 and 45731896586 (2026-11-25) failed: the build job on
  `150_-431/t0-2m is 25061558 bytes, over the 20971520-byte limit per file`, the deploy job on
  `151_-431/t0-2m unpacks to more than 67108864 bytes`. Neither cell is in the live manifest yet.
- Limits: 20 MiB per gzip file (the build job and the deploy job), 64 MiB of JSON per cell file (the
  deploy job). Cloudflare Pages caps a file at 25 MiB.
- `t0-2m` is the 2 m-detail copy of tier 0's bands; `t0-3m` holds the same classes at 3 m, so a cell
  without `t0-2m` still has every tier.

## Decisions

- **Skip the file, not the cell** (owner, 2026-11-25): option 1 of the two the owner accepted; option 2,
  splitting dense cells into quarters, is issue #10. Raising the limits was rejected (the 25 MiB cap).
- **Only `t0-2m`** (owner): an oversize `t0-3m` or `t1-4` still fails the cell, as now, because those
  layers have no finer or coarser copy to fall back on.
- **The build job also fails a cell whose `t0-3m` or `t1-4` JSON is over 64 MiB** (assumption: the owner
  said such a layer "still fails as now"; today it fails the whole deploy instead of its cell). Failing
  the cell in the build job keeps the rest of the run deploying, which is the point of this change.
- **A failed cell leaves no folder.** The build job wrote layers one by one into the cell's folder, so a
  cell that failed on a later layer left a partial folder, and the deploy job refused the whole artifact.
  That broke "A failed cell keeps its previous files" (its cell must be left out of the artifact); the
  build job now removes a failed cell's folder.
- **Decided in the build job, for both limits.** The build job already has the JSON before gzipping, so
  it checks both the gzip size and the JSON size of `t0-2m` and leaves the file out when either is over.
  The deploy job stays as strict as before: a `t0-2m` file present in an artifact must still pass every
  check, so a hostile or broken artifact can't use the skip to get an oversize file published.
- **The marker is `bytes` 0 with a zero tier 0** rather than dropping the key or adding a new key. A
  layer file is gzip and never 0 bytes, so `bytes` 0 can't mean anything else; keeping the key and tier
  `0` keeps the manifest's shape, so a reader that requires every layer key and a tier-0 count still
  reads the manifest. Rejected: dropping the `t0-2m` key (breaks such readers), a new key such as
  `absent` (a new field every reader and checker must learn, and redundant with `bytes` 0).
- **Only `t0-2m` may carry the marker**, and only in exactly the form `{"bytes": 0, "tiers": {"0":
  {"polygons": 0, "points": 0}}}`: `bytes` 0 on `t0-3m` or `t1-4`, or a `t0-2m` with `bytes` 0 and any
  other `tiers` (an empty one included), makes the entry invalid, in an artifact and in the live
  manifest.
- **The manifest's readers.** The cell format and manifest are a contract with their readers. The known
  reader (checked 2026-11-25) requires every layer key with a tier-0 count for `t0-2m`, and reads no
  `t0-2m` file, so it reads the marker as a valid entry and needs no change.

## Open questions (for the owner)

None. The marker's form was left to the builder ("zero polygons, or the repo's own absent marker").

## Rollout

The two known cells are missing from the live manifest, so the next run plans them again and publishes
them without `t0-2m`. A cell left out once is rebuilt in full by the yearly refresh or a recipe bump,
and left out again only if it is still too large.

## Review rounds

- Spec review, round 1 (2026-11-25): 0 blockers, 5 should-fix, 5 consider; all taken in the spec except
  renaming "A cell is three gzip JSON layer files" (a REMOVED plus ADDED for a name only). No round 2.

## Risks

- A reader that requests every layer of every cell gets a 404 for a left-out `t0-2m`. The site has
  no file for it by design; readers must check `bytes` first.
- Those cells lose their 2 m bands until issue #10 splits them.
