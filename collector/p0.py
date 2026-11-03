"""Read-only review of repository P0 evidence; never a new source verification."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from collector.exporters import safe_target, write_csv, write_json
from scripts.geography_data import publication_payload as geography_payload
from scripts.government_directory import publication_payload as government_payload
from scripts.import_psa_lgus import normalize
from scripts.national_budget.pipeline import publication_payload as budget_payload
from scripts.provincial_reference import DATASETS as PROVINCIAL_DATASETS
from scripts.provincial_reference import publication_payload as provincial_payload


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_p0(root, target):
    """Export existing evidence in brief order with no approvals or outbound requests."""
    root, target = Path(root).resolve(), Path(target).resolve()
    safe_target(target)
    # Restrict this adapter independently: callers must never point it at source inputs.
    if target == root or (
        target.is_relative_to(root) and not target.is_relative_to(root / "data/staging")
    ):
        raise ValueError("P0 output inside the repository must be under data/staging")
    registry_path = root / "pangasinan_lgu_registry_staging.json"
    starter = read(registry_path)
    original_lgus = {row["psgc"]: row for row in starter["lgus"]}
    source_path = root / "data/production/sources.json"
    sources = {r["id"]: r for r in read(source_path)}
    existing = read(root / "data/production/lgus.json")
    profile = read(root / "data/production/province_profile.json")
    normalized = normalize(
        read(registry_path),
        checksum(registry_path),
        sources["source-psa-psgc-20250731"]["accessed_date"],
    )
    if normalized["lgus"] != existing or normalized["province_profile"] != profile:
        raise ValueError(
            "Existing reviewed PSGC registry/profile differs from preserved transcription"
        )
    geography = geography_payload(root)
    geo_manifest = geography["data/geography/manifest.json"]
    raw_barangays = geography["data/geography/barangays.json"]
    government = government_payload(root)["data/government-leadership.json"]
    districts = {
        code: district
        for district in government["districts"]
        for code in district["lgu_psgcs"]
    }
    government_sources = {source["id"]: source for source in government["sources"]}
    provincial_reference = provincial_payload(root)["data/provincial-reference.json"]
    about = next(
        page for page in provincial_reference["official_pages"] if page["id"] == "about"
    )
    budget = budget_payload(root)
    if budget["manifest"]["status"] != "approved":
        raise ValueError("Approved FY2027 snapshot unavailable")
    inputs = [
        registry_path,
        source_path,
        root / "data/production/lgus.json",
        root / "data/production/province_profile.json",
        root / "data/production/government_directory.json",
        root / "data/geography/manifest.json",
        root / "data/geography/barangays.json",
        root / "data/geography/municipalities.geojson",
        root / "data/national_budget/approved/candidates.json",
        root / "data/national_budget/approved/decisions.json",
    ]
    inputs.extend(
        root / "data/provincial_reference" / (name + ".json")
        for name in ("official_pages", "sources", *PROVINCIAL_DATASETS)
    )
    input_hashes = {str(p.relative_to(root)): checksum(p) for p in inputs}
    run_id = (
        "p0-review-"
        + hashlib.sha256(json.dumps(input_hashes, sort_keys=True).encode()).hexdigest()
    )
    review_metadata = {
        "collection_run_id": run_id,
        "collection_method": "repository_evidence_review",
        "source_published_at": None,
        "license": None,
        "redistribution_review": "pending",
        "independently_verified": False,
        "data_format": "json",
        "metadata_missing_fields": {
            "source_published_at": "not_supplied",
            "license": "not_supplied",
        },
    }

    files = []

    def json_output(relative, value):
        write_json(target / relative, value)
        files.append(relative)

    def csv_output(relative, rows, columns):
        write_csv(target / relative, rows, columns)
        files.append(relative)

    def evidence(source_ids, reference=None, artifact=None):
        return {
            "source_ids": source_ids,
            "source_urls": [sources[s]["url"] for s in source_ids],
            "source_agencies": [sources[s].get("publisher") for s in source_ids],
            "source_titles": [sources[s].get("name") for s in source_ids],
            "source_kind": (
                "user_reviewed_transcription"
                if source_ids == ["source-psa-psgc-20250731"]
                else "supplied_reference_information"
            ),
            "independently_verified": False,
            "license": None,
            "redistribution_review": "pending",
            "source_published_at": None,
            "metadata_missing_fields": {
                "source_published_at": "not_supplied",
                "license": "not_supplied",
            },
            "reference_period": reference,
            "source_sha256": artifact,
            "accessed_dates": {s: sources[s].get("accessed_date") for s in source_ids},
            "retrieved_at": None,
            "retrieved_at_missing_reason": "original_utc_time_not_supplied",
            "collection_method": "repository_evidence_review",
        }

    psa = ["source-psa-psgc-20250731"]
    provincial = ["source-pangasinan-province-reference"]
    overview_fields = {}
    for field in (
        "name",
        "psgc",
        "capital",
        "population",
        "cities",
        "municipalities",
        "barangays_reported",
    ):
        ids = provincial if field in ("capital", "barangays_reported") else psa
        reference = (
            profile["population_reference_date"]
            if field == "population"
            else (profile["administrative_listing_as_of"] if ids == psa else None)
        )
        overview_fields[field] = {
            "value": profile[field],
            "evidence": evidence(
                ids, reference, profile.get("source_sha256") if ids == psa else None
            ),
        }
    overview_fields["official_website"] = {
        "value": sources[provincial[0]]["url"],
        "evidence": evidence(provincial),
    }
    for field in (
        "administrative_region",
        "land_area",
        "general_location",
        "coordinates",
        "seal",
        "seal_usage_permissions",
    ):
        overview_fields[field] = {
            "value": None,
            "missing_reason": "not_collected",
            "evidence": None,
        }
    about_evidence = {
        "source_id": about["source_id"],
        "source_url": about["source_url"],
        "source_agency": "Provincial Government of Pangasinan",
        "source_title": "About Pangasinan",
        "source_page_id": about["id"],
        "retrieved_at": about["collected_at"],
        "source_published_at": None,
        "reference_period": about["as_of_date"],
        "artifact_path": "data/provincial_reference/official_pages.json",
        "artifact_sha256": input_hashes[
            "data/provincial_reference/official_pages.json"
        ],
        "hash_scope": "saved_extracted_page_collection_not_original_html",
        "collection_method": "repository_evidence_review",
        "missing_fields": {
            "source_published_at": "not_supplied",
            "reference_period": "not_supplied",
            "original_html_sha256": "not_retained_in_repository",
        },
    }
    area_paragraphs = [
        text for text in about["text"] if text.startswith("Covering approximately")
    ]
    area_match = (
        re.match(
            r"^Covering approximately (\d{1,3}(?:,\d{3})*) hectares of land,",
            area_paragraphs[0],
        )
        if len(area_paragraphs) == 1
        else None
    )
    if area_match:
        overview_fields["land_area"] = {
            "value": int(area_match[1].replace(",", "")),
            "unit": "hectares",
            "approximate": True,
            "raw_value": area_paragraphs[0],
            "evidence": about_evidence,
        }
    else:
        overview_fields["land_area"]["missing_reason"] = "source_layout_unrecognized"
    location_paragraphs = [
        text for text in about["text"] if text.startswith("Pangasinan is bounded on ")
    ]
    if len(location_paragraphs) == 1:
        overview_fields["general_location"] = {
            "value": location_paragraphs[0],
            "raw_value": location_paragraphs[0],
            "evidence": about_evidence,
        }
    warnings = [
        "Existing user-reviewed transcription; no independent live PSA or POPCEN verification.",
        geo_manifest["barangay_note"],
        "Review-only output; no new publication approval or license clearance.",
    ]
    json_output(
        "01_provincial_overview/pangasinan_overview.json",
        {
            **review_metadata,
            "review_status": "pending",
            "is_mock": False,
            "coverage_status": "partial",
            "fields": overview_fields,
            "warnings": warnings,
        },
    )

    counts = Counter(r["parent_psgc"] for r in raw_barangays)
    lgus = []
    missing_lgu = (
        "land_area",
        "official_website",
        "official_social_media",
        "hall_address",
        "contact",
        "coordinates",
    )
    for row in existing:
        district = districts[row["psgc"]]
        district_source = government_sources[district["source_ids"][0]]
        provenance = evidence(
            row["source_ids"], row["psgc_release"], row["source_sha256"]
        )
        population_evidence = evidence(
            row["source_ids"], row["population_reference_date"], row["source_sha256"]
        )
        lgus.append(
            {
                "id": row["id"],
                "name": row["name"],
                "psgc": row["psgc"],
                "parent_psgc": profile["psgc"],
                "classification": row["classification"],
                "legislative_district": district,
                "population": row["population"],
                "population_reference_date": row["population_reference_date"],
                "psgc_release": row["psgc_release"],
                "barangay_count_in_snapshot": counts.get(row["psgc"]),
                **review_metadata,
                "source_record_id": row["psgc"],
                "retrieved_at": None,
                "source_url": sources[row["source_ids"][0]]["url"],
                "source_agency": sources[row["source_ids"][0]]["publisher"],
                "source_title": sources[row["source_ids"][0]]["name"],
                "is_mock": False,
                "review_status": "pending",
                "original": row,
                "original_source_row": original_lgus[row["psgc"]],
                **{key: None for key in missing_lgu},
                "missing_fields": {
                    **{key: "not_collected" for key in missing_lgu},
                    "retrieved_at": "original_utc_time_not_supplied",
                    "source_published_at": "not_supplied",
                    "license": "not_supplied",
                    **(
                        {"barangay_count_in_snapshot": "not_collected"}
                        if row["psgc"] not in counts
                        else {}
                    ),
                },
                "evidence": {
                    "legislative_district": {
                        "source_id": "government-directory:" + district_source["id"],
                        "source_url": district_source["url"],
                        "source_sha256": district_source["sha256"],
                        "source_agency": district_source["publisher"],
                        "source_title": "Provincial city/municipality legislative district listing",
                        "retrieved_at": district_source["retrieved_at"],
                        "source_published_at": None,
                        "reference_period": None,
                        "missing_fields": {
                            "source_published_at": "not_supplied",
                            "reference_period": "not_supplied",
                        },
                        "collection_method": "repository_evidence_review",
                        "original_district": district,
                        "note": "Source-listed district membership; no project allocation or official sponsorship inferred.",
                    },
                    **{
                        key: provenance
                        for key in ("name", "psgc", "classification", "parent_psgc")
                    },
                    "population": population_evidence,
                    "barangay_count_in_snapshot": {
                        "source": geo_manifest["barangay_source"],
                        "reference_period": None,
                        "warning": geo_manifest["barangay_note"],
                    },
                },
            }
        )
    envelope = {
        **review_metadata,
        "is_mock": False,
        "review_status": "pending",
        "coverage_status": "partial",
        "warnings": warnings,
    }
    json_output("02_lgu_directory/pangasinan_lgus.json", {**envelope, "records": lgus})
    barangays = []
    geo_sources = {s["url"]: s for s in geo_manifest["sources"]}
    for row in raw_barangays:
        source = geo_sources[row["source_url"]]
        barangays.append(
            {
                **row,
                **review_metadata,
                "id": "barangay-" + row["psgc"],
                "source_record_id": row["psgc"],
                "source_agency": row["publisher"],
                "source_title": "PSGC Cloud barangay snapshot",
                "license": row["license"],
                "population": None,
                "missing_fields": {
                    "population": "not_collected",
                    "reference_period": "unversioned_source",
                    "source_published_at": "not_supplied",
                },
                "reference_period": None,
                "retrieved_at": source["retrieved_at"],
                "is_mock": False,
                "review_status": "pending",
                "original": row,
                "evidence": {
                    field: {
                        "source_url": row["source_url"],
                        "source_sha256": row["source_sha256"],
                        "source_agency": row["publisher"],
                        "release": row["release"],
                        "retrieved_at": source["retrieved_at"],
                    }
                    for field in ("name", "psgc", "parent_psgc")
                },
            }
        )
    json_output(
        "02_lgu_directory/pangasinan_barangays.json",
        {
            **envelope,
            "official": False,
            "psa_release": None,
            "source": geo_manifest["barangay_source"],
            "records": barangays,
        },
    )
    csv_output(
        "02_lgu_directory/lgu_directory.csv",
        lgus,
        [
            "id",
            "name",
            "psgc",
            "parent_psgc",
            "classification",
            "legislative_district",
            "population",
            "population_reference_date",
            "psgc_release",
            "barangay_count_in_snapshot",
            "review_status",
            "is_mock",
            "missing_fields",
            "evidence",
        ],
    )

    review, candidates, budget_sources = [], [], {}
    for record in budget["projects"]:
        upstream = record["upstream"]
        values = {
            field: upstream.get(field)
            for field in (
                "program",
                "office",
                "region",
                "nep_php",
                "hgab2_php",
                "hgab3_php",
                "house_php",
                "delta_php",
                "bridge_group",
                "held",
                "flags",
                "pdf_url",
                "reading_status",
            )
        }
        review.append(
            {
                **review_metadata,
                **values,
                **{
                    field: record[field]
                    for field in (
                        "id",
                        "dataset",
                        "upstream_id",
                        "title",
                        "scope",
                        "house_stage",
                        "record_sha256",
                        "geographic_review_status",
                        "source_review_status",
                    )
                },
                "snapshot_id": record["snapshot_id"],
                "reference_period": "FY2027 proposals",
                "retrieved_at": budget["manifest"]["retrieved_at"],
                "source_url": upstream.get("url"),
                "source_agency": "BetterGovPH comparison API; original issuing agencies identified in source documents",
                "source_title": record["title"],
                "source_record_id": record["upstream_id"],
                "data_format": "json",
                "currency": "PHP",
                "amount_type": "national_budget_proposal_comparison",
                "retrieved_at_scope": "collection_snapshot_timestamp_not_document_retrieval",
                "review_status": "pending",
                "missing_fields": {
                    field: "not_supplied"
                    for field, value in values.items()
                    if value is None
                },
            }
        )
        candidates.append(
            {
                **review_metadata,
                "id": record["id"],
                "title": record["title"],
                "scope": record["scope"],
                "record_sha256": record["record_sha256"],
                "original_upstream": upstream,
                "source_record_id": record["upstream_id"],
                "reference_period": "FY2027 proposals",
                "retrieved_at": budget["manifest"]["retrieved_at"],
                "retrieved_at_scope": "collection_snapshot_timestamp_not_document_retrieval",
                "snapshot_id": record["snapshot_id"],
                "geographic_match_type": record["geographic_match_type"],
                "review_status": "pending",
                "original_geographic_review_status": record["geographic_review_status"],
                "lgu_associations": [],
                "existing_lgu_associations": record["lgu_associations"],
                "evidence": {
                    "source_url": upstream.get("url"),
                    "pdf_url": upstream.get("pdf_url"),
                    "inclusion_reasons": record["inclusion_reasons"],
                },
                "warning": "Discovery evidence only; title/office matching does not establish a local allocation.",
            }
        )
        api_url = upstream.get("url")
        if api_url:
            budget_sources[("comparison_page", api_url)] = {
                "stage": "comparison_page",
                "source_url": api_url,
                "snapshot_id": record["snapshot_id"],
                "retrieved_at": budget["manifest"]["retrieved_at"],
                "reference_period": "FY2027",
                "access_review": "existing_snapshot_only",
                "redistribution_review": "pending",
                "live_verified": False,
            }
        api_path = upstream.get("api_url")
        if api_path and api_path.startswith("/api/"):
            api_source = "https://budget.bettergov.ph" + api_path
            budget_sources[("api", api_source)] = {
                "stage": "api",
                "source_url": api_source,
                "snapshot_id": record["snapshot_id"],
                "retrieved_at": budget["manifest"]["retrieved_at"],
                "reference_period": "FY2027",
                "access_review": "existing_snapshot_only",
                "redistribution_review": "pending",
                "live_verified": False,
            }
        for stage, url in (upstream.get("pdf_url") or {}).items():
            if url:
                budget_sources[(stage, url)] = {
                    "stage": stage,
                    "source_url": url,
                    "snapshot_id": record["snapshot_id"],
                    "retrieved_at": budget["manifest"]["retrieved_at"],
                    "reference_period": "FY2027",
                    "access_review": "existing_snapshot_only",
                    "redistribution_review": "pending",
                    "live_verified": False,
                }
    csv_output(
        "05_national_budget_2027/national_budget_2027_review.csv",
        review,
        list(review[0]) if review else ["id"],
    )
    json_output(
        "05_national_budget_2027/project_geographic_candidates.json",
        {
            **envelope,
            "snapshot_id": budget["manifest"]["snapshot_id"],
            "records": candidates,
            "disclaimers": budget["manifest"]["disclaimers"],
            "coverage": budget["coverage"],
        },
    )
    inventory = list(budget_sources.values())
    for source in inventory:
        source["snapshot_retrieved_at"] = source["retrieved_at"]
        source["retrieved_at"] = None
        source["retrieved_at_missing_reason"] = (
            "individual_source_retrieval_not_supplied"
        )
        source["license"] = None
    csv_output(
        "05_national_budget_2027/budget_source_inventory.csv",
        inventory,
        [
            "stage",
            "source_url",
            "snapshot_id",
            "retrieved_at",
            "snapshot_retrieved_at",
            "retrieved_at_missing_reason",
            "license",
            "reference_period",
            "access_review",
            "redistribution_review",
            "live_verified",
        ],
    )
    source_inventory = [
        {
            "source_id": sid,
            "source_url": row["url"],
            "source_agency": row.get("publisher"),
            "source_title": row.get("name"),
            "accessed_date": row.get("accessed_date"),
            "retrieved_at": None,
            "license": None,
            "redistribution_review": "pending",
            "license_status": "not_supplied",
            "review_status": "pending",
        }
        for sid, row in sources.items()
        if sid in psa + provincial
    ]
    source_inventory.extend(
        {
            "source_id": s["sha256"],
            "source_url": s["url"],
            "retrieved_at": s["retrieved_at"],
            "source_sha256": s["sha256"],
            "review_status": "pending",
            "license_status": "see_geography_manifest",
            "license": None,
            "redistribution_review": "pending",
        }
        for s in geo_manifest["sources"]
    )
    for sid in sorted(
        {sid for district in government["districts"] for sid in district["source_ids"]}
    ):
        source = government_sources[sid]
        source_inventory.append(
            {
                "source_id": "government-directory:" + sid,
                "source_url": source["url"],
                "source_agency": source["publisher"],
                "source_title": "Provincial city/municipality legislative district listing",
                "retrieved_at": source["retrieved_at"],
                "source_sha256": source["sha256"],
                "license": None,
                "license_status": "not_supplied",
                "redistribution_review": "pending",
                "review_status": "pending",
            }
        )
    source_inventory.append(
        {
            "source_id": about["source_id"],
            "source_url": about["source_url"],
            "source_agency": "Provincial Government of Pangasinan",
            "source_title": "About Pangasinan",
            "retrieved_at": about["collected_at"],
            "source_sha256": about_evidence["artifact_sha256"],
            "hash_scope": about_evidence["hash_scope"],
            "license": None,
            "license_status": "not_supplied",
            "redistribution_review": "pending",
            "review_status": "pending",
        }
    )
    csv_output(
        "source_inventory.csv",
        source_inventory,
        [
            "source_id",
            "source_url",
            "source_agency",
            "source_title",
            "accessed_date",
            "retrieved_at",
            "source_sha256",
            "hash_scope",
            "license_status",
            "license",
            "redistribution_review",
            "review_status",
        ],
    )
    gaps = [
        {"dataset": "overview", "field": field, "reason": value["missing_reason"]}
        for field, value in overview_fields.items()
        if value.get("missing_reason")
    ]
    gaps.extend(
        [
            {
                "dataset": "barangays",
                "field": "official_release",
                "reason": "unofficial_unversioned_mirror",
            },
            {"dataset": "barangays", "field": "population", "reason": "not_collected"},
            {
                "dataset": "lgus",
                "field": ",".join(missing_lgu),
                "reason": "not_collected",
            },
            {
                "dataset": "psa",
                "field": "original_utc_retrieval",
                "reason": "not_supplied",
            },
            {
                "dataset": "budget",
                "field": "geographic_associations",
                "reason": "pending_human_review",
            },
        ]
    )
    csv_output("collection_gaps.csv", gaps, ["dataset", "field", "reason"])
    csv_output(
        "collection_log.csv",
        [
            {
                "stage": stage,
                "status": "reviewed_existing_evidence",
                "network_requests": 0,
            }
            for stage in (
                "01_provincial_overview",
                "02_lgu_directory",
                "05_national_budget_2027",
            )
        ],
        ["stage", "status", "network_requests"],
    )
    json_output(
        "quality_report.json",
        {
            "coverage_status": "partial",
            "network_requests": 0,
            "counts": {
                "lgus": len(lgus),
                "barangays": len(barangays),
                "budget_records": len(review),
            },
            "warnings": warnings,
            "gaps": gaps,
            "independent_live_verification": False,
        },
    )
    manifest = {
        **review_metadata,
        "coverage_status": "partial",
        "review_status": "pending",
        "is_mock": False,
        "network_requests": 0,
        "inputs": input_hashes,
        "outputs": {name: checksum(target / name) for name in files},
    }
    write_json(target / "manifest.json", manifest)
    return manifest
