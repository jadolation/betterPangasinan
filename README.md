# Better Pangasinan

An independent, volunteer-led civic information portal for Pangasinan. This is
not an official government website and does not claim government endorsement or
formal organizational affiliation.

The site uses vanilla HTML, CSS, JavaScript, and a Python static build. Preserve
the blue/gold design, Space Grotesk and Lora typography, and existing hero wave.
The repository-root `logo.svg` supplies the shared brand and SVG favicon.

## Build and Test

Run from the repository root with Python 3:

```sh
python -m pip install -r requirements.txt
python build.py
python -m pytest
```

If your system exposes Python 3 as `python3` rather than `python`, substitute
`python3` in these commands. An isolated synthetic build can be generated with:

```sh
python build.py --mode test --output /tmp/kilo/provincial-test --no-root-compatibility
```

That directory is for local testing only and must not be deployed.

The default build is production. Deploy only the generated `public/` directory.
Root HTML files are compatibility build output, not independent page sources.
Never deploy the whole repository or use test fixtures as production input.
Run the browser regression suite with Node.js 22 or later:

```sh
npm ci
npx playwright install chromium
npm run test:browser
```

The runner builds and serves `public/` automatically. It uses system Chrome if
available, otherwise Playwright Chromium. Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE`
to override the browser path. Reports and screenshots are under
`tests/browser/report/` and `tests/browser/artifacts/`.

For a local production preview:

```sh
python3 -m http.server 8000 --directory public
```

## Source Layout

- `src/pages/`: page content with title and description front matter.
- `src/partials/`: shared base, header, and footer. Edit these, not generated HTML.
- `assets/`: shared styles, browser scripts, and static resources.
- `logo.svg`: provincial brand artwork; preserve its aspect ratio.
- `build.py`: validation and static compilation entry point.
- `data/` and `schemas/`: structured records, source references, and validation rules.
- `data/production/tourism.json`: curated tourism guide (attractions, commute routes, local food), validated by `scripts/tourism.py` against `schemas/tourism.schema.json`; self-hosted licensed photos live in `assets/tourism/`.
- `tests/`: automated validation and synthetic test inputs.
- `src/locales/`: English interface strings and additional-language foundations.
- `public/`: generated deployment artifact.

## Publication Rules

Public records require traceable sources, review, explicit availability, and
approval. Empty sections are intentional when no approved records are available.
Do not invent budgets, population, officials, contracts, findings, or coordinates.
Missing information is not zero and is not evidence of LGU noncompliance.
Appropriations, expenditure, approved budgets, and contract values are distinct;
never aggregate incompatible years, units, or amount types. Project location
does not establish the funding or implementing entity.

Synthetic records must remain marked `is_mock: true` and confined to tests or
explicit test builds. Production must reject mock records, never substitute
them for missing data, and exclude fixtures and internal materials from its
artifact. Official identifiers, boundaries, records, and additional-language
translations still require source review before publication.

Read `methodology.html`, `privacy.html`, and `corrections.html` in the built site
for public policy. No account system or personal-data submission service is
provided. A dedicated volunteer or corrections contact channel is not yet
published; do not invent contact details or affiliations.

## Deployment

Run the production build and tests before publishing. GitHub Pages should use
the repository workflow's validated `public/` artifact, not branch-root hosting.
For another static host, use `python build.py` as the build command and `public`
as the publish directory. Relative asset and page links support project-subpath
hosting. Do not upload source datasets, private test inputs, notes, credentials,
or the repository itself.

The English dictionary currently covers the homepage hero/search and shared
dynamic states. The remaining editorial and module copy is English source
content; dictionary extraction is incremental. Filipino and Pangasinan are
unreviewed foundations only, so no language switcher is exposed.

Before release, inspect desktop and mobile layouts, keyboard navigation, logo
loading, no-JavaScript content, unavailable data states, source links, and the
deployment artifact. Automated checks alone do not establish accessibility
conformance or source accuracy. No live deployment is implied by a local build.

## Unified Local Prototype

The user-reviewed starter now populates the existing production graph: 48 LGUs,
four cities, 44 municipalities and 48 dated population observations. The total
3,188,540 persons refers to July 1, 2024; the administrative listing is dated
July 31, 2025. Original starter files and collection labels are retained.

```sh
python3 -m scripts.import_psa_lgus --input pangasinan_lgu_registry_staging.json --output data/staging/normalized_lgus.json --publish data/production
python3 build.py
```

`scripts/site_data.py` validates supplemental adapters before replacing output
and permits only their explicit public filenames. Production builds mirror these
same resources to the repository root for Live Server; raw downloads, staging,
private reviews and test fixtures are not copied. Existing production review and
mock-rejection rules remain enforced.

For real staging records that are not deployment-ready, use a separate preview:

```sh
python3 build.py --mode preview
python3 -m http.server 8001 --directory preview-public
```

Preview mode rejects mocks, keeps graph/schema/provenance validation, labels
every page as a development preview, and never rewrites root compatibility
files. `--data-dir` can select a normalized staging graph. Production still
rejects draft and unreviewed generic records. Deploy neither `preview-public/`
nor the repository root.

Available routes:

- `index.html`, `lgus.html`, `lgu.html`: source-backed provincial KPIs, searchable
  LGUs, population, PSGCs, dates and parent-linked barangay lists.
- `municipality-map.html`: 48 source-matched polygons and an equivalent text
  directory; profile selection supports `?psgc=`. These are simplified reference
  boundaries, not a legal survey.
- `historical-budget.html`: 3,821 collected GAA program families, 2020-2026 annual
  amounts, department/query/year filters, chart/table and filtered CSV. All 38
  province-name department queries completed; optional individual LGU query
  batches remain available, not claimed as already collected.
- `budget-context.html`, `budget-hearings.html`: distinct national/regional NEP
  context, budget-cycle scope and three machine-transcript topic matches.
- `government.html`, `hospitals.html`, `history.html`, `statistics.html`: original
  research observations and official-page captures, preserving source periods,
  unknown currentness, qualifications and source links. Finance, legislation and
  projects pages also embed their reviewed reference observations separately
  from generic ledgers and awarded-project records.

The geography sources are geoBoundaries ADM3/ADM2 (2020 reference; CC BY 3.0 IGO)
and an attributed, unversioned PSGC Cloud snapshot of 1,364 barangays. The mirror
does not establish an official current PSA release. All 48 parent code/name
pairs were checked against the supplied registry; source-provided 10-digit
codes were preserved. Original URLs, licensing/terms, hashes, reference dates
and matching limitations are in `data/geography/manifest.json`.

Repeatable collection entry points are `scripts/geography_data.py`,
`scripts/provincial_reference.py` and `scripts/historical_budget/collect.py`.
Builds are offline. For a historical refresh, use a separate `--root` workspace
first, inspect its coverage and exact annual values, and explicitly review it
with `python3 -m scripts.historical_budget.publish --root <workspace> --review-prototype`
before replacing the retained approved inputs. Collection must not be treated as
automatic authorization for a new production snapshot.

Known limits: geographic matching does not attribute national projects to LGUs;
hospital heads are directory-listed with unknown as-of dates; hearing speakers
and figures may be machine-transcription errors; the DPWH budget-cycle endpoint
returned HTTP 404 and stays unavailable. Historical GAA/NEP responses provide
checksums but no source commit. Name-query completeness is not geographic
exhaustiveness. The FY2027 approved snapshot and its attribution states remain
unchanged.

## Transparency Interface

`transparency.html` is the public entry point for budget and local disclosure
tools. Availability and counts come from actual published files; missing or
invalid data is not shown as zero funding. Existing routes remain available,
including `projects.html`, the LGU Explorer at `lgus.html`, and the Government
directory at `government.html`.

Transparency pages use one canonical navigation list (`SECTION_NAV_ITEMS` in
`build.py`) and `src/partials/transparency-nav.html`. Frontmatter explicitly sets
`section_nav: transparency` and the active `section_item`; page titles do not
determine section membership. `assets/section-nav.js` measures the actual header
and navigation border boxes, handles anchor-aware current states and preserves
same-page budget filters. Mobile navigation stays in a single scrollable row;
without JavaScript it remains an ordinary set of links.

The budget route supports links to `national-budget.html#projects`, `#offices`
and `#about-data`. Search, program, comparison and sort are visible by default;
advanced filters retain selected values while closed. Filters are shareable in
the query string. Results render 25 records at a time, with responsive mobile
rows and a keyboard-operable evidence dialog. Totals and CSV include the entire
filtered selection, not only the visible page. Financial summaries remain
separated by House reading under their own disclosure.

