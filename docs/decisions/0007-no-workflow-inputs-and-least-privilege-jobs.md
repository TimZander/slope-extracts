---
status: accepted
date: 2026-11-23
decision-makers: the owner (the concern: "if we allow a triggered run on any region then there is risk about the token being exposed?"); Claude (the model)
---
# The build workflow takes no input, every job reads only, and nothing steered from outside runs where the token is

## Context and Problem Statement

The deploy job now holds a Cloudflare token whose reach is account-wide (ADR 0003). The owner asked
whether a run triggered for any region could expose it. The workflow parses third-party data (the TNM
API, lidar GeoTIFFs) and uploads build jobs' output to the live site.

## Considered Options

- No inputs: `schedule` and `workflow_dispatch` only, every job `contents: read`, the token in an
  Environment and given to one step, all third-party output checked before that step
- A `workflow_dispatch` input naming a region or cells, validated by a fail-closed step
- Also run on `pull_request` to preview changes

## Decision Outcome

Chosen option: "no inputs". What a run builds comes only from `regions.json` on `main` and the live
manifest, so no caller can steer it. A validated input would be safe if every check held, but it is more
surface for no need: a manual run builds what is missing or stale, which is what a by-hand run is for.

In detail:
- No `pull_request_target`, `workflow_run`, push or comment trigger.
- No `${{ }}` inside `run:`; the plan's own output reaches the build step through `env:`.
- Plan and build jobs hold no secret, and the build jobs' wheels are hash-pinned.
- The deploy job takes the plan's job list through `env:` and checks every artifact before the wrangler
  step:
  - only planned `cells-<n>` artifacts, each `jobs.txt` exactly its planned list, no cell twice
  - files must be regular, at most 20 MiB, and of the exact slope-cell form, with points in the cell
  - entries are rebuilt field by field, so no unchecked key reaches the manifest
- It checks every file read back from the live site against its manifest size and form. It refuses to
  publish when the live manifest vanished after the plan read it, or when the new one would list fewer
  cells.
- Error text from artifacts is printed with control characters replaced, so it can't start a workflow
  command.

If the on-demand relay ever needs a cell input, it gets its own decision. That decision would
need its own validation step that fails closed: cell ids `^(0|-?[1-9]\d*)_(0|-?[1-9]\d*)$` within a
listed region's coverage, and region ids from an allow-list.

### Consequences

- Good, because the tests pin every property above (`tests/test_workflow.py`).
- Bad, because a by-hand run can't build one chosen cell. Editing `regions.json` (an `only` list) does
  that, through a reviewed pull request.
