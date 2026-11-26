## ADDED Requirements

### Requirement: Runs follow one another

The build workflow SHALL be scheduled every 15 minutes and SHALL run one run at a time, never cancelling
a running one, so a run scheduled while another runs starts when that one ends.

#### Scenario: A run scheduled during a run

- **WHEN** a scheduled run starts while a 40-minute run is still building
- **THEN** it waits, and starts when that run ends, with nothing cancelled that had started

#### Scenario: Reading the schedule

- **WHEN** the workflow file is read
- **THEN** its one `cron` fires four times an hour, and its concurrency group never cancels a run in progress

## MODIFIED Requirements

### Requirement: Runs wait until the owner turns building on

The build workflow's plan job SHALL run only when the repository variable `BUILD_ENABLED` is `true`.
Until then every run SHALL skip all its jobs and build, read and deploy nothing, so a repository
merged before its Cloudflare project and secrets exist doesn't fail on every scheduled run.

#### Scenario: Before setup

- **WHEN** a scheduled run starts and `BUILD_ENABLED` isn't set
- **THEN** the plan, build and deploy jobs are skipped and the run ends without failing

#### Scenario: After setup

- **WHEN** the owner has set `BUILD_ENABLED` to `true`
- **THEN** the plan job runs as before
