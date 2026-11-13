# P0 verification checklist

Boxes are ticked only by a human reviewer. "Automated" notes record what `web-crawler verify`
and agent review established, with run and hash references; they are evidence for human review,
not approval. Run `.venv/bin/python web-crawler status <run-id>`: results are void once stale.

Current run: `20261113T080554Z-9887` (manifest SHA-256 `688a86739a623dbf7bbb1cc09116f99769749a49d548b1e3b77c77a64768bf18`),
PSA geography release Q3_2026, population release Q1_2026, OSM extract `philippines-261112.osm.pbf`,
stable Chrome 157.0.8103.51.

- [ ] Live PSA capture of the actual current release, complete pagination and hashes.
  Automated: release discovered by probing (Q4_2026 has 0 rows; Q3_2026 newest); 3+3 pages cover API count 1,413;
  evidence hashes and token redaction pass.
- [ ] Province, cities, municipalities, barangays with unique 10-digit string PSGCs and typed parents.
  Automated: 1 / 4 / 44 / 1,364; every PSA record exported once; parents exist with correct level.
- [ ] 2024 population values, periods and geography compatibility.
  Automated: 1,413/1,413 joined from Q1_2026 (Q2_2026 and Q3_2026 publish no populations).
  Open: population release differs from geography release; PSA gives year only, no census reference date.
- [ ] Provincial overview with field-level official evidence and explicit gaps.
  Automated: 10 of 12 brief fields filled. Land area is a source conflict; seal missing. Coordinates are the
  OSM admin-centre node (Lingayen, agrees with the capital), not an official source.
- [ ] LGU directory and barangay lists with field-level evidence and explicit gaps.
  Automated: all 48 provincial LGU pages captured and matched to PSGC by exact name. Coordinates 48/48 from
  OSM (18 by `ref` = PSGC, 30 by unique name inside the OSM province polygon; not official). Address 4/48
  (+1 with two candidates) and contact 7/48 from LGU websites, as published and marked for review.
- [ ] Review-only JSON/CSV, source inventory, collection log, gaps, reproducible verification.
  Automated: all outputs present; rebuild is byte-identical; 5,934 cited values re-read from evidence.
- [ ] FY2027 read-only review against the approved snapshot (`web-crawler budget-review`); not yet re-run on
  the new tool outside tests.
- [ ] Integration schema compatibility, then a separate human publication review.

## Needs fixing next

1. **Human decisions on source conflicts** (`output/inconsistencies.json`):
   - Provincial land area: About page "approximately 536,818 hectares" vs Geography page "545,101 hectares".
   - Income class differs for 27 LGUs between pangasinan.gov.ph and PSA Q3_2026 (site likely predates the
     latest reclassification; confirm the authoritative DOF/PSA source and date before display).
   - 2020 population: Bugallon site 23,749 vs PSA 74,962 (site value looks wrong); Infanta 26,262 vs 26,242.
   - PSA Q3_2026 returns U+FFFD in place of "ñ" for 8 barangay names (Q1_2026 is correct). Keep originals;
     decide display name policy.
2. **Address and contact gaps** (`output/collection_gaps.csv`): 21 LGUs have no website linked on the
   provincial site; 16 linked sites could not be collected — DNS does not resolve (Anda, Calasiao), invalid
   TLS certificate (Asingan, Balungao, Bani, Bugallon, Natividad, Villasis), HTTP 403 on robots.txt (Laoac,
   Mapandan, Pozorrubio, Santa Barbara, Sison), off-site redirect (Mabini), non-.gov.ph domain (Santo
   Tomas), Urdaneta peer mismatch; 6 captured sites state no address. DILG national has no LGU hall
   directory (only barangay officials and CART). Remaining options: LGU Facebook pages are out of scope
   (login/terms); a reviewed manual-entry file with source links, or contacting LGUs, is a human decision.
   - Malasiqui's site shows template contacts ("(075) 123-4567"); its address and email are flagged.
   - Dagupan publishes two addresses (City Hall Complex vs 2nd Floor); reviewer picks.
   - Phone labels come from the preceding page line and can be noisy (e.g. Facebook URLs on Bolinao).
