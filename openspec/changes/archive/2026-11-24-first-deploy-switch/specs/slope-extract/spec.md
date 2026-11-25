## ADDED Requirements

### Requirement: A first deploy can replace a placeholder site

While the repository variable `FIRST_DEPLOY` is exactly `true`, the plan and deploy jobs SHALL read a
live `manifest.json` that answers 200 with a body `json.loads` can't decode or parse as no manifest, and
build from scratch, but only when a path no site holds also answers 200. Otherwise such a body, and any
JSON body that isn't a valid manifest, SHALL fail the plan job.

#### Scenario: A placeholder that answers every path

- **WHEN** `FIRST_DEPLOY` is `true`, the live `manifest.json` answers 200 with an empty or HTML body, and a path no site holds answers 200 too
- **THEN** the plan job reports no manifest and plans cells from scratch, and the deploy job publishes a site of this run's cells with its own `404.html`

#### Scenario: The switch left off

- **WHEN** `FIRST_DEPLOY` is `false`, `True` or not set, and the live `manifest.json` answers 200 with an HTML body
- **THEN** the plan job fails with "the live manifest is not valid" and nothing is built

#### Scenario: The switch left on over a live site

- **WHEN** `FIRST_DEPLOY` is `true` and the live site has a valid manifest
- **THEN** the run reads it and keeps every cell it lists, as without the switch

#### Scenario: A pipeline site whose manifest answers HTML

- **WHEN** `FIRST_DEPLOY` is `true`, the live `manifest.json` answers 200 with an HTML body, and a path no site holds answers 404 (the site has a `404.html`)
- **THEN** the plan job fails with "the live manifest is not valid", and no site of this run's cells alone is published

#### Scenario: A broken manifest with the switch on

- **WHEN** `FIRST_DEPLOY` is `true` and the live `manifest.json` is JSON but not a valid manifest
- **THEN** the plan job fails with "the live manifest is not valid"

## MODIFIED Requirements

### Requirement: Files read back from the live site are checked

Each file read back from the live site SHALL be the size the live manifest gives it and pass the cell-file
checks. The deploy job SHALL fail before the wrangler step otherwise, or when:
- the live manifest is invalid, unless the first-deploy switch reads it as no manifest
- a file it lists answers 404
- it reads no manifest (a 404, or the switch) though the plan job read one
- the new manifest would list fewer cells than the live one

#### Scenario: A file changed on the live site

- **WHEN** a live cell file's size differs from the live manifest's
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: The switch forgives a manifest the plan job read

- **WHEN** the plan job read a valid manifest, and the deploy job, with `FIRST_DEPLOY` `true`, reads the manifest as none
- **THEN** the deploy job fails, and no site of this run's cells alone is published

#### Scenario: The custom domain stops answering

- **WHEN** the plan job read the live manifest but the deploy job gets a 404 for it
- **THEN** the deploy job fails, and no site of this run's cells alone is published
