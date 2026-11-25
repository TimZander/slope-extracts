---
status: accepted
date: 2026-11-25
decision-makers: the owner (asked for every sdd repository to move to the plugin's current version); Claude (the update)
---
# Update sdd from 0.3.2 to 0.4.4

## Context and Problem Statement

This repository ran sdd 0.3.2. Before 0.4.3, `sdd archive verify` fails an archive commit; 0.4.4 brings spec review's pass I questions. The plugin's current version is 0.4.4.

## Considered Options

- Update with `/sdd:init`, one PR
- Stay on 0.3.2

## Decision Outcome

Chosen option: update. It refreshes `scripts/sdd/` (plus the new Azure scripts, unused here), the plugin-owned `.claude/sdd-workflow.md`, `.claude/sdd-version` and the lock file's `engines` entry.

Deletion check: every line `.claude/sdd-workflow.md` lost was plugin text reworded (the check-verdict and default-branch-tools rules now say "On GitHub", and the requirements rule notes Azure DevOps). No rule this repository added was removed. `/sdd:init` printed no warnings. `check-specs.sh --worktree` passes; no active change.
