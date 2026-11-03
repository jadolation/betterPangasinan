# P0 collection and review prototype

The collector writes review staging only. It has no publication or approval
command. The existing website, approved FY2027 snapshot and reviewed directory
remain the application sources. See [the source brief](../doc/BETTER%20PANGASINAN%20WEB%20CRAWLER.md)
and [AGENTS.md](../AGENTS.md) for scope and mandatory controls.

## Setup and reproducibility

Use Python 3.12 and install the hash-locked environment:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-collector.lock
```

The lock includes the existing JSON/GIS adapters and test/type/lint tools.
Shapely 2.2 is pinned because the existing projection adapter returns coordinate
lists; clean Python 3.12 testing exposed its incompatibility with Shapely 2.1. It does
not change the website's requirements.txt. Regenerate with `uv pip compile
requirements-collector.in --python-version 3.12 --generate-hashes --output-file
requirements-collector.lock` after reviewing updates. Never assume pinned versions
are permanently secure; scan before deployment.

Run the synthetic vertical slice entirely offline, including staging exports:

```sh
.venv/bin/python -m collector.cli collect --source psa_psgc \
  --fixture tests/fixtures/collector/psgc_sample.xlsx --environment test
```

The JSON response identifies `run_id`. Evidence bytes are under
`data/staging/collector/raw/<sha256>`, SQL staging is
`data/staging/collector/staging.sqlite`, and the complete run export is under
`data/staging/collector/runs/<run_id>/`. Rerun the same command: audit run IDs differ,
but identical input creates no additional entity versions. Use the returned ID:

```sh
.venv/bin/python -m collector.cli validate --source psa_psgc --run-id RUN_ID
.venv/bin/python -m collector.cli report --run-id RUN_ID
.venv/bin/python -m collector.cli export --source psa_psgc --run-id RUN_ID \
  --format json,csv --target data/staging/fixture-review
```

Invalid acquisitions/layouts/hierarchies are audited and exit nonzero; they create
no staged entity versions. Their review exports remain explicitly invalid. Missing
population remains null with `not_collected`. `validate` is a read-only recheck,
not an approval or mutation of the original audit. `--state-dir` changes the local
test storage location. Repository destinations must be under `data/staging`;
publication, input and symlink escapes are rejected. Fixtures cannot enable HTTP.

## P0 work in order

```sh
.venv/bin/python -m collector.cli review-p0
```

This reads and validates preserved repository inputs, with zero outbound requests,
and produces `data/staging/Better_Pangasinan_Research/`:

1. `01_provincial_overview/pangasinan_overview.json`: field-specific source and
   reference metadata, approximate land area and general location from the saved
   official about page. Coordinates, administrative region, seal and rights remain
   null. Original about-page HTML is absent; its evidence hash explicitly covers
   the preserved extracted page rather than claiming a raw HTML hash.
2. `02_lgu_directory/`: `pangasinan_lgus.json`, `pangasinan_barangays.json`,
   `lgu_directory.csv`. Reuses the existing reviewed 48-LGU/population transcription
   and 1,364-record unofficial barangay snapshot, plus existing validated six-district
   assignments. Retains their differing source
   vintages, original values and explicit parent links. This is not independent
   official-source or current-release verification.
3. `05_national_budget_2027/`: `national_budget_2027_review.csv`,
   `project_geographic_candidates.json`, `budget_source_inventory.csv`. Recompiles
   the existing approved 732-record snapshot through its current validation gates.
   Keeps NEP, second reading and third reading separate, with exact original integer
   PHP amounts and nulls. It carries existing discovery evidence forward; it makes
   no new geographic assignments and does not treat proposals as spending.

The root includes `source_inventory.csv`, `collection_log.csv`,
`collection_gaps.csv`, `quality_report.json` and a SHA-256 `manifest.json` binding
inputs and outputs. Outputs are marked pending and partial; passing validation
never clears license restrictions. Historical retrieval times are preserved where
known. A date-only source is not relabeled as a UTC retrieval timestamp. The P0
review run ID is deterministic from inputs, so reruns produce identical outputs.
Use `--target /tmp/p0-review` for an isolated export.

## Source mapping and permissions checklist

`config/sources/psa_psgc.yaml` is typed and disabled: endpoint, approved paths,
release, access and redistribution review are unresolved. The only implemented
XLSX mapping is [synthetic_psgc_v1](../tests/fixtures/collector/README.md), with exact
worksheet/column contracts. No inferred PSA header mapping is used.

Before live collection, record the exact official download, identity, dated
release, reference period, terms/robots/license evidence and permitted paths.
Obtain source-access authorization; separately review redistribution. Configure
container egress restrictions and verify the actual connection destination to
prevent DNS rebinding. The HTTPX adapter deliberately accepts only an isolated
MockTransport test harness; there is no live-mode escape flag. Its tests cover
public-DNS checks, host/path allowlists, redirect rejection, bounded retries,
Retry-After, timeout/HTTP errors, size/type and XML/ZIP safety. These are contract
tests, not proof of an operational live integration.

Run workers with only staging INSERT/SELECT permissions and private raw storage;
no website, approval or production credentials/mounts. Local SQLite is only an
isolated prototype backend. For PostgreSQL/PostGIS, migrations, least-privilege
roles and the disposable integration test, follow [migrations/README.md](../migrations/README.md).
The local container has no network. Docker Desktop and the seven PostGIS integration tests have now been verified
locally; see the Docker verification section in the migration guide. Do not publish source files with unresolved
redistribution rights. Raw bytes remain under ignored staging, not Git.

## Tests

```sh
.venv/bin/python -m pytest
.venv/bin/ruff check collector tests/unit/test_collector*.py tests/data/test_p0_review.py tests/security tests/integration
.venv/bin/ruff format --check collector tests/unit/test_collector*.py tests/data/test_p0_review.py tests/security tests/integration
.venv/bin/mypy collector --ignore-missing-imports
.venv/bin/alembic -c migrations/alembic.ini upgrade head --sql
```

Tests begin with failing assertions before implementations: fixture ingestion,
hierarchy/schema failure, malformed workbooks, HTTP policy, versioning, no-op
reruns, acquisition errors, mock approval rejection, destination protections,
formula-safe CSV, manifest checksums and exact P0 input preservation. PostgreSQL
is skipped locally unless an explicitly disposable test URL is provided. The
`collector-postgis` CI job provisions an isolated PostGIS database and runs the
fixture through acquisition, staging, rerun and export after applying migrations. No test requires
government network access. Browser checks are separate from collector validation.

## Known gaps

Official current PSGC download/layout and 2024 POPCEN evidence/linkage remain
unverified. Existing population comes from a previously user-reviewed
transcription, not a newly acquired census artifact. Barangays are explicitly an
unofficial unversioned snapshot. Some overview/directory fields and original
source timestamps/licenses remain unavailable. No production live PSGC downloader, S3 integration,
review UI, production adapter, Pandera tabular rules, Airflow or generic spider is
introduced. Single-source serial runs are the supported prototype workflow;
concurrent imports can roll back on uniqueness conflicts and require retry.
PostgreSQL runs require an external migration/connection setup; the fixture CLI
intentionally uses the isolated SQLite backend. These gaps block a claim that
all P0 datasets are freshly collected, authoritative and ready for publication.

## Authorized live P0 practice run

A separate bounded smoke check now exercises the existing provincial URL and
budget API base without enabling the synthetic-only PSA importer:

```sh
.venv/bin/python -m collector.practice --authorize-live-practice \
  --target data/staging/practice-NEW-UNIQUE-NAME
