## ADDED Requirements

### Requirement: The site lists its files' hashes

Each deploy SHALL write `hashes.json`: JSON with exactly `format` `slope-hashes`, `version` 1, and
`files` mapping every file of the deployment but itself and `_headers`, as `/<path>`, to its Pages
hash: the first 32 lowercase hex digits of the BLAKE3 hash of the file's base64 text followed by its
extension, the text after its name's last dot.

#### Scenario: A file's hash

- **WHEN** the site holds `a.json` with the two bytes `{}`
- **THEN** `hashes.json` maps `/a.json` to `ec47da64e7da6749028b38bc647d8a22`

#### Scenario: A cell file's hash

- **WHEN** the site holds `a.json.gz` with the two bytes `{}`
- **THEN** `hashes.json` maps `/a.json.gz` to `c4d46c65815aef2535f97005ed44d325`, hashed with extension `gz`

#### Scenario: A deployed site

- **WHEN** a run deploys a site of one cell
- **THEN** `hashes.json` lists that cell's three files, its region's overview, `manifest.json`,
  `404.html` and `LICENSE.txt`, each with its hash, and nothing else

### Requirement: A deploy reads back only what it needs

The deploy job SHALL read back from the live site `hashes.json`, the kept cells' `t1-4` files (for the
overviews) and each kept file `hashes.json` doesn't list, and deploy them from the bytes read; it SHALL
take every other kept file's hash from `hashes.json` unread. With no live manifest it SHALL read no
`hashes.json`; one answering 404 SHALL list nothing. A kept cell is one the new manifest lists and
this run didn't build.

#### Scenario: A run after a run

- **WHEN** the live site holds one cell and its `hashes.json`, Cloudflare holds every kept hash, and a run builds another cell
- **THEN** the deploy job requests from the live site `manifest.json`, `hashes.json` and the first
  cell's `t1-4` file only, and the deployment names both cells' files

#### Scenario: The first run after this change

- **WHEN** the live site holds one cell and no `hashes.json`, and a run builds another cell
- **THEN** the deploy job reads back and checks all three of the first cell's files, as before, and
  the new `hashes.json` lists both cells' files

#### Scenario: A hash not of its form

- **WHEN** the live `hashes.json` maps a kept file to `"zz"`
- **THEN** the deploy job fails and nothing is deployed

### Requirement: The live hashes belong to the live manifest

The deploy job SHALL fail, creating no deployment, when the live `hashes.json` is over 4 MiB, not its
keys, format, version and `/<path>` → hash entries, or answers other than 200 or 404; when its
`/manifest.json` entry isn't the read manifest's hash; or when a file read back hashes to another entry
it gives. It SHALL ignore entries for paths it doesn't keep, and read back kept paths with none.

#### Scenario: Hashes from another deployment

- **WHEN** the live `hashes.json` was written with an older manifest than the live one
- **THEN** the deploy job fails and no deployment is created

#### Scenario: A `t1-4` file that doesn't match its hash

- **WHEN** a kept cell's `t1-4` file reads back with bytes whose hash differs from `hashes.json`'s
- **THEN** the deploy job fails and no deployment is created

#### Scenario: A path that is no longer kept

- **WHEN** the live `hashes.json` lists the whole-cell files of a cell this run builds split
- **THEN** the deploy job ignores those entries, and the new `hashes.json` lists the cell's quarters' files only

### Requirement: A deploy uploads only the files Cloudflare lacks

The deploy job SHALL ask Cloudflare which of the deployment's hashes it lacks, upload only those files,
then confirm every hash of the deployment to Cloudflare. A lacking file in the run's folder SHALL be
uploaded from it; any other SHALL be read back, at most its manifest size, a bucket at a time without
writing it to disk, and uploaded only if it hashes to its `hashes.json` entry; else the deploy fails.

#### Scenario: Only new files

- **WHEN** Cloudflare holds every kept file's hash, and lacks two of the files this run wrote
- **THEN** the run uploads exactly those two, confirms every hash of the deployment, and creates the deployment

#### Scenario: A kept file Cloudflare no longer holds

- **WHEN** Cloudflare lacks the hash of a kept cell's `t0-3m` file, and the live site serves that file unchanged
- **THEN** the deploy job reads it back, uploads it, and creates the deployment

#### Scenario: A kept file read back too large

- **WHEN** Cloudflare lacks a kept file's hash, and the live site serves that path with more bytes than the manifest gives it
- **THEN** the deploy job fails without reading past that size, and no deployment is created

#### Scenario: A re-read leaves no file

