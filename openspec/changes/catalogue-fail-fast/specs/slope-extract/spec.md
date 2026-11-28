## ADDED Requirements

### Requirement: A build job stops asking a catalogue that failed it

Once a catalogue request in a build job has failed all 4 of its tries without an answer (each a timeout,
or a connection, name or TLS error; an HTTP error is an answer), every later catalogue request in that job SHALL fail at once, without being
sent, naming the earlier failure. The job's remaining `hrdem` cells then fail quickly, each keeping its
previous files and planned again by a later run; its `3dep` cells are built as usual. Other catalogue
failures SHALL NOT have this effect.

#### Scenario: A job that can't reach the catalogue

- **WHEN** a build job's first `hrdem` cell fails because every catalogue request timed out, and the job has two more `hrdem` cells and one `3dep` cell
- **THEN** the two `hrdem` cells fail without a catalogue request being sent, their errors say the catalogue didn't answer earlier in the job, the `3dep` cell is built, and `failed.json` lists the three `hrdem` cells

#### Scenario: An answer the job can't use

- **WHEN** a build job's first `hrdem` cell fails because the catalogue's answer was over 8 MiB, or named a next page on another host
- **THEN** the job's next `hrdem` cell still asks the catalogue
