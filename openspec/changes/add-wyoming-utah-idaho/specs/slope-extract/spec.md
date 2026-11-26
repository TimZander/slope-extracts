## ADDED Requirements

### Requirement: A border cell is built for each region that covers it

A cell in the coverage of two regions SHALL be planned, built and published once for each of them:
its files under each region's folder, and an entry in each region's `cells` or `quartered`. Each
region's copy SHALL be planned from that region's own entry in the live manifest.

#### Scenario: A border cell

- **WHEN** regions `colorado` and `utah` both cover cell `152_-437`, and neither has it built
- **THEN** the run plans `colorado/152_-437` and `utah/152_-437`, the site holds
  `colorado/152_-437/t1-4.json.gz` and `utah/152_-437/t1-4.json.gz`, and both regions list the cell

#### Scenario: One region's copy is stale

- **WHEN** `utah`'s copy of a border cell is built with the current recipe and `colorado`'s with an older one
- **THEN** the run plans `colorado`'s copy only, and the deploy keeps `utah`'s files and entry as they were

### Requirement: A build job is never given the same cell twice

The plan job SHALL start a new job rather than give one job the same cell for two regions, keeping the
cells' order. The deploy job SHALL fail, publishing nothing, when a job in the plan's list names one
cell twice, for one region or for two.

#### Scenario: Two copies next to each other in the plan

- **WHEN** the cells to build are, in order, `wyoming/164_-445`, `utah/164_-445` and `utah/164_-444`
- **THEN** the run has two jobs: `wyoming/164_-445`, then `utah/164_-445 utah/164_-444`

#### Scenario: A job list with a cell twice

- **WHEN** the plan's job list gives one job `wyoming/164_-445 utah/164_-445`
- **THEN** the deploy job fails and nothing is deployed

## MODIFIED Requirements

### Requirement: A run builds missing and stale cells, at most 48

The plan job SHALL read the live site's manifest and choose, in coverage order (or the `only` list's), the
cells it lists in neither `cells` nor `quartered`, lists with another recipe number, lists as built more
than 300 days ago, or lists in `cells` with a layer left out, at most 48, in jobs of at most 3 cells.
With none to build, no build or deploy job SHALL run.

#### Scenario: A stale cell

- **WHEN** a cell was built with recipe 0 and the current recipe is 1
- **THEN** the next run builds it again

#### Scenario: The yearly refresh

- **WHEN** a cell was built 2025-11-01 and the plan runs on 2026-11-23
- **THEN** the run builds it again; on 2026-06-01 it would not have

#### Scenario: Nothing left

- **WHEN** every cell of every region is built with the current recipe
- **THEN** the run ends after the plan job

#### Scenario: A whole cell built without its 2 m layer

- **WHEN** the live manifest lists a cell in `cells`, built today with the current recipe, with its `t0-2m` left out
- **THEN** the run builds it again

#### Scenario: A split cell with a quarter's 2 m layer left out

- **WHEN** the live manifest lists a cell in `quartered`, built today with the current recipe, with one quarter's `t0-2m` left out
- **THEN** the run doesn't build it

#### Scenario: Jobs of a whole run

- **WHEN** 7 cells are to be built, none twice
- **THEN** the run has jobs of 3, 3 and 1 cells