`assets/transparency.css` supplies scoped shared components. The existing
budget entry script retains validation, checksums, calculations and CSV;
`assets/national-budget-view.js` handles table rows, office cards and structured
evidence. Technical fields and original disclaimers remain available through
progressive disclosure. This presentation layer does not modify approval,
geographic attribution or source data, and does not load live budget API results.

## Maps And Unified LGU Profiles

The homepage follows six content sections: hero, provincial overview,
municipality map, Transparency Snapshot, Government Snapshot, then Public
Knowledge. Volunteer access is retained within Government and the footer, not
as another campaign section after Public Knowledge. The former homepage LGU
search, three-card feature grid and sources/methodology columns are removed;
the map and LGU Explorer remain the discovery tools.

`scripts/home_snapshot.py` derives `data/home-snapshot.json` from already
validated publication resources. The homepage requests this small summary, not
the full project or historical program datasets. Counts stay distinct, unknown
values stay hidden, and reported budget observations are labeled separately
from the structured local financial ledger.

### Districts And Representatives

`data/production/government_directory.json` is the canonical structured source
for provincial leadership, regular board members, congressional representatives,
ex-officio positions and six legislative districts. Its adapter and schema verify
all 48 PSGCs occur once, with district sizes 10/8/6/5/9/10 and correct official
role links. No proposed eight-district arrangement is applied. Public output is
`data/government-leadership.json`; raw page captures stay private under ignored
`data/government_sources/raw/`. Capture and normalization are explicit:

