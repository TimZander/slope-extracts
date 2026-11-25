## ADDED Requirements

### Requirement: Each region has an overview of its built cells' tier 4

A region with a built cell SHALL have `<region>/overview.json.gz`: gzip JSON with exactly the keys
`format` `slope-overview`, `version` 1, `region`, and `tiers` holding only tier `4`, class `30`: the tier-4
polygons of every built cell of the region, cells in coverage order, each cell's polygons in its
`t1-4` file's order, rings encoded as in a cell. A region with no built cell SHALL have no overview.

#### Scenario: Two built cells

- **WHEN** a region has two built cells, with 3 and 5 tier-4 polygons
- **THEN** its overview holds 8 polygons in class `30` of tier `4`, the first cell's 3 first

#### Scenario: The same cells give the same bytes

- **WHEN** the overview is written twice from the same cell files
- **THEN** both are byte for byte the same

#### Scenario: No built cell

- **WHEN** a region has no built cell
- **THEN** the site holds no overview for it

### Requirement: The deploy job writes the overview from the cells it publishes

The deploy job SHALL write each overview from the `t1-4` files it is about to publish, after their
checks, and SHALL never read an overview back from the live site. It SHALL fail before the wrangler
step when an overview's file would be over 20 MiB or its JSON over 64 MiB, the limits of a cell file.

#### Scenario: A run adds a cell

- **WHEN** a run builds one more cell of a region
- **THEN** the deployed overview holds that cell's tier-4 polygons with the others'

#### Scenario: An overview too large

- **WHEN** an overview's gzip file would be 21 MiB
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: A live manifest's overview entry

- **WHEN** the live manifest gives a region an `overview` entry with any value
- **THEN** the plan and deploy jobs accept it, use none of it, and write the new entry from the new overview

### Requirement: The manifest gives each region's overview

A region's manifest entry SHALL hold `overview` when the region has one, giving the overview's `bytes`,
`polygons` and `points`, counted as a cell tier's, and no `overview` when it has none.

#### Scenario: The overview's entry

- **WHEN** a region's overview is 1,200 bytes with 8 polygons of 90 points
- **THEN** the region's `overview` is `{"bytes": 1200, "polygons": 8, "points": 90}`

## MODIFIED Requirements

### Requirement: The site sets its CORS and cache headers

`_headers` SHALL send `Access-Control-Allow-Origin: *` and `X-Content-Type-Options: nosniff` on every path,
and one `Cache-Control` per path:
one day for cell files (`/<region>/<cell>/…`), an hour for `LICENSE.txt` and overview files, five
minutes for `manifest.json`.
A missing path SHALL answer from `404.html`.

#### Scenario: Reading the headers file

- **WHEN** `_headers` is read
- **THEN** no path matches two rules that set `Cache-Control`

#### Scenario: The overview's cache

- **WHEN** `_headers` is read
- **THEN** `/colorado/overview.json.gz` matches one rule, which caches it for an hour, and
  `/colorado/158_-425/t1-4.json.gz` matches one, which caches it for a day

### Requirement: Deploying adds to the live site

The deploy job SHALL write the whole site to a folder: this run's cells, every other cell the live
manifest lists (read back from the live site), each region's overview, the new manifest, `_headers`,
`404.html` and `LICENSE.txt`.
It SHALL upload it with `wrangler pages deploy` to project `slope-extracts`. A run that built no cell SHALL
deploy nothing.

#### Scenario: A second run

- **WHEN** a run builds one more cell
- **THEN** the deployed site holds both cells' files and a manifest listing both

#### Scenario: Nothing built

- **WHEN** every cell of a run failed
- **THEN** nothing is deployed, and the live site stays as it was
