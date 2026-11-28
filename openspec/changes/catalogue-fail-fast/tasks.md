## 1. Fail fast

- [ ] 1.1 Tests (the latch reset per test): after every try of one catalogue request timed out, the job's next hrdem cells fail at once without a request, naming the earlier failure, a 3dep cell still builds, and failed.json lists the hrdem cells; an oversized or off-host answer doesn't trip it; seen to fail
- [ ] 1.2 `sources.py`: remember a catalogue that never answered (timeouts, connection errors) in the process; later requests raise at once

## 2. Records

- [ ] 2.1 ADR 0039 (a build job stops asking a catalogue that failed it)
- [ ] 2.2 Conformance review recorded