```sh
python3 -m scripts.government_directory --collect
python3 -m scripts.government_directory --initialize
```

These commands normalize the reviewed November 2026 reference names and must
not be treated as an automatic future-term roster update. Recheck source names,
effective district arrangements and individual fields before a later refresh.

The province's official board, Governor, Vice Governor and municipality listing
were retrieved successfully. House directory requests returned HTTP 403, so the
six House names retain the user's reviewed 20th Congress reference, not a false
claim of live House verification. PCL remains a pending position because the
reported references differ. No confirmed PCL officeholder is selected. The
Governor's +63 75 632-3138 telephone is Governor-office-only; Vice Governor
telephone/mobile and exact office-location fields remain unknown unless their
specific evidence is confirmed. Social links are included only when the
official profile supplies them. Portraits are not used.

The shared map supports `municipality-map.html?view=districts&district=leg%3Apangasinan%3A4th`.
It highlights groups of the existing municipality paths, with no additional or
invented geometry. Municipality View remains the default; selections and
hover/focus previews remain separate. Missing optional leadership data leaves
the municipality explorer functional. Government filtering and the generated
LGU profile representative panels use the same canonical record IDs. A district
relationship does not imply that an official requested or controlled a project.

The homepage places its municipality explorer immediately after the provincial
statistics. `assets/lgu-map.js` shares one data/projection promise and one
implementation across `home`, `explorer` and `profile` modes. Blue polygons turn
gold on hover, focus and selection. Preview and persistent selection are
independent; no municipality is randomly selected. Every map retains source
attribution and a text alternative.

```js
const map = window.createMunicipalityMap({
  container,
  mode: 'profile',
  selectedPsgc: '0105518000',
  onSelect(record) { /* Navigate only on an explicit selection. */ },
  onPreview(recordOrNull) { /* A preview does not change profile identity. */ }
});
await map.ready;
```

`lgu.html?id=lgu-0105518000#statistics` is the canonical local destination.
`assets/lgu-profile.js` resolves identity once and embeds statistics, barangays,
finances, projects, applicable services and sources. Query IDs and section
anchors remain bookmarkable. Missing optional data does not replace the LGU or
its population with another locality's information.

`scripts/lgu_profiles.py` generates small optional views at
`data/lgu-profiles/<lgu-id>.json` during the static build. These ignored root
mirrors and generated public files are not independently maintained datasets.
Statistics use the same published observations as the province-wide views.
Generic relationships require explicit LGU IDs/codes; provincial reference
records use exact unique LGU labels. A hospital name alone is insufficient to
establish its location. National title matches appear only as discovery leads,
without becoming local finance records or assigning an office's funding to a
municipality. The complete national/historical datasets remain in their
specialist explorers rather than being copied into every profile.

The LGU directory initially renders 12 cards, with full-registry search and
Show More. Province-wide pages remain available for comparisons; existing
`?lgu=` bookmarks provide a prominent link to the corresponding profile section.
Plain-language summaries come first, original records and technical identifiers
remain in source disclosures, and ledger amounts are never combined with
reported local-budget observations or national proposals.

