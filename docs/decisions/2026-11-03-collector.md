# Offline P0 evidence review

Repository discovery found reusable reviewed LGU/population data, geography
provenance and a separately approved FY2027 compiler. Keep these unchanged and
reuse validation for review exports rather than adding another publication path.
The official requirements brief is present as doc/BETTER PANGASINAN WEB CRAWLER.md,
rather than the BETTER PANGASINAN.md name referenced in AGENTS.md.

Implement synthetic-only XLSX parsing and isolated SQLite staging first, with
SQLAlchemy/PostGIS migration support for a separately provisioned database.
Source registry stays disabled; HTTPX is test-harness-only until actual-destination
and network egress enforcement are verified. Do not substitute application-level
DNS checks for those controls. No source access or license approval is inferred.

P0 exports review existing records in brief order, retain uncertainty, and reveal
missing fields/UTC source timestamps rather than fabricating them. No automated
approvals, production writes or new geographic allocations exist.

Full-suite validation also reproduced an existing geodesic roundoff failure for
identical coordinates. Explicitly return zero for identical endpoints; retain all
original source coordinates and warnings. Existing regression test covers this.

Final local validation: clean hash-locked Python 3.12 environment, 342 pytest
checks passed and one disposable PostgreSQL test skipped because Docker's daemon
is absent. Ruff, mypy, the 25-page production build, PostgreSQL migration SQL
rendering and Compose configuration validation passed. The final lockfile audit
reported no known vulnerabilities. CI PostGIS execution and live government-source
verification were not performed locally. Generated P0 manifest verifies 19 input
hashes and 11 output hashes; repeated fixture acquisition creates zero new versions.
