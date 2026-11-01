# Better Pangasinan — Official Web Research Handoff, Batch 01

**Collected:** 2026-10-31  
**Repository target:** `jadolation/betterPangasinan` (`main`)  
**Status:** Preliminary source-backed research. **NOT approved production data.**

## Dataset inventory

| Dataset | Rows | What has actually been collected |
|---|---:|---|
| `lgu_registry_2024` | 48 | Official Pangasinan city/municipality names, 10-digit PSGC, income classification, 2024 POPCEN, and published district grouping |
| `statistics` | 30 | Population, urbanization, economic, agricultural, and fisheries indicators with reference period and source |
| `budget_observations` | 15 | Selected annual and supplemental budget amounts in provincial resolutions and news reports (includes 2027 **proposal**) |
| `legislation_index` | 15 | Provincial ordinance/resolution index entries with dates and source references; titles summarized for research purposes |
| `project_leads` | 4 | Planning-stage project/program mentions, **not verified awarded contracts** |
| `hospital_directory_observations` | 12 | Hospital/chief names as listed on official directory, **current officeholder dates unverified** |
| `source_inventory` | 47 | Official institutional page/document links and explicit review-status notes |
| `collection_gaps` | 13 | Workstream-specific missing evidence and recommended review owners |

**Total structured observations:** 124 across the first six datasets, plus 47 source records and 13 gap entries. Every row should retain its original source URL and review notes.

## Confirmed highlights from web pages

- **Provincial population, 2024:** 3,188,540 (PSA). The 48 city/municipal figures sum to the same total.
- **Geography:** Four cities, 44 municipalities, and 1,364 barangays (PSA). The LGU table lists 10-digit PSGC codes with leading zeros; preserve as strings.
- **Provincial GDP, 2025:** PHP 408.45 billion; reported growth 4.3% (PSA Provincial Product Accounts). GDP is **not** government revenue or budget.
- **Provincial approved annual budget, 2026:** PHP 8,379,222,529 reported by the provincial government; the original approved appropriations should still be obtained for line-item ingestion.
- **Provincial proposed annual budget, 2027:** PHP 9,329,848,870, explicitly **proposed**, not yet an approved budget as of the source report.
- **Palay production, 2025:** 1,213,312 metric tons (PSA report).
- **Full Disclosure Policy:** Pangasinan provincial and Bolinao pages publish indexes of periodic financial, procurement, SEF, NTA, and LDRRM reports; index discovery is **not equivalent to verifying all document contents**.

## Official starting references

- Philippine Statistics Authority, Pangasinan PSGC: https://psa.gov.ph/classification/psgc/citimuni/0105500000
- Provincial cities/municipalities: https://www.pangasinan.gov.ph/city-municipalities/
- Provincial Finance: https://www.pangasinan.gov.ph/bacs/financial-management/
- Provincial Procurement/BACS: https://www.pangasinan.gov.ph/bacs/
- Annual Procurement Plan 2026: https://www.pangasinan.gov.ph/bacs/annual-procurement-plan-2026/
- Ordinances: https://www.pangasinan.gov.ph/kind/ordinances/
- Citizen's Charter: https://www.pangasinan.gov.ph/citizens-charter/
- COA audit download entry: https://www.coa.gov.ph/wpfd_file/pangasinan-compliance-audit-report-2024/
- NAMRIA Geoportal: https://geoportal.gov.ph/

All 47 URLs are catalogued in `source_inventory.csv/json`.

## Critical verification and publication rules

1. **This export does not conform automatically to the repository's production JSON Schemas.** Its files are research-stage evidence tables, not `data/production/*.json` replacements.
2. The PSA demographic table is a source snapshot with 2024 census population values; confirm against the latest PSGC release and accepted geographic registry at import time.
3. Budget rows from the Sangguniang Panlalawigan are **budget-review resolution observations**. `operative in PART` is preserved; do not treat all as unconditional full approvals. Supplemental budgets and annual budgets must never be summed as interchangeable values.
4. The 2027 provincial figure is a **proposal**, not an actual appropriation or expenditure.
5. Some PDF sources were indexed by search, but screenshot verification was unavailable; these rows are explicitly flagged for manual document review. Do not publish those as fully verified records.
6. Legislation titles in the research tab are shortened paraphrases for discovery. Extract the exact official titles and verify effective status before publishing legal content.
7. The four projects/programs are **reported planning leads**, not awarded public contracts, operational services, or completed public works.
8. The hospital directory is an official listing, but the page does not establish a current `as_of` date for each named officeholder.
9. COA documents were **located only**. No adverse finding, audit opinion, financial liability, or official wrongdoing conclusion was extracted.
10. No official municipal/city boundaries, procurement award line items, actual expenditure line items, or reviewed local service fees were imported in this batch.
11. Never assume that an unavailable document means an LGU failed its disclosure obligations.
12. Respect use/republication terms, including GIS data licenses and sensitive records.

## Recommended ingestion path

1. Register sources in a reviewed staging area, keep original URLs and retrieval dates.
2. Import 48 LGU PSGC identifiers into a reviewed geographic registry.
3. Review each record against its original source; assign the actual government entity and date.
4. Normalize the data into `schemas/record.json` and module-specific schemas from the current repo; use a reviewed source link and cross-reference IDs.
5. Run `python -m pytest`, `python build.py`, and the Playwright checks before production release.
6. Preserve separate states for missing, unreviewed, source-confirmed, approved and published material.

**Suggested review order:** `LGU Registry` → `Source Inventory` → `Statistics` → annual budget resolutions → `Legislation` → procurement document details → project/contract linkage → GIS and public services.