## National Budget Pipeline

### Published Project Locations

`map.html` is the FY2027 Project Locations explorer, separate from the SVG
municipality/district map. It defaults to All Programs and also supports
API-published points from other programs. `?project=<dataset:upstream-id>` opens
the matching program and source location. Budget records with usable coordinates
offer a map link; records without them say Location unavailable. LGU profile
name matches remain discovery leads, never confirmed local allocations.

`scripts/national_budget/geographic_audit.py` recomputes two allowlisted derived
outputs during every build: `data/project-locations/projects.geojson` and
`review-summary.json`. Do not edit these generated root/public mirrors by hand.
The approved FY2027 records, amounts, House stages and original geographic review
states are unchanged. Source-record metadata and original OCR/normalization
annotations remain accessible as evidence.

Coordinate order follows explicitly named longitude/latitude fields, never
whichever order lands in Pangasinan. FMR start/end segments retain both source
versions and deduplicate identical pairs with evidence. A valid endpoint remains
plotted when its partner is invalid; missing or uninterpretable coordinates
produce no invented marker. API-published standalone points are identified as
such and are not assumed to be surveyed infrastructure locations.

Shapely handles Polygon/MultiPolygon coverage, holes and the provincial union.
`pyproj` supplies WGS84 geodesic distances and a local UTM51N 200-metre boundary
tolerance for the simplified reference geometry. Endpoints over 200 km apart,
identical endpoints and municipality mismatches are review indicators, not proof
of error or misconduct. No reliable land/coastline dataset is used, so the audit
does not claim that a point is offshore solely because it is outside Pangasinan.
Required dependencies are declared in `requirements.txt`.

The Leaflet 1.9.4 map is self-hosted under `assets/leaflet/`, with its BSD 2-Clause
license retained in the JavaScript header and source license file. The default
Web Mercator (EPSG:3857) view uses standard OpenStreetMap background tiles. Provider
URL, attribution and viewport-only loading options are centralized in
`assets/project-map-config.js`. Normal browser caching and referring-origin
information are retained; no offline download, tile proxy, bulk cache, route
lookup or road snapping is implemented. Evaluate an explicitly licensed hosted
provider before substantial traffic; OSM's community servers have no availability
guarantee. Read `privacy.html#map-privacy` and the OSM tile-usage policy.

Choose No basemap to stop new tile requests. Basemap and boundary failures do not
remove valid source markers or connections. A missing boundary overlay uses an
approximate overview viewport, not invented project locations or a claim of
administrative consistency. An actually mismatched supplied boundary hash still
fails integrity validation. Thin, nearly transparent municipal overlays preserve
roads and labels beneath them. Program and suspicious-layer controls change only
visibility, not records or classifications.

Latitudes beyond Web Mercator's supported range remain in source evidence and
are not drawn at a clamped latitude. The explicit global-coordinate inspection
switch rebuilds a tile-free EPSG:4326 view for those exceptional coordinates.
The normal OSM view has no artificial coordinate grid. Source values, hashes and
the geographic audit are identical in either projection.

The initial viewport fits Pangasinan only. All matching usable source locations,
including distant suspicious points, remain in their original layers. Selecting
a record opens its first usable source point; View Start, View End and View Both
navigate the active segment without changing source values. Suspicious-location
search expands to all programs and clears incompatible search/municipality/
comparison filters, without fitting the viewport to outliers. Pangasinan Overview
preserves selection and filters; Reset View explicitly clears them. Dashed lines are endpoint
connections, not road centerlines, driving routes or construction evidence.
Outside-province namesakes are distinguished from inconsistent Pangasinan claims.
No source coordinate is moved or omitted merely to make it look plausible.
Explicit `name_match_elsewhere` records are hidden by default, with a dynamically
reported excluded count and an Include outside-province search matches option.
Outside coordinates and suspicious status alone never exclude a record: the
Bolinao outlier remains in the default view. A namesake project deep link or
explicit namesake-status filter enables inclusion. Reset returns to focused
All Programs. URL parameters preserve filters and inclusion on reload/history;
all source records and their geometry remain in the downloadable dataset.
The specific Koronadal FMR `fmr:house_only:ib:p722:r4` is additionally excluded
from Project Locations at the user's request, including its markers, connection,
list entry and old map deep link. The inclusion checkbox cannot restore that
record to this map. Approved source and derived audit downloads remain intact;
integrity checks run on the complete files before the visual exclusion is applied.

