---
status: accepted
date: 2026-11-26
decision-makers: the owner (split-dense-cells open question 4, 2026-11-26: the assumption the change proceeded on)
---
# A quarter object in the manifest holds exactly `layers`

## Context and Problem Statement

A few very steep cells build a layer file too large to publish: over 20 MiB of gzip or 64 MiB of JSON.
Cloudflare Pages caps a file at 25 MiB, so the limits stay. ADR 0013 left such a cell's `t0-2m` out as
a stop-gap; issue #10 asked to split such a cell into four 0.125° quarters instead (change
split-dense-cells). ADR 0016 gives each quarter its own `layers`. May a quarter object carry other keys?

## Considered Options

- Exactly `layers`, checked strictly, in an artifact and in the live manifest
- Extra keys allowed and ignored

## Decision Outcome

Chosen option: "exactly `layers`", so a later per-quarter field is a deliberate addition, and an
artifact or live manifest carrying anything else fails the plan or the deploy. A quartered entry's
four quarters are also exactly the cell's, qrow then qcol.

### Consequences

- Good, because nothing unchecked can ride in a quarter entry.
- Bad, because adding a per-quarter field later is a change in this repository and its readers.
