# National Budget Integration: Reviewed Implementation Plan

## Scope And Findings

Analysis requested, not implementation authorization. Preserve Python static generation, vanilla JavaScript, current branding, existing datasets and public-only deployment. No push, merge or deployment. Historical GAA ingestion and migration of unrelated research datasets are out of scope for the first implementation.

Inspected local `main` at `8479f6d`; initially the only untracked content was `Better_Pangasinan_Research_Batch_01/`. This is local repository inspection, not confirmation that remote main has no newer commits.

The repository has 12 registered production datasets, currently empty; research tables are not production replacements. `build.py` validates before generating flat HTML routes and allowlisted public assets. Default builds also rewrite root compatibility outputs. Use isolated builds with `--no-root-compatibility` during development. Never edit generated root HTML as source.

The November 1 live API samples report source commit `a0caa778442cdae5583f5a006ea7401dab00e5ac`, build time `2026-10-26T08:46:14.383Z`. These were discovery requests, not a persisted or complete collection.

| Pangasinan query | API-reported rows | Rows sampled | House comparison |
| --- | ---: | ---: | --- |
| dpwh | 696 | 1 | hgab3 |
| fmr | 32 | 1 | hgab2 |
| hfep | 4 | 1 | hgab2 |
| nia | 0 | 0 | hgab2 |

Do not present these counts as verified geographic coverage. NIA's empty result has null monetary sums, not proof of no irrigation funding. District discovery defaults to 50 of 254 records and must also be paginated.

A filtered directory request (`districts?q=Pangasinan&limit=10`) returned six district IDs, `leg:pangasinan:1st` through `leg:pangasinan:6th`, and four unique office IDs. The 1st DEO serves district 1 (Tier A); 2nd DEO serves districts 2 and 4 (Tier B); 3rd DEO serves districts 5 and 6 (Tier B); 4th DEO serves district 3 (Tier A). These are API associations, not independently verified territorial boundaries. Retrieve district details for exact budget-record labels before office collection.

District `headline` NEP is whole-office scope while its House figure is named-project scope. Use `fy2027_vs_proposal` for the API's like-for-like office comparison, not subtraction of headline values. Preserve residuals and office-change/no-office buckets without assigning national residual amounts to Pangasinan.

The sampled third-district detail confirms the exact FY2027 published office label `Pangasinan 4th District Engineering Office` and supplies `projects_api`; collect the other three office details rather than extrapolating their labels. Its named-project NEP is PHP 625,600,000 while its whole-office NEP is PHP 663,798,000, demonstrating why headline comparisons are unsafe.

Mapandan's live sample contains `house-reading:3959` and `house-reading:3923`: PHP 44 million and PHP 5 million respectively in each proposal, PHP 49 million per version, zero difference; the second retains `nep_evidence_review`. Preserve the original response as a regression fixture during implementation, with retrieval metadata, not as approved production data.

## Required Corrections To Specification v1.0

1. Separate collection inclusion, title evidence, geographic assignment and publication approval. HFEP's `q=Pangasinan` sample returns `Region I Medical Center`, whose displayed title does not contain Pangasinan. Record a `province_query_match` reason without asserting `province_title_explicit` unless the title actually supports it.
2. Add shared/umbrella-allocation scope. The DPWH query returns a PHP 1 billion Central Office line covering named projects across numerous regions. Its whole amount is not Pangasinan-attributable. Preserve it separately as a shared allocation; never manufacture a geographic share or drop it solely for its NCR office region.
3. Replace scalar LGU assignment with reviewed many-to-many project/LGU associations. Each association needs PSGC, evidence IDs, review status, reviewer and review time. Do not duplicate money for multi-LGU records; municipal views are overlapping and not additive.
4. Keep `dataset:upstream_id` as identity within FY2027, with fiscal year included in the broader storage namespace. Treat stability across source revisions as unproven. Preserve snapshot-qualified versions and conflict evidence; never silently overwrite reviewed data on refresh.
5. Define independent publication, geographic and comparison/source-review states. Approval can authorize faithful publication of a flagged comparison, not erase or convert the upstream flag into verified evidence. Human approval must be explicit and bound to record/snapshot checksums; agents do not self-approve.
6. Retain nulls, source-supplied deltas and counts of rows with known amounts. Missing-version arithmetic is not ordinary subtraction. Keep comparable-row change metrics distinct from all-selected-row version sums. Never invent a zero-valued missing version on a project card.
7. Group summary figures by House reading. A mixed-program overview may show separately labeled hgab3 DPWH and hgab2 other-program totals, not a single unlabeled House total. Never sum repeated query-level `data.sums`, which already cover the entire matching set on each page.
8. Use `national-budget.html` initially, matching existing flat routes and relative project-subpath URLs. A clean directory route requires a deliberate builder change and is not necessary for this release.
9. Preserve document hashes, original and mirrored URLs, and page-number conventions. Non-DPWH rows can have null hgab3 page/doc fields while supplying an hgab3 PDF URL because upstream verified identical reading lists. Do not synthesize missing raw fields or reject this valid structure.
10. Successful zero matches require a valid response envelope and metadata. A zero-byte body, invalid JSON, missing metadata, failed request or incomplete pagination is an error, not an empty dataset.