Hashes bind the derived output to the current publication snapshot, project-file
bytes and municipality boundary bytes. The browser checks those bindings, the
coordinate-file checksum and complete feature/segment consistency. Stale or
altered evidence fails closed. The list remains available if Leaflet or the
boundary reference cannot load; errors are never substituted with zero funding.

The committed Bolinao bridge (`dpwh:house-reading:6548`) has one structured API
point at longitude 119.92525, latitude 6.38299. Its title explicitly also publishes
latitude 16.38329, longitude 119.92648. Following the user's November 3 approval,
the audit displays this second pair as **source-title evidence, unverified**.
This is a narrowly reviewed interpretation for that exact record, title, API
pair, snapshot and record hash, not a general title-coordinate scraper.
The order is explicitly latitude/longitude and the first pair agrees with named
API fields; geography does not determine order. Source paths, exact tokens/text,
offsets, title copies and reading versions are retained. Changed or stale bindings
suppress the extra point and add a review flag while keeping any usable API point.

First Point and Second Point identify these evidence types. Their approximately
1,106 km dashed connection is a `title_coordinate_comparison`, **not verified
bridge endpoints or an alignment**. The first marker is not duplicated. No title
coordinate is corrected, and no original budget value or geographic review state
is changed. The updated derived output contains 207 Points and 33 LineStrings
across the same 174 mapped projects and 732 records. All 32 structured FMR
connections remain; the extra line is the separately labeled title comparison.
Other DPWH records still have no newly inferred endpoints. Their 70 records with
chainages are not interpreted as geographic alignments.
Automated browser tests route OSM tiles to controlled PNG fixtures, including
manually created contexts, so regression runs never crawl public tile servers.

`national-budget.html` is a separate FY2027 proposal explorer. It does not insert
national proposals into the existing 12 production datasets or their totals.
Python's standard library handles collection; `jsonschema` validates separate
contracts under `schemas/national_budget/`. No database, backend, browser API crawl
or React application is used. Historical GAA is collected by its separate
pipeline and is never combined with these FY2027 proposals.

Collect a resumable internal batch and normalize it:

```sh
python3 -m scripts.national_budget.collect --output data/national_budget/raw/my-batch --offices
python3 -m scripts.national_budget.pipeline normalize data/national_budget/raw/my-batch/manifest.json --output data/national_budget/review/my-batch
```

The collector obtains the overview, all district-directory pages, Pangasinan
district details, four province-name searches, the Mapandan regression query and,
with `--offices`, each discovered office's exact published label. Requests are
bounded-retry, HTTPS-host-restricted and snapshot-bound. List queries are sequential;
details default to one worker with an explicit `--detail-workers` limit of three. Raw response
bytes, checksums, HTTP attempts, UTC dates, errors, pagination and reconciled
whole-query sums remain under ignored `raw/`. Reusing a batch checks a live
overview before using cached pages; a changed snapshot requires a new batch.
Use `--help` for controlled reviewed-registry LGU batches and optional project
details. `--config` loads bounded page-size, timeout, retry and search settings;
the default is `data/national_budget/config.json` and the trusted API/year/programs
cannot be changed. `--details` retrieves at most ten records by default;
`--detail-limit` is bounded to 50 and repeated `--detail-id dataset:upstream_id`
selects particular already-collected records. Repeated `--details` batches advance
to missing evidence instead of fetching the first records again. Do not run a
broad uncontrolled crawl. Do not use the preliminary
research registry as a reviewed registry.
An LGU collection registry needs `review_status: "approved"`, `reviewer`, UTC
`reviewed_at`, a PSA HTTPS `source_url`, the reviewed `release`, and an `lgus`
array of Pangasinan city/municipality `{psgc, name}` entries. Syntactic checks are
not official code-to-name verification; the named reviewer must do that review.
Later LGU offsets and selected detail batches merge into the same snapshot-bound
manifest. A failed live anchor preserves the previous manifest and logs a failed
attempt separately; failures are not converted into a fresh successful batch.

