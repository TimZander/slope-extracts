---
status: accepted
date: 2026-11-28
decision-makers: the owner ("make the fail-fast change for catalogue timeouts"); Claude (what trips it)
---
# A build job stops asking NRCan's catalogue once it has failed to answer

## Context and Problem Statement

About one run in ten, one of the 16 build jobs can't reach NRCan's catalogue at all while the others
reach it (runs 25, 119, 133 and 146: every request timed out). Each `hrdem` cell of that job then spent
about 9 minutes on four tries before failing, holding the run's deploy back by about 27 minutes.

## Considered Options

- Fail the job's later `hrdem` cells at once after one request goes unanswered (fail fast)
- Treat a catalogue timeout as "skipped" so the run stays green
- Stop asking the catalogue during builds: a list of mosaic tiles and project footprints in the repository

## Decision Outcome

Chosen option: "fail fast", the owner's, because it is small and keeps a real outage visible as a red
run. Only a request whose every try ends in a timeout or connection error trips it; an answer that can't
be used (over 8 MiB, a next page off the catalogue's host) fails only its own cell. The state lives for
the build process, so the next run's jobs ask again.

### Consequences

- Good, because a job that can't reach the catalogue ends in about 9 minutes instead of 27.
- Bad, because the run still turns red and sends a failure notice; the static list (option 3) would
  remove the dependency, at the cost of a refresh job.
