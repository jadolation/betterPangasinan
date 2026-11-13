# Better Pangasinan web crawler (P0)

One CLI for collecting, building and verifying the brief's P0 datasets
(`doc/BETTER PANGASINAN WEB CRAWLER.md` §2, §3, §6, §13). Outputs are review-only
staging files. Nothing here approves or publishes data.

```sh
.venv/bin/python web-crawler sources                       # registered sources
.venv/bin/python web-crawler collect --authorize-live --build   # live capture into a new run
.venv/bin/python web-crawler build  <run-id>               # rebuild outputs offline from evidence
.venv/bin/python web-crawler verify <run-id>               # independent checks; updates doc/P0-VERIFICATION.md
.venv/bin/python web-crawler status <run-id>               # current | stale | unverified
.venv/bin/python web-crawler runs                          # list runs
.venv/bin/python web-crawler budget-review                 # FY2027 read-only review export
```

Bounded first capture of a new or changed source:
`collect --authorize-live --source pangasinan-gov --page lgus --lgu-limit 3`.

## Requirements

- `.venv` with `requirements.txt`; Node with the pinned `@playwright/test` (`npm ci`).
- Current stable Google Chrome. The shared preflight `scripts/browser-security.cjs`
  enforces the sandbox and a minimum version; it opens a visible window.
- `PSA-TOKEN` in the environment or `.env`. It is sent only as the documented
  `token` query parameter, redacted from saved artifacts, and never written to URLs
  in the manifest. The verifier scans evidence for it.

## Sources (`crawler/sources.py`)

| Source | Method | What it provides |
| --- | --- | --- |
| `psa-psgc` | PSA Classification API (`Classification API Documentation.yaml`) | Release discovery, PSGC hierarchy, income/urban-rural class, populations by year |
| `pangasinan-gov` | Visible Chrome, robots.txt-checked | About/Geography statements, the 48 LGU pages (district, land area, barangay count, links) |

PSA release discovery probes `/psgc/{version}/provinces?reg=1&prv=55` for quarterly
version names from the current quarter backwards and records every probe. A version
with zero Pangasinan rows is treated as unreleased. Geography comes from the newest
release; populations come from the newest release that publishes them (these can
differ — both are recorded on every record).

To add a source: write `collect_<name>(run, options)` that saves evidence with
`run.add_evidence(...)`, register it in `SOURCES`, then map it in `build.py`. Capture
and inspect a bounded live response before writing the mapping.

## Run layout (`data/staging/web-crawler/runs/<run-id>/`, ignored by Git)

| Path | Contents |
| --- | --- |
| `manifest.json` | sources, probes, browser version, evidence inventory (URL, UTC time, HTTP status, response and artifact SHA-256, redaction flag), errors |
| `evidence/` | immutable raw captures; never rewritten |
| `output/pangasinan_overview.json`, `pangasinan_lgus.json`, `pangasinan_barangays.json` | records with per-field `{value, evidence}` or `{value: null, missing_reason}` |
| `output/lgu_directory.csv` | flat LGU directory for review |
| `output/inconsistencies.json` | disagreements between or within official sources, unresolved |
| `output/collection_gaps.csv`, `source_inventory.csv`, `collection_log.csv` | brief §15 deliverables |
| `output/build.json` | output hashes and counts |
| `verification.json` | verifier result bound to manifest and output hashes |

Field evidence is one of: a JSON pointer into a PSA artifact, an exact quote from a
captured page's text, or an exact link (`WEBSITE`/`FACEBOOK`) on a captured page.

## Rules the code enforces

- PSGC codes are 10-digit strings. Newer PSA releases drop the leading zero; the
  published form is kept in `psgc_as_published`.
- Parents come from the record's `reg`/`prv`/`mun` fields and must agree with the
  code prefix, exist, and have the right level. Pagination must cover the API count.
- Unknown values are `null` with a reason, never `0`. Conflicting official
  statements are reported, not chosen between. Site pages are matched to PSGC by
  exact normalized name only; ambiguity is reported.
- Requests: allowlisted hosts, public DNS only, pinned and checked peer IP, no
  redirects (API), byte and time limits, robots.txt and crawl delay respected,
  no challenge solving. Browser runs block non-same-origin and non-document/script/style requests.
- Records stay `review_status: pending`, `is_mock: false`, `publication_status: not_approved`.

## Verification

`verify` re-reads raw evidence without `build.py`'s parsers, rebuilds into a scratch
directory to prove reproducibility, re-reads every cited value from its artifact,
checks hierarchy, counts, missingness and review barriers, and writes a completeness
matrix against the brief's §2–3 fields. It updates only the generated block of
`doc/P0-VERIFICATION.md`; the human checklist above that block is maintained by people.
`validation_status: passed` means structurally sound evidence for human review —
not complete, not integration-ready, not approved.

## Tests

```sh
.venv/bin/python -m pytest tests/web_crawler     # replay tests use the newest real run; skip if none
node --test tests/web_crawler/*.test.cjs
```
