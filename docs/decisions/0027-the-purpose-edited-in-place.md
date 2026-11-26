---
status: accepted
date: 2026-11-26
decision-makers: the owner ("Update the purpose", deploy-from-hashes open question 3)
---
# The spec's Purpose is edited in place for the deploy credential's two calls

## Context and Problem Statement

The slope-extract spec's Purpose said the deploy credential is "confined to one step"; after ADR 0025 it
reaches two curl calls. A delta can't carry a Purpose, and the workflow forbids hand edits to
`openspec/specs/`, so the change left it as an open question.

## Considered Options

- Edit the Purpose in place, in the change's PR, with the owner's leave
- Leave it stale

## Decision Outcome

Chosen option: "edit it in place" (the owner's). The Purpose now says "confined to two plain API calls".
The requirements check compares requirement blocks only, so it passes; no requirement changes.

### Consequences

- Good, because the spec's first lines match what it requires.
- Neutral, because a Purpose edit is the one hand edit to `openspec/specs/` made outside an archive,
  and only with the owner's say.