Normalization produces `candidates.json` and `review-report.json` under ignored
`review/`. Candidates preserve original fields, query provenance and source
warnings, but receive no LGU assignments or publication approvals. A
`q=Pangasinan` match is not necessarily a title match or a location in the province;
namesakes such as New Pangasinan in Koronadal, South Cotabato can also match.
Central-office umbrella
amounts may cover several regions; their full amounts are not provincial funding.
`data/national_budget/discovery.json` records collection/publication summary
information; the approved inputs remain authoritative. It is not a geographic
completeness claim.

### Human Review

No command approves records. A human must supply `decisions.json` conforming to
`schemas/national_budget/review.schema.json`, referencing the exact candidate and
record SHA-256 values. Decisions contain a named reviewer, UTC `reviewed_at`,
snapshot identity, explicit approve/exclude choices, evidence document keys and
independent source/geographic states. Review metadata is a declared audit trail,
not cryptographic proof of reviewer identity. Do not invent a reviewer or approve
data merely because automated checks pass.

The current 732-record snapshot and four offices were explicitly approved for
publication by the user on November 1, 2026. Its decisions retain the original
statement and authorization timestamp in `authorization`, together with the
original candidate hash and a binding hash of every source record. `recorded_by`
identifies the agent applying that instruction; decision timestamps record its
application, not an invented claim that the user independently inspected every
PDF at that time. Publication-only authorization cannot create LGU assignments,
mark geography reviewed, or clear source warnings. All project-detail responses
are collected, but geographic attribution remains pending.

Approved projects require `scope`, `geographic_review_status`,
`source_review_status`, `evidence_source_ids` and `lgu_associations` (possibly empty).
Use `reviewed_with_warnings` when upstream flags or held pairings remain. Excluded
records require a reason. Geography may remain pending for explicitly labeled
office/uncertain records; geographic-scope records require geographic review.
Shared umbrella records cannot be promoted into wholly geographic allocations.

LGU associations require reviewed PSGCs, names and evidence for each association.
The decision file's `lgu_registry` contains human-reviewed PSA release entries
(`psgc`, `name`, `source_url`, `release`, `reviewer`, `reviewed_at`); associations
must match it. Registry review is not project-location evidence. Office approvals
are separate and bind each office's checksum. Use empty `offices` and
`lgu_registry` arrays when neither is approved. Any incomplete coverage requires
explicit `allow_incomplete_coverage: true`; collection conflicts/errors cannot be
waived. Collect the selected records' project details before approving them;
missing details or PDF evidence block publication, not retention as a candidate.

After human review, verify publication with:

```sh
python3 -m scripts.national_budget.pipeline compile data/national_budget/review/my-batch/candidates.json data/national_budget/review/my-batch/decisions.json --output /tmp/kilo/budget-publication-preview
```

Only after review, place the exact candidates and decisions at
`data/national_budget/approved/candidates.json` and `approved/decisions.json`.
There is deliberately no automatic promotion command. Keep the last approved
inputs unchanged when a collection fails. The build revalidates them before
replacing output, rejects partial/stale approvals and emits only
`manifest.json`, `projects.json`, `offices.json`, `coverage.json` and `sources.json`
under `public/data/national-budget/2027/`. Raw requests/research/review files are
not copied. The browser checks the exact published file bytes against manifest
SHA-256 hashes before rendering, rejecting mixed/stale assets. Without approved inputs, the same files explicitly report
unavailable, not zero funding. Never copy a test approval into this directory.
The default UI displays all published scopes with non-geographic-total labels;
the geographic lens remains restricted to independently reviewed assignments.
Production compatibility builds also mirror the same five validated files to
`data/national-budget/2027/` so a repository-root Live Server works as well as
the generated `public/` site. Neither mirror contains raw responses or review inputs.

### Verification

```sh
python3 -m pytest
python3 build.py --no-root-compatibility
npm run test:browser
```

Browser tests use local synthetic approved responses, not live API availability.
They cover review warnings, stage/scope separation, filtered formula-safe CSV,
subpath URLs, keyboard use and 320/375/430/768/desktop layouts. The Playwright
runner still performs the default compatibility build. Screenshots and browser
reports stay under ignored `tests/browser/artifacts/` and `report/`.

Interpret totals per reading and scope, preserving null and known-row counts.
Comparable-row change excludes held pairings and different-scope comparisons.
Never sum repeated pagination aggregates, office and geographic views, different
House readings or overlapping municipal views. The initial Mapandan capture is
a regression fixture only: PHP 49 million NEP, PHP 49 million House, zero change,
with the Amanoaoac source warning preserved, never a PHP 98 million budget.