```

This command needs outbound HTTPS and system `curl`. It checks three robots files,
then fetches one public page from each enabled legacy source. It does not invoke
a broad scrape or change source configuration. It pins each TLS connection to a
DNS-validated public IP, verifies the actual remote IP, bypasses environment proxy
settings, limits each response to 2 MB/25 seconds, and refuses automatic redirects.
Only the specific same-host provincial About-page canonical redirect is accepted,
with robots evaluation and a new pinned connection. Cookies are discarded, raw
bodies and allowlisted HTTP metadata retained, and no protective challenge is
bypassed. Unknown rights remain pending; these private snapshots cannot be taken
as redistribution approval. Main PSA HTTPX transport remains disabled.

The November 3 run is retained under `data/staging/practice-2026-11-03-02/`:
6 HTTP requests, 8 hashed files plus manifest, successful provincial HTML and
FY2027 budget overview (4 datasets). PSA collection was skipped: current config
is disabled, and robots response included `cf-mitigated: challenge`. The provincial
page redirected from `/about-pangasinan/` to `/the-province/about-pangasinan/`.
Its population paragraph explicitly references 2020; it is not 2024 POPCEN evidence.
The budget overview is an independent, unofficial proposal comparison; document
and project-level verification were outside this smoke check.

An earlier trial is retained under `practice-2026-11-03-01/`: it recorded the
provincial 301 and a 404 from the practice runner's mistaken `/overview` suffix.
A regression test now requires exactly the existing collector's configured API
base, and the corrected run uses that endpoint. No budget configuration or
approved snapshot was changed. Practice tests were added red-first; final local
suite: 350 passed, 1 skipped; Ruff and mypy passed. PostgreSQL remains the skipped
local integration test. Other P1/P2 websites have not yet been exercised.

Docker verification is now complete: see [runtime results and commands](../migrations/README.md#docker-verification-november-3-2026). The earlier skipped Docker/PostGIS notes above describe the initial prototype validation, before Docker Desktop was started.