- **WHEN** the deploy job reads back a kept file Cloudflare lacks and uploads it
- **THEN** no file holding its bytes is left on the runner

#### Scenario: A kept file changed on the live site

- **WHEN** Cloudflare lacks a kept file's hash, and the live site serves that path with other bytes
- **THEN** the deploy job fails and no deployment is created

### Requirement: Files keep their content types

Every file the deploy job uploads SHALL carry the content type wrangler gave it: `application/gzip`
for `.gz`, `application/json` for `.json`, `text/html` for `.html` and `text/plain` for `.txt`.

#### Scenario: A cell file's type

- **WHEN** a run uploads `colorado/158_-425/t1-4.json.gz` and `manifest.json`
- **THEN** they are sent as `application/gzip` and `application/json`

### Requirement: The deploy's one package is installed from its lockfile

The deploy job SHALL install only `blake3-wasm` 2.1.5, with `npm ci --ignore-scripts` from
`deploy/package-lock.json`, in a step that holds no secret, and no wrangler config file SHALL exist in
the repository.

#### Scenario: Reading the package files

- **WHEN** `deploy/package.json` and its lockfile are read
- **THEN** the only dependency is `blake3-wasm` 2.1.5, with its integrity hash, and the package has no install script

#### Scenario: Reading the install step

- **WHEN** the workflow file is read
- **THEN** the deploy job installs with `npm ci --ignore-scripts` in a step that names no secret

### Requirement: The Cloudflare token reaches two curl calls only

The token and account id SHALL be secrets of the Environment `pages-production`, used only by the
deploy job, and given only to two steps after the assemble and hash steps: one fetching an upload
token for project `slope-extracts`, one creating the deployment from files earlier steps wrote. Each
SHALL write them with shell builtins into curl's header and config files, removed on exit, unset them
before running any program, and print no response.

#### Scenario: Reading the deploy job

- **WHEN** the workflow file is read
- **THEN** `secrets.` appears in exactly two steps of the deploy job, each calling only `api.cloudflare.com` with curl, both after the assemble and hash steps, and in no other job

#### Scenario: Reading a token step

- **WHEN** either token step is read
- **THEN** the token reaches curl only through a header file and the account id only through a config file, both secrets are unset before curl runs, curl writes its answer to a file, and the step removes those files on exit

### Requirement: The upload token stays out of the log

The step that fetches the upload token SHALL mask it before anything else uses it, and pass it on only
in a file under the runner's temporary folder that only the job's user can read, never in a step
output or the environment. The upload step SHALL remove that file when it ends, failed or not, and
SHALL print neither the token nor an API response.

#### Scenario: Reading the token step

- **WHEN** the workflow file is read
- **THEN** the token step writes `::add-mask::` before it writes the token's file, and neither token step writes `GITHUB_OUTPUT` or `GITHUB_ENV`

#### Scenario: A failed upload

- **WHEN** the upload step fails on Cloudflare's answer
- **THEN** the token's file is gone and the step's output holds neither the token nor the answer's body

## MODIFIED Requirements

### Requirement: Deploying adds to the live site

The deploy job SHALL create a deployment of Pages project `slope-extracts` on branch `main` from a
manifest naming every file of the site: this run's cells, every other cell the live manifest lists,
each region's overview, the new manifest, `hashes.json`, `404.html` and `LICENSE.txt`, with `_headers`
beside it. A run that built no cell SHALL deploy nothing.

#### Scenario: A second run

- **WHEN** a run builds one more cell
- **THEN** the deployed site holds both cells' files and a manifest listing both

#### Scenario: Nothing built

- **WHEN** every cell of a run failed
- **THEN** nothing is deployed, and the live site stays as it was

### Requirement: Files read back from the live site are checked

Each file read back to assemble the site SHALL be the size the live manifest gives it and pass the cell-file
checks. The deploy job SHALL fail before the deployment is created otherwise, or when:
- the live manifest is invalid, unless the first-deploy switch reads it as no manifest
- a file it lists answers 404
- it reads no manifest (a 404, or the switch) though the plan job read one
- the new manifest would list fewer cells, whole and quartered together, than the live one

#### Scenario: A file changed on the live site

- **WHEN** a live cell file the deploy job reads back to assemble the site differs in size from the live manifest's
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: A live cell without its 2 m layer

- **WHEN** the live manifest lists a cell whose `t0-2m` is marked left out, `hashes.json` lists none of its files, and a run builds another cell but not it
- **THEN** the deploy job reads back that cell's `t0-3m` and `t1-4`, requests no `t0-2m`, and the new
  manifest keeps its entry as it was

