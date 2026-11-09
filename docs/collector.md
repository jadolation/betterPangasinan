# Real-data collector prototype

The operational workflow imports real, attributable source artifacts into review
staging. It has no synthetic collection mode, publication command or approval API.
See [PSA access research](psa-access-research.md) for current official endpoints,
licensing, API requirements and observed access blockers.

## Setup

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-collector.lock
```

The lock includes existing JSON/GIS adapters and verification tools. Shapely 2.2
is required by the existing projection adapter's coordinate-list interface.

## Import real source data

The current verified mapping supports the existing reviewed PSA transcription:

```sh
.venv/bin/python -m collector.cli collect --source psa_psgc \
  --input pangasinan_lgu_registry_staging.json \
  --state-dir data/staging/psa-prototype
```

This produces **49 pending, non-mock records**: one province, four cities and
44 municipalities. It retains original JSON rows, source links, string PSGCs,
parent links, administrative release and population reference dates. Provincial
population is an explicitly evidenced sum of the supplied LGU populations.
It does not import invented barangays, capital or land area. The source remains
labeled `user_reviewed_transcription`, with independent verification false and
unknown original retrieval/publication metadata explicit. This is not a fresh
current PSA workbook, despite being real rather than synthetic data.

The JSON response identifies `run_id`. Original bytes are retained at
`<state-dir>/raw/<sha256>`, SQLite at `<state-dir>/staging.sqlite`, and review
outputs at `<state-dir>/runs/<run_id>/`. Repeating the same source creates a new
audit run but zero new entity versions. Invalid inputs retain failure evidence
and exit nonzero without creating entity versions.

```sh
.venv/bin/python -m collector.cli report --run-id RUN_ID --state-dir data/staging/psa-prototype
.venv/bin/python -m collector.cli validate --run-id RUN_ID --state-dir data/staging/psa-prototype
.venv/bin/python -m collector.cli export --run-id RUN_ID --state-dir data/staging/psa-prototype \
  --format json,csv --target data/staging/psa-review
```

Repository output destinations are restricted to staging; symlink escapes and
production/input destinations are rejected. CSV formulas are escaped. Validation
and collection never grant approval. Missing values remain null with reasons.
JSON/CSV manifests include source hashes and quality/change/gap reports.

## P0 review package

```sh
.venv/bin/python -m collector.cli review-p0
```

`data/staging/Better_Pangasinan_Research/` contains:

- `01_provincial_overview/pangasinan_overview.json`: field evidence, approximate
  land area and general location from saved official-page extraction, explicit gaps.
- `02_lgu_directory/`: 48 reviewed LGUs, existing six-district assignments and
  1,364 explicitly unofficial/unversioned barangay records, with JSON/CSV outputs.
- `05_national_budget_2027/`: all 732 approved comparison records carried into
  read-only review CSV, existing geographic candidates and source inventory.
- Source inventory, collection log, gaps, quality report and input/output hashes.

These exports reuse existing reviewed evidence. They do not refresh the approved
application data or imply that unofficial barangays are a current PSA release.
The budget compiler preserves separate NEP/House reading amounts and uncertainty;
proposal amounts are never represented as spending or wholly local allocations.

## Live practice and browser downloads

The existing bounded practice runner still works:

```sh
.venv/bin/python -m collector.practice --authorize-live-practice \
  --target data/staging/practice-NEW-UNIQUE-NAME