## Research Batch Assessment

All eight JSON/CSV pairs were inspected, alongside the brief and the workbook's supported text rendering. Counts match the brief: 48 LGUs, 30 statistics, 15 budget observations, 15 legislation entries, four project leads, 12 hospital observations, 47 sources and 13 collection gaps. This is 184 logical rows, including 124 domain observations, not twice that number because of format mirrors. JSON/CSV parity was inspected, not established by an executed parser test.

- The registry preserves 10-digit PSGC strings, four cities and 44 municipalities; populations sum to 3,188,540. Its filename is not a universal vintage: 2024 population is combined with a PSGC table labeled July 31, 2025. District and income-class effective dates require separate verification. District provenance refers to the provincial directory in the source inventory but LGU rows link only to PSA.
- The 76 domain rows with source IDs resolve to the 47-source inventory on inspection; LGUs use URLs without source IDs. No reviewed national-budget line dataset or Mapandan API snapshot is supplied in this batch. The Mapandan regression capture therefore comes from live API discovery, not an existing research fixture.
- Municipal budget observations cover only 12 of 48 LGUs, including ten annual budgets and two supplemental budgets; no city budget is represented. Do not present this as comprehensive fiscal coverage. The provincial 2027 PHP 9,329,848,870 proposal is local government finance, not a national NEP allocation.
- Bayambang and San Quintin PDF-derived amounts are labeled `reported_by_official_html` (`budget_observations.json:59-70,171-182`). Correct evidence-type metadata only after review; do not reinterpret these as approved production values.
- Sual's PHP 505 million is explicitly operative in PART (`budget_observations.json:73-84`), not a reviewed wholly operative appropriation. San Quintin's resolution date is blank. Both require original-document review.
- Legislation titles are paraphrases and full text is unreviewed. Four project leads share one planning article and include program aggregates/master planning, not contracts. All hospital officeholder as-of dates are null; Bayambang District Hospital appears in legislation but not the 12-row hospital directory, so the latter is not established as exhaustive.
- Workbook rendering appears to round several monetary values relative to JSON/CSV. Raw stored cell precision/formulas were not established; do not use rendered spreadsheet values as authoritative amounts. Preserve centavos for local research finance even though this national API uses integer pesos.
- The brief's cautions are consistent with these findings: discovery is not document verification, currentness, lawful GIS redistribution, audit findings or publication approval. Keep unrelated research remediation separate from the national-budget feature.

## Implementation Sequence

### 1. Contracts And Research Staging

- Keep the supplied batch internal. Register research sources and review the 48-LGU registry before enabling municipal collection; preserve PSGC strings and the census reference date. Do not silently insert research rows into existing production datasets.
- Add separate national-budget schemas for project, office, batch, review decisions and publication manifest. Retain complete raw envelopes plus normalized records referencing raw checksums.
- Model query provenance, independent review states, multi-LGU associations, shared-allocation scope, document evidence and version-specific amounts. Use integer pesos in Python; validate safe integers in JavaScript or transport monetary values as decimal strings and use BigInt consistently.
- Fixtures must cover real captured API shapes and separately labeled synthetic failures. No contractor, implementation status or coordinates may be inferred.

### 2. Reproducible Discovery And Collection

- Implement a small Python CLI under `scripts/national_budget/` for discovery, fetch, normalization, validation and compilation; avoid six empty wrapper modules if fewer cohesive modules suffice.
- Fetch overview, every district-directory page, Pangasinan district details and exact `matched_label` office names. Deduplicate offices by supplied identity, preserving shared districts and tiers. Office queries must use published labels, not card shorthand.
- Complete province queries for all four datasets with page size at most 200. Capture exact URL, UTC time, HTTP status, raw-byte SHA-256, meta, disclaimers and errors for every attempt.
- Follow `data.next_offset` for project lists. Validate advancing offsets, totals, returned row counts, duplicate IDs and final unique coverage; explicitly support legitimate total-zero responses. Implement district pagination against its actual response contract rather than assuming project-list shape.
- Apply bounded retries, timeout, Retry-After handling and modest concurrency; never retry permanent 4xx indefinitely. Restrict API requests and redirects to trusted HTTPS hosts.
- Detect changed source commit/build and inconsistent records across pages and details. Mark affected queries incomplete; resume only against the same snapshot, otherwise start a new batch. Do not copy upstream portal's 4,000-row cutoff as silent completeness.
- Retrieve detail evidence with caching and bounded requests for records intended for review. Encode opaque IDs exactly once.
- Persist a query-level coverage matrix: requested, complete, failed, deferred, valid-zero; raw/unique counts and review counts are distinct. Reconcile per-version row sums with API whole-query sums without summing page metadata.
- Only after registry review, run configured representative LGU queries, then remaining controlled batches. Regional context is evidence, not an unconditional exclusion rule; NIA lacks region and shared national lines can be coded elsewhere.