3. **Coordinates are OpenStreetMap town-centre nodes**, not hall locations or official data (ODbL,
   attribution required). An official alternative needs NAMRIA boundaries (brief §5, P1).
4. Other gaps: seal/logo and usage permission; land area for Agno, San Nicolas and Tayug (not stated on their provincial pages); 21 official websites.
5. Capital (Lingayen) rests on 16 consistent statements on LGU pages, not a dedicated provincial statement;
   reviewer should confirm that is acceptable evidence.
6. Repository cleanup still pending approval: superseded `scripts/psa-download.cjs`,
   `scripts/province-directory.cjs` and tests that import the deleted `collector` package make the full test
   suite fail at collection.

## Historical (pre-reset) notes

Runs under `data/staging/web-crawler/psa-20261113-*` and `budget-review-20261113` came from the removed
`scripts/p0_*.py`. They hard-coded release Q2_2024 although Q3_2026 is available; treat their counts as
historical only.

<!-- web-crawler:auto:start -->

## Latest automated verification — run `20261113T080554Z-9887`

Generated by `web-crawler verify`. Automated results are evidence for human review, not approval. Re-run `web-crawler status` to see whether these results are stale.

- Verified at: 2026-11-13T08:14:00Z
- Manifest SHA-256: `688a86739a623dbf7bbb1cc09116f99769749a49d548b1e3b77c77a64768bf18`
- PSGC release: Q3_2026; population release: Q1_2026
- Structural validation: **passed**; collection completeness: **partial**; publication: **not_approved**
- Source errors during collection: 22

| Check | Result | Detail |
| --- | --- | --- |
| evidence_hashes_match_manifest | pass | 259 artifacts |
| no_unlisted_evidence_files | pass |  |
| no_credential_in_evidence | pass | scanned with the configured PSA token |
| no_credential_in_recorded_urls | pass |  |
| rebuild_reproduces_outputs | pass |  |
| required_outputs_present | pass |  |
| psa_pages_cover_declared_count | pass | 1413 rows, API count 1413 |
| psgc_ten_digit_strings | pass |  |
| psgc_unique | pass |  |
| every_psa_record_exported_once | pass |  |
| parents_exist_with_correct_type | pass |  |
| overview_counts_match_raw | pass | {"City": 4, "Mun": 44, "Bgy": 1364} |
| lgu_and_barangay_datasets_partitioned | pass |  |
| field_values_match_cited_evidence | pass | 5934 evidenced fields re-read |
| missing_values_have_reasons | pass |  |
| no_unevidenced_zero_values | pass |  |
| records_review_pending_and_not_mock | pass |  |
| directory_csv_matches_lgu_json | pass | 48 rows |

### Field completeness (brief §2–3)

| Overview field | Status |
| --- | --- |
| official_name | filled |
| psgc | filled |
| region | filled |
| capital | filled |
| population_2024 | filled |
| number_of_cities | filled |
| number_of_municipalities | filled |
| number_of_barangays | filled |
| land_area_ha | conflict |
| coordinates | filled |
| seal_logo | missing |
| official_website | filled |

| LGU field | Filled | Missing | Conflict |
| --- | --- | --- | --- |
| name | 48 | 0 | 0 |
| psgc | 48 | 0 | 0 |
| classification | 48 | 0 | 0 |
| legislative_district | 48 | 0 | 0 |
| population_2024 | 48 | 0 | 0 |
| land_area_ha | 45 | 3 | 0 |
| barangay_count | 48 | 0 | 0 |
| website | 27 | 21 | 0 |
| facebook | 46 | 2 | 0 |
| address | 4 | 43 | 1 |
| contact | 7 | 41 | 0 |
| coordinates | 48 | 0 | 0 |

### Inconsistencies for review

- income_classification_differs: 27
- placeholder_contact_on_lgu_site: 1
- population_2020_differs: 2
- provincial_land_area_conflict: 1
- source_encoding_defect: 8

Details: `data/staging/web-crawler/runs/20261113T080554Z-9887/output/inconsistencies.json`, `collection_gaps.csv`, `verification.json`.

<!-- web-crawler:auto:end -->
