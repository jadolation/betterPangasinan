# Collector data dictionary

| Field | Meaning |
| --- | --- |
| id | Stable entity authority/identifier; never an approval |
| version / artifact_sha256 | SHA-256 of exact input bytes, separate from logical identity |
| collection_run_id | Unique acquisition audit; deterministic input-bound ID for P0 review |
| retrieved_at | Original UTC acquisition where known; null with reason otherwise |
| source_published_at | Original publication date, never substituted with review time |
| reference_period / release | Statistical period and geography vintage, independently retained |
| source_url / source_record_id | Original attributable link and upstream identifier |
| raw_values / original_source_row | Unchanged input values and headers |
| evidence | Workbook sheet/row or field-specific source/reference/hash metadata |
| missing_fields | Explicit reason for null; unknown is never zero |
| validation_status | Collected/valid/invalid/incomplete; unrelated to approval |
| review_status | Always pending in new collector outputs |
| is_mock | True for every synthetic record; cannot receive collector approval |
| coverage_status | Partial until actual required source coverage is verified |
| license_status / redistribution_review | Restrictions independent from data validation |
| created_versions | New immutable entity versions; zero on byte-identical reruns |
| changes | Added/removed/changed entity IDs compared with previous non-invalid run |

A changed artifact creates new evidence versions. `changes.changed` excludes
acquisition metadata and evidence hashes so unchanged field values are not
reported as changed facts. Invalid source rows remain in audit but create no
entity versions; duplicates are never silently selected. CSV review cells with
formula prefixes are escaped. JSON preserves the original strings.

P0 real-data envelopes preserve source-specific representations; they are not
application production schemas. Budget stages use original integer PHP amounts
and explicit nulls, with no cross-stage aggregation or provincial allocation.
