## ADDED Requirements

### Requirement: A build job stops asking a catalogue that failed it

Once a catalogue request in a build job has failed all its tries, every later catalogue request in that
job SHALL fail at once, without being sent, so the job's remaining `hrdem` cells fail quickly. Each keeps
its previous files and is planned again by a later run; the job's `3dep` cells are built as usual.

#### Scenario: A job that can't reach the catalogue

- **WHEN** a build job's first `hrdem` cell fails because every catalogue request timed out, and the job has two more `hrdem` cells and one `3dep` cell
- **THEN** the two `hrdem` cells fail without a catalogue request being sent, the `3dep` cell is built, and the job lists the three `hrdem` cells as failed