```

It checks robots before the provincial page and budget API overview, verifies
public-IP HTTPS destinations, bounds downloads and preserves failed responses.
The separate PSA source remains disabled after its official workbook returned a
403 challenge. No live secret or source approval is inferred. The optional host-side browser helper is also available:

```sh
npm ci
npx playwright install chrome
npm run collect:psa -- --headed --target data/staging/psa-browser-NEW-BATCH --authorize-live-practice
```

The November 4 headed run passed robots, then stopped at an HTTP 403 HTML challenge on the PSGC landing page; no workbook was acquired.
See the access research guide for evidence and legitimate fallback options.

## Docker and PostgreSQL

See [migrations/README.md](../migrations/README.md) for tested commands. The runtime
image includes the reviewed real transcription instead of synthetic workbooks.
The offline worker retains `network_mode: none`, a read-only root and UID 10001.
The live-practice service is opt-in and has staging-only mounts. A bridge is not
an outbound firewall; production collection still needs infrastructure egress
controls. PostgreSQL/PostGIS requires separate migrations and least-privilege
credentials. Local SQLite remains an isolated prototype backend.

## Tests and boundaries

```sh
.venv/bin/python -m pytest
.venv/bin/ruff check collector tests/unit/test_collector*.py tests/unit/test_real_psa.py tests/support tests/security tests/integration
.venv/bin/ruff format --check collector tests/unit/test_collector*.py tests/unit/test_real_psa.py tests/support tests/security tests/integration
.venv/bin/mypy collector --ignore-missing-imports
```

Synthetic extraction is test-only, in `tests/support/synthetic_collector.py`; it
injects deterministic rows through the same validation/staging boundaries. It is
not included in the runtime image. Mock approval/publication rejection remains
covered. Real-input unit/CLI tests use the preserved reviewed transcription, and
the PostGIS test now ingests those same 49 real-shaped non-mock source records.
Use a fresh disposable database for each PostGIS run; historical evidence remains
append-only. Tests are not proof of live PSA workbook access.

Current gaps: original current official workbook and observed mapping, API token
and intended-use approval, current barangay/population source linkage, full S3
integration, orchestrator and authorized publication integration. Source access
failures cannot be resolved by weakening safeguards or removing regression tests.

## Scrape-only MVP boundary

The current MVP acquisition workspace is `data/staging/web-crawler/`, separate
from `Better_Pangasinan_Research/` and local-transcription imports. Only fresh
crawler responses and outputs derived from those responses belong here. Do not
populate it using `review-p0`: that command deliberately reviews existing
repository evidence and does not satisfy this scrape-only boundary.

Each run must retain exact source URLs, UTC retrieval times, original response
bytes, SHA-256 hashes, extraction status and pending review restrictions. Denied
or failed responses are diagnostic evidence, not datasets. Missing coverage is
reported rather than filled from production data, PSA transcriptions or approved
budget candidates. PSA acquisition is deferred. The existing bounded practice
runner can acquire the provincial about page and budget API overview; it does
not collect a complete LGU directory, barangays or budget project records.

Use a new run directory for each attempt:

```sh
.venv/bin/python -m collector.practice --authorize-live-practice \
  --target data/staging/web-crawler/p0-NEW-RUN
```

The practice runner also observes PSA robots while leaving PSA content collection
disabled. The directory stays beneath staging for existing permission and Docker
mount isolation. No output is automatically published.

## File-based project candidates

No database or Docker service is required for the API capture-to-candidate path.
With a completed crawler batch, run the offline adapter:

```sh
.venv/bin/python -m collector.candidates \
  --run data/staging/web-crawler/psa-geography-20261109-01 \
  --target data/staging/web-crawler/project-candidates-NEW-RUN
```

The adapter verifies capture checksums and API pagination totals, reconstructs
records from captured responses, validates geographic identifiers/parents, and
checks `lgus.json`, `sources.json` and `statistics.json` against the repository
schemas. Outputs are drafts. `provenance.json` retains source rows, response
locations, hashes and timestamps. No existing production data or transcription
is read. Repeating the adapter into a fresh destination produces identical files.

`province_profile.candidate.json` and `barangays.candidate.json` are review
candidates, not drop-in approved geographic bundles. The province production
schema requires human approval, capital and exact reference dates, which this
capture does not establish. Population observations retain the API year; exact
dates remain null rather than being inferred. Captured API release is Q2_2024,
not a claim of latest administrative coverage. Response artifacts may be redacted
to remove echoed authentication tokens; their stored hashes identify those bytes.

The November 9 capture generated 48 LGUs, 1,364 barangays and 144 LGU population
observations (2015, 2020 and 2024). Integration/publication remains an explicit
review step. This adapter does not modify the approved national-budget snapshot.

## Render the provincial directory

The official directory displays email addresses through its own page scripts.
Use visible sandboxed stable Chrome to capture rendered table cells, including
plain-text emails and two-column hospital contact rows:

```sh
node scripts/province-directory.cjs \
  data/staging/web-crawler/directory-rendered-NEW-RUN --authorize-live
```

The bounded host-side run preserves robots, original HTML, rendered HTML and
extracted directory JSON with hashes. It restricts network origins, pins public
DNS destinations and verifies connection peers. It does not verify mailbox or
telephone activity. The collector has no publication action. External resources
are blocked, so this is a targeted directory capture rather than visual-fidelity
verification of the full website.