#### Scenario: A live split cell

- **WHEN** the live manifest lists a split cell, `hashes.json` lists none of its files, and a run builds another cell
- **THEN** the deploy job reads back its quarters' files, each checked against its quarter's size and
  bounds, and the new manifest keeps its entry under `quartered` as it was

#### Scenario: A whole cell becomes split

- **WHEN** the live manifest lists a cell in `cells`, and this run builds it split
- **THEN** the new manifest lists it in `quartered` only, the site holds its quarters' files and none
  of its whole-cell files, and the deploy goes ahead

#### Scenario: A split cell fits whole again

- **WHEN** the live manifest lists a cell in `quartered`, and this run builds it whole
- **THEN** the new manifest lists it in `cells` only, and the site holds its whole-cell files and none
  of its quarters'

#### Scenario: The switch forgives a manifest the plan job read

- **WHEN** the plan job read a valid manifest, and the deploy job, with `FIRST_DEPLOY` `true`, reads the manifest as none
- **THEN** the deploy job fails, and no site of this run's cells alone is published

#### Scenario: The custom domain stops answering

- **WHEN** the plan job read the live manifest but the deploy job gets a 404 for it
- **THEN** the deploy job fails, and no site of this run's cells alone is published

### Requirement: The site sets its CORS and cache headers

`_headers` SHALL send `Access-Control-Allow-Origin: *` and `X-Content-Type-Options: nosniff` on every path,
and one `Cache-Control` per path:
one day for cell files (`/<region>/<cell>/…`, quarters' included), an hour for `LICENSE.txt` and overview
files, five minutes for `manifest.json` and `hashes.json`.
A missing path SHALL answer from `404.html`.

#### Scenario: Reading the headers file

- **WHEN** `_headers` is read
- **THEN** no path matches two rules that set `Cache-Control`

#### Scenario: The overview's cache

- **WHEN** `_headers` is read
- **THEN** `/colorado/overview.json.gz` matches one rule, which caches it for an hour, and
  `/colorado/158_-425/t1-4.json.gz` matches one, which caches it for a day

#### Scenario: A quarter's cache

- **WHEN** `_headers` is read
- **THEN** `/colorado/158_-425/316_-850/t0-2m.json.gz` matches one rule, which caches it for a day

#### Scenario: The hashes' cache

- **WHEN** `_headers` is read
- **THEN** `/hashes.json` matches one rule, which caches it for five minutes

### Requirement: The deploy job writes the overview from the cells it publishes

The deploy job SHALL write each overview from the `t1-4` files it is about to publish, after their
checks, and SHALL never read an overview back from the live site. It SHALL fail before the deployment
is created when an overview's file would be over 20 MiB or its JSON over 64 MiB, the limits of a cell
file.

#### Scenario: A run adds a cell

- **WHEN** a run builds one more cell of a region
- **THEN** the deployed overview holds that cell's tier-4 polygons with the others'

#### Scenario: An overview too large

- **WHEN** an overview's gzip file would be 21 MiB
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: A live manifest's overview entry

- **WHEN** the live manifest gives a region an `overview` entry with any value
- **THEN** the plan and deploy jobs accept it, use none of it, and write the new entry from the new overview

### Requirement: The site holds at most 19,000 files

The deploy job SHALL fail before the deployment is created when its manifest would name more than
19,000 files, `hashes.json` counted and `_headers`, which it doesn't name, not.

#### Scenario: Too many files

- **WHEN** the deployment's manifest would name 19,001 files
- **THEN** the deploy job fails and nothing is deployed

#### Scenario: Counting a split cell's files

- **WHEN** a region has one whole cell and one split cell with one quarter's `t0-2m` left out
- **THEN** the site's file count includes 3 files for the whole cell and 11 for the split one

#### Scenario: Counting the hashes file

- **WHEN** the deployment's manifest would name 18,999 files besides `hashes.json`
- **THEN** it names 19,000 files, and the deploy goes ahead

## REMOVED Requirements

### Requirement: Wrangler is installed from its lockfile, with no install scripts

**Reason**: The deploy no longer runs wrangler; it needs only wrangler's hashing package.
**Migration**: "The deploy's one package is installed from its lockfile" pins `blake3-wasm` the same way.

### Requirement: The Cloudflare credentials reach one step only

**Reason**: Deploying from a manifest of hashes takes two Cloudflare calls, not one wrangler run.
**Migration**: "The Cloudflare token reaches two curl calls only" and "The upload token stays out of the log".
