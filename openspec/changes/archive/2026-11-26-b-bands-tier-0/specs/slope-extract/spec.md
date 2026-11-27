## MODIFIED Requirements

### Requirement: Slope classes are named by their lower bound

A class SHALL be named by its lower slope bound in degrees. Its upper bound SHALL be the next class's
lower bound in the same tier, or none for the tier's last class. Slope SHALL be computed from the DEM's
gradient on a UTM grid (the cell centre's NAD83 zone). Pixels with no elevation SHALL be in no class.

#### Scenario: A plane at 41 degrees

- **WHEN** a DEM is a plane sloping 41°
- **THEN** its pixels are in class `35` (35–45°) at tier 0

### Requirement: Tier 0 holds every band and the cliffs

Tier 0 SHALL hold bands `27`, `30`, `32`, `35` (35–45°), `45`, `50` (50°+) and cliffs `60`, which lie over
`50` from 60°. Cliffs
SHALL always come from the 2 m DEM (sieve 6 px, simplify 1.8 m, minimum 8 m²). Bands SHALL come from the
3 m DEM in layer `t0-3m` (sieve 10 px, simplify 2.7 m, minimum 18 m²) and, unless that layer is left
out, from the 2 m DEM in layer `t0-2m` (sieve 10 px, simplify 1.8 m, minimum 8 m²).

#### Scenario: A cone of known slopes

- **WHEN** a cell is built from a DEM of concentric rings at 28°, 31°, 33°, 37°, 42°, 47°, 53° and 62°
- **THEN** both tier-0 layers hold polygons in all seven classes, and its entry names recipe 2

#### Scenario: A plane at 62 degrees

- **WHEN** a DEM is a plane sloping 62°
- **THEN** its pixels are in band `50` and in cliffs `60` at tier 0

## ADDED Requirements

### Requirement: Tier 0's earlier classes still pass the deploy job's checks

The cell-file check SHALL also accept tier-0 classes `40` and `55`, the classes of cells built with
recipe 1, so a kept cell not yet rebuilt can be read back and deployed. Any other tier-0 class SHALL
fail it.

#### Scenario: A kept recipe-1 cell

- **WHEN** the live site holds a recipe-1 cell whose `t0-3m` and `t0-2m` files have classes `30`, `35`, `40`, `45` and `55`, and the deploy job reads it back
- **THEN** it passes the check and the deployment keeps it

#### Scenario: A tier-0 class of neither recipe

- **WHEN** a tier-0 file of a built cell holds a class `33`
- **THEN** the deploy job fails and nothing is deployed
