## ADDED Requirements

### Requirement: Runs follow one another

The build workflow SHALL be scheduled every 15 minutes and SHALL run one run at a time, never cancelling
a running one. Of the runs scheduled while one runs, the newest SHALL start when it ends; older waiting
runs are dropped without starting.

#### Scenario: Reading the schedule

- **WHEN** the workflow file is read
- **THEN** its one `cron` fires every 15 minutes, and its concurrency group is one group that never cancels a run in progress

### Requirement: The pipeline reads the live site past its edge cache

Every read of the live site by the plan and deploy jobs (manifest, `hashes.json`, tile indexes, read-back
files and the check once deployed) SHALL carry a query string of its own, so the CDN's cache never
answers it and each read gets the files of the live deployment.

#### Scenario: A file the CDN still caches

- **WHEN** the CDN still holds a file of the previous deployment and the plan job reads that path
- **THEN** the request carries a query string, and the plan reads the live deployment's file

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