### 3. Review And Publication Gate

- Normalize into candidate records; merge provenance by identity only within a consistent snapshot. Title similarity is never a deduplication key.
- Generate an internal report separating title matches, query-only matches, office-only records, shared allocations, ambiguous geography, evidence warnings and exclusions.
- Require a human decision identifying reviewer, UTC time, exact snapshot/record hash, permitted publication scope and evidence for each geographic association. Unresolved budget-source flags remain visible even when publication is authorized.
- No approved records is a supported first-release state. Ship a truthful unavailable dashboard rather than promote API data automatically. Reviewer identity/approval decisions are release prerequisites, not agent defaults.
- Compile only explicitly approved, schema-valid inputs; reject stale hash approvals, mock data, missing evidence, unresolved conflicts and malformed stages. Do not read candidates as a fallback when approved inputs fail.
- Generate manifest/projects/offices/coverage/sources under `public/data/national-budget/2027/` as part of the build, not before a build that deletes `public/`. Validate before mutating output. Keep immutable approved source snapshots outside generated `public/`.
- Preserve the last approved snapshot when refresh fails, clearly dated. Publish incomplete coverage only when explicitly approved and prominently disclosed; never label it exhaustive.

### 4. Static Interface

- Add `src/pages/national-budget.html`, scoped CSS/JS and a Projects & Tools navigation entry, preserving shared header, typography, logo and hero.
- Load approved local JSON only. Keep national proposals out of `finances.json`, existing generic projects and their aggregations; do not extend `assets/modules.js` dataset registration merely to reuse generic financial rendering.
- Provide explicit geographic-match and office lenses, multi-LGU filtering, program/office/status/stage filters, sorting, evidence panels and filtered CSV export. Label row counts as budget comparison records rather than unique construction projects, since HFEP may have separate funding-column rows per facility.
- Show proposal-not-spending, unofficial-source, coverage and no-allegations notices. Shared allocations and office scopes must not inflate geographic cards. Never imply an LGU has no projects when no reviewed match exists.
- Render untrusted titles/flags as text; validate HTTPS link destinations. Escape CSV quoting and spreadsheet formula prefixes, including leading whitespace/control characters; include original IDs, reading and snapshot identity.
- Separate loading, unavailable, invalid-data, no-approved-snapshot and no-filter-matches states. Include useful static no-JavaScript explanation and download links where data exists. Keep historical GAA hidden or explicitly deferred.

### 5. Verification And Release Evidence

- Test null/zero, safe integer bounds, unknown stages, mismatched totals, same query across pages, shared offices, multi-LGU overlap, umbrella allocations and returned-title/query mismatches.
- Test all API failures in the original specification, district pagination, changed snapshots, resumed batches and approval invalidation after edits. Use deterministic local fixtures in CI, not live API dependencies.
- Test exact Mapandan per-version totals and evidence flag; never a PHP 98 million combined figure. Test zero NIA-style responses retain unknown monetary sums.
- Add artifact tests proving raw/review/research/XLSX/test files are absent from `public/` and existing 12-dataset gates still apply. Keep existing empty-production assertions unless deliberately migrating those datasets; adding the separate module does not require approving unrelated research.
- Run `python -m pytest`, isolated production and test builds, then `npm run test:browser` with its build side effects understood. Verify all requested viewport widths, keyboard flow, source links, filtered CSV, stage-specific totals, subpath hosting, no-JavaScript content and unavailable states; capture desktop/mobile screenshots.
- Update README/methodology only during authorized implementation. Final report must distinguish discovery observations, complete collection results, approved records and pending review, cite snapshot dates and test outcomes, and confirm no push/merge/deployment.

## Release Boundary

Code completeness does not imply data approval. Full approved provincial figures remain unavailable until complete collection, scope classification, reconciliation and human review succeed. Historical GAA ingestion, general research promotion, exact original legal titles, procurement awards and current hospital officeholders remain separate workstreams.
