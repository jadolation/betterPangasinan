"""Normalize internal collection manifests and compile explicitly reviewed snapshots.

No command grants approval. Review decisions record explicit human authorization
and are bound to candidate hashes. An absent approved snapshot is unavailable.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
DATASETS = {"dpwh": "hgab3", "fmr": "hgab2", "hfep": "hgab2", "nia": "hgab2"}
AMOUNTS = ("nep_php", "hgab2_php", "hgab3_php", "house_php", "api_php", "delta_php")
SAFE_INTEGER = 2**53 - 1
PUBLIC_FILES = ("manifest", "projects", "offices", "coverage", "sources")


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def public_file_hash(value):
    """Hash the exact ASCII JSON bytes emitted by the static builder and CLI."""
    encoded = (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_json(path):
    def reject(value):
        raise ValueError(f"Non-finite JSON number: {value}")
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject, object_pairs_hook=unique)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def validate_schema(name, value):
    schema = read_json(ROOT / "schemas" / "national_budget" / f"{name}.schema.json")
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)


def utc_date(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Review and retrieval timestamps must be UTC with Z suffix")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Invalid UTC timestamp") from error
    if parsed > datetime.now(timezone.utc):
        raise ValueError("Timestamp cannot be in the future")


def https(value):
    parsed = urlparse(value) if isinstance(value, str) else None
    if not parsed or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Source links must be absolute HTTPS URLs")


def validate_upstream(row, dataset):
    if dataset not in DATASETS or row.get("dataset") != dataset:
        raise ValueError("Unknown or mismatched program dataset")
    if not isinstance(row.get("id"), str) or not row["id"] or not isinstance(row.get("title"), str) or not row["title"].strip():
        raise ValueError("Project needs an original ID and title")
    if row.get("is_mock") or row["id"].startswith("mock-"):
        raise ValueError("Mock records cannot enter the national budget pipeline")
    for field in AMOUNTS:
        if field not in row:
            raise ValueError(f"Missing monetary field: {field}")
        value = row[field]
        if value is not None and (type(value) is not int or abs(value) > SAFE_INTEGER or (field != "delta_php" and value < 0)):
            raise ValueError(f"Invalid integer peso value: {field}")
    if row["house_php"] != row[DATASETS[dataset] + "_php"]:
        raise ValueError("House amount does not match comparison reading")
    if row["nep_php"] is None or row["house_php"] is None:
        if row["delta_php"] is not None:
            raise ValueError("Missing-version delta must remain null")
    elif row["delta_php"] is not None and row["delta_php"] != row["house_php"] - row["nep_php"]:
        raise ValueError("Incorrect monetary difference")
    if not isinstance(row.get("flags"), list) or not all(isinstance(flag, str) for flag in row["flags"]):
        raise ValueError("Missing or malformed upstream flags")
    if row.get("bridge_group") not in ("house_only", "nep_only", "unchanged", "increased", "decreased", "scope_review"):
        raise ValueError("Unknown upstream comparison group")
    if not isinstance(row.get("pdf_url"), dict):
        raise ValueError("Missing document reference object")
    for value in row["pdf_url"].values():
        if value is not None:
            https(value)
    if row.get("url") is not None:
        https(row["url"])
    for field in ("nep_page", "hgab2_page", "hgab3_page"):
        value = row.get(field)
        if value is not None and (type(value) is not int or value < 1):
            raise ValueError("Invalid PDF page reference")
    for field, bound in (("lat", 90), ("lon", 180)):
        value = row.get(field)
        if value is not None and (type(value) not in (int, float) or not -bound <= value <= bound):
            raise ValueError("Invalid supplied coordinate")


def record_hash(record):
    return digest({key: value for key, value in record.items() if key != "record_sha256"})


def normalize(manifest):
    """Retain all query provenance; never infer an LGU or approve a record."""
    validate_schema("batch", manifest)
    utc_date(manifest["retrieved_at"])
    overview = manifest["overview"]
    meta = overview["meta"]
    if meta.get("fiscal_year") != 2027 or meta.get("currency") != "PHP" or meta.get("scale") != "pesos":
        raise ValueError("Unsupported fiscal year, currency or scale")
    snapshot = {key: meta[key] for key in ("source_commit", "built_at")}
    if not meta.get("notice") or not overview.get("disclaimers"):
        raise ValueError("Missing upstream notice/disclaimers")
    snapshot_id = "2027:" + snapshot["source_commit"] + ":" + snapshot["built_at"]
    records, conflicts = {}, []
    errors = [f"Collection: {error}" for error in manifest.get("errors", [])]
    errors.extend(f"Query {index}: {query['error']}" for index, query in enumerate(manifest["queries"]) if query.get("error"))
    all_queries_complete = bool(manifest["queries"]) and all(query["complete"] for query in manifest["queries"])
    if manifest["complete"] and (not all_queries_complete or errors or manifest.get("run_complete") is False):
        errors.append("Inconsistent collection completeness flag")
    for query_index, query in enumerate(manifest["queries"]):
        dataset = query.get("dataset")
        if dataset not in DATASETS:
            continue
        query_meta = query.get("meta") or {}
        if any(query_meta.get(key) != value for key, value in snapshot.items()):
            errors.append(f"Snapshot metadata missing or changed in query {query_index}")
        if query_meta.get("house_stage") != DATASETS[dataset]:
            errors.append(f"Invalid comparison stage in query {query_index}")
        for row in query.get("rows", []):
            try:
                validate_upstream(row, dataset)
            except ValueError as error:
                errors.append(f"{dataset}:{row.get('id')}: {error}")
                continue
            identifier = dataset + ":" + row["id"]
            reason = {
                "query_index": query_index, "category": query["category"],
                "params": query.get("params", {}), "response_ids": query.get("response_ids", []),
            }
            if identifier in records:
                if records[identifier]["upstream"] != row:
                    conflicts.append({"id": identifier, "query_index": query_index, "upstream": row})
                records[identifier]["inclusion_reasons"].append(reason)
                continue
            title_explicit = bool(re.search(r"\bpangasinan\b", row["title"], re.I))
            # Central/region-wide and multi-region lines need human scope review.
            shared = "central" in (row.get("office_kind") or "").lower() or "regional" in (row.get("office_kind") or "").lower() or ";" in row["title"]
            match_type = "province_title_explicit" if title_explicit else "ambiguous_or_region_missing"
            if query["category"] == "office" and not title_explicit:
                match_type = "office_scope_only"
            record = {
                "id": identifier, "upstream_id": row["id"], "dataset": dataset,
                "fiscal_year": 2027, "snapshot_id": snapshot_id, "title": row["title"],
                "house_stage": DATASETS[dataset], "upstream": deepcopy(row),
                "scope": "shared" if shared else "uncertain",
                "geographic_match_type": match_type, "lgu_associations": [],
                "inclusion_reasons": [reason], "geographic_review_status": "pending",
                "source_review_status": "pending", "publication_status": "candidate",
            }
            records[identifier] = record
    for record in records.values():
        details = [entry for entry in manifest.get("details", []) if entry["dataset"] == record["dataset"] and entry["id"] == record["upstream_id"]]
        if details:
            for detail in details:
                envelope = detail.get("envelope", {})
                detail_meta = envelope.get("meta", {})
                if any(detail_meta.get(key) != value for key, value in snapshot.items()) or any(envelope.get("data", {}).get(key) != value for key, value in record["upstream"].items()) or not envelope.get("disclaimers"):
                    errors.append(f"Detail evidence conflicts with listing/snapshot: {record['id']}")
            record["detail_evidence"] = details
        record["record_sha256"] = record_hash(record)
        validate_schema("project", record)
    coverage = {
        "snapshot_id": snapshot_id, "exhaustive_geographic_coverage": False,
        "queries": [{key: value for key, value in query.items() if key not in ("rows", "meta", "disclaimers")} for query in manifest["queries"]],
        "unique_records": len(records), "requiring_geographic_review": len(records),
        "approved_records": 0, "excluded_records": 0,
        "project_detail_records": sum(bool(record.get("detail_evidence")) for record in records.values()),
        "all_project_details_collected": all(record.get("detail_evidence") for record in records.values()) if records else False,
        "errors": errors, "conflicts": conflicts,
        "complete": bool(manifest.get("complete")) and all_queries_complete and not errors and not conflicts,
        "limitations": [
            "Query matches do not establish physical location or exhaustive coverage.",
            "Office and multi-LGU views overlap and must not be added together.",
            "Shared umbrella amounts are not wholly attributable to Pangasinan.",
            "NIA records may lack region; zero name matches do not establish absence of funding.",
        ],
    }
    candidates = {
        "snapshot_id": snapshot_id, "retrieved_at": manifest["retrieved_at"],
        "projects": sorted(records.values(), key=lambda record: record["id"]),
        "offices": manifest.get("offices", []), "coverage": coverage,
        "sources": {"overview": overview, "requests": manifest.get("requests", [])},
    }
    candidates["sources"]["query_notices"] = [
        {"query_index": index, "notice": (query.get("meta") or {}).get("notice"), "disclaimers": query.get("disclaimers", [])}
        for index, query in enumerate(manifest["queries"])
    ]
    candidates["candidate_sha256"] = digest(candidates)
    return candidates


def stage_totals(records):
    """Version sums include known rows only, explicitly reporting missing values."""
    result = {}
    for stage in ("hgab2", "hgab3"):
        rows = [row for row in records if row["house_stage"] == stage]
        if not rows:
            continue
        totals = {"records": len(rows)}
        for field in ("nep_php", "house_php"):
            values = [row["upstream"][field] for row in rows]
            known = [value for value in values if value is not None]
            total = sum(known) if known else None
            if total is not None and abs(total) > SAFE_INTEGER:
                raise ValueError("Summary exceeds safe integer transport range")
            totals[field] = total
            totals[field + "_known_rows"] = len(known)
            totals[field + "_missing_rows"] = len(values) - len(known)
        paired = [row for row in rows if row["upstream"]["nep_php"] is not None and row["upstream"]["house_php"] is not None and row["upstream"].get("bridge_group") != "scope_review" and not row["upstream"].get("held")]
        totals["comparable_rows"] = len(paired)
        totals["comparable_delta_php"] = sum(row["upstream"]["house_php"] - row["upstream"]["nep_php"] for row in paired) if paired else None
        if totals["comparable_delta_php"] is not None and abs(totals["comparable_delta_php"]) > SAFE_INTEGER:
            raise ValueError("Summary exceeds safe integer transport range")
        result[stage] = totals
    return result


def review_stamp(value):
    if not isinstance(value.get("reviewer"), str) or not value["reviewer"].strip():
        raise ValueError("Explicit human reviewer identity required")
    utc_date(value.get("reviewed_at"))


def compile_snapshot(candidates, decisions):
    """Require immutable, explicit review decisions; this function cannot approve."""
    validate_schema("review", decisions)
    review_stamp(decisions)
    if candidates.get("candidate_sha256") != digest({key: value for key, value in candidates.items() if key != "candidate_sha256"}):
        raise ValueError("Candidate checksum changed")
    if decisions["candidate_sha256"] != candidates["candidate_sha256"] or decisions["snapshot_id"] != candidates["snapshot_id"]:
        raise ValueError("Stale snapshot approval")
    utc_date(candidates["retrieved_at"])
    if datetime.fromisoformat(decisions["reviewed_at"].replace("Z", "+00:00")) < datetime.fromisoformat(candidates["retrieved_at"].replace("Z", "+00:00")):
        raise ValueError("Approval cannot predate collection")
    coverage = candidates["coverage"]
    if coverage["errors"] or coverage["conflicts"]:
        raise ValueError("Cannot publish unresolved collection conflicts/errors")
    if not coverage["complete"] and not decisions["allow_incomplete_coverage"]:
        raise ValueError("Incomplete coverage needs explicit approval")
    if not candidates["sources"]["overview"].get("meta", {}).get("notice") or not candidates["sources"]["overview"].get("disclaimers"):
        raise ValueError("Missing original source notices")
    indexed = {record["id"]: record for record in candidates["projects"]}
    if len(indexed) != len(candidates["projects"]):
        raise ValueError("Duplicate candidate IDs")
    authorization = decisions.get("authorization")
    if authorization:
        utc_date(authorization["authorized_at"])
        if datetime.fromisoformat(authorization["authorized_at"].replace("Z", "+00:00")) > datetime.fromisoformat(decisions["reviewed_at"].replace("Z", "+00:00")):
            raise ValueError("Recorded approval cannot predate user authorization")
        values_hash = digest({record["id"]: digest(record["upstream"]) for record in candidates["projects"]})
        if authorization["source_values_sha256"] != values_hash:
            raise ValueError("Source values changed since publication authorization")
    registry = {}
    for entry in decisions["lgu_registry"]:
        review_stamp(entry)
        https(entry["source_url"])
        if urlparse(entry["source_url"]).hostname not in ("psa.gov.ph", "www.psa.gov.ph"):
            raise ValueError("Reviewed LGU registry requires a PSA source")
        if entry["psgc"] in registry:
            raise ValueError("Duplicate registry PSGC")
        registry[entry["psgc"]] = entry
    published, excluded, seen = [], [], set()
    for decision in decisions["projects"]:
        if decision["id"] in seen or decision["id"] not in indexed:
            raise ValueError("Duplicate or unknown review decision")
        seen.add(decision["id"])
        record = indexed[decision["id"]]
        validate_schema("project", record)
        validate_upstream(record["upstream"], record["dataset"])
        if record["record_sha256"] != record_hash(record) or decision["record_sha256"] != record["record_sha256"]:
            raise ValueError("Stale record approval")
        if record["snapshot_id"] != candidates["snapshot_id"] or record["publication_status"] != "candidate":
            raise ValueError("Invalid candidate snapshot/status")
        if record["id"] != record["dataset"] + ":" + record["upstream_id"] or record["upstream_id"] != record["upstream"]["id"] or record["title"] != record["upstream"]["title"] or record["house_stage"] != DATASETS[record["dataset"]]:
            raise ValueError("Candidate identity, title or stage changed")
        review_stamp(decision)
        if decision["decision"] == "exclude":
            if not decision.get("exclusion_reason", "").strip():
                raise ValueError("Exclusion requires a reason")
            excluded.append({"id": record["id"], "reason": decision["exclusion_reason"]})
            continue
        if authorization and (decision["scope"] == "geographic" or decision["geographic_review_status"] != "pending" or decision["lgu_associations"] or decision["source_review_status"] != "reviewed_with_warnings"):
            raise ValueError("Publication-only authorization cannot verify geography or clear source warnings")
        if not record.get("detail_evidence"):
            raise ValueError("Publication requires collected project-detail evidence")
        evidence = decision["evidence_source_ids"]
        if not evidence:
            raise ValueError("Publication requires reviewed evidence references")
        documents = candidates["sources"]["overview"]["data"].get("documents", [])
        document_ids = {document["key"] for document in documents}
        if not set(evidence) <= document_ids:
            raise ValueError("Unknown evidence document")
        if (record["upstream"]["flags"] or record["upstream"].get("held")) and decision["source_review_status"] != "reviewed_with_warnings":
            raise ValueError("Upstream review flags must remain warnings")
        for version in ("nep", record["house_stage"]):
            if record["upstream"][version + "_php"] is not None:
                if not record["upstream"]["pdf_url"].get(version):
                    raise ValueError("Known amount needs a source PDF link")
                if record["upstream"].get(version + "_doc") not in evidence:
                    raise ValueError("Known amount needs its reviewed source document")
        associations = decision["lgu_associations"]
        for association in associations:
            review_stamp(association)
            if association["review_status"] != "reviewed" or not association["evidence_source_ids"] or not set(association["evidence_source_ids"]) <= document_ids:
                raise ValueError("LGU association requires reviewed evidence")
            if association["psgc"] not in registry or association["name"] != registry[association["psgc"]]["name"]:
                raise ValueError("LGU association requires reviewed registry membership")
        if len({association["psgc"] for association in associations}) != len(associations):
            raise ValueError("Duplicate LGU association")
        if decision["scope"] == "geographic" and decision["geographic_review_status"] != "reviewed":
            raise ValueError("Geographic scope requires independent review")
        if record["scope"] == "shared" and decision["scope"] == "geographic":
            raise ValueError("Shared allocations cannot be counted as wholly geographic funding")
        if associations and decision["geographic_review_status"] != "reviewed":
            raise ValueError("Cannot publish unreviewed LGU associations")
        public = deepcopy(record)
        public.update({key: decision[key] for key in ("scope", "geographic_review_status", "source_review_status", "lgu_associations")})
        public["publication_status"] = "approved"
        public["review"] = {key: decision[key] for key in ("reviewer", "reviewed_at", "evidence_source_ids")}
        published.append(public)
    office_index = {office["id"]: office for office in candidates["offices"]}
    if len(office_index) != len(candidates["offices"]):
        raise ValueError("Duplicate candidate office IDs")
    offices, office_seen = [], set()
    for decision in decisions["offices"]:
        review_stamp(decision)
        identifier = decision["id"]
        if identifier not in office_index or identifier in office_seen or decision["sha256"] != digest(office_index[identifier]):
            raise ValueError("Unknown, duplicate or stale office approval")
        office_seen.add(identifier)
        office = deepcopy(office_index[identifier])
        validate_schema("office", office)
        office["review"] = deepcopy(decision)
        offices.append(office)
    if not published:
        raise ValueError("Approved snapshots must contain explicitly approved records")
    public_coverage = deepcopy(coverage)
    public_coverage.update({"approved_records": len(published), "excluded_records": len(excluded), "exclusions": excluded,
                            "requiring_geographic_review": sum(record["id"] not in seen for record in candidates["projects"]) + sum(record["geographic_review_status"] == "pending" for record in published),
                            "stage_totals_by_scope": {scope: stage_totals([record for record in published if record["scope"] == scope]) for scope in ("geographic", "office", "shared", "uncertain")}})
    # Raw request logs and internal query paths are never part of the public source file.
    sources = {"overview": deepcopy(candidates["sources"]["overview"]),
               "query_notices": deepcopy(candidates["sources"].get("query_notices", [])),
               "lgu_registry": deepcopy(decisions["lgu_registry"])}
    disclaimers = {item["id"]: item for item in sources["overview"]["disclaimers"]}
    for query in sources["query_notices"]:
        for item in query["disclaimers"]:
            if item["id"] in disclaimers and disclaimers[item["id"]] != item:
                raise ValueError("Conflicting disclaimer text")
            disclaimers[item["id"]] = item
    manifest = {"status": "approved", "fiscal_year": 2027, "snapshot_id": candidates["snapshot_id"],
                "retrieved_at": candidates["retrieved_at"], "notice": sources["overview"]["meta"]["notice"],
                "disclaimers": list(disclaimers.values()), "candidate_sha256": candidates["candidate_sha256"],
                "review": {key: decisions[key] for key in ("reviewer", "reviewed_at", "allow_incomplete_coverage")}}
    payload = {"manifest": manifest, "projects": published, "offices": offices, "coverage": public_coverage, "sources": sources}
    if authorization:
        manifest["review"]["authorization"] = deepcopy(authorization)
    manifest["files"] = {name + ".json": public_file_hash(value) for name, value in payload.items() if name != "manifest"}
    validate_schema("manifest", manifest)
    utc_date(manifest["retrieved_at"])
    return payload


def publication_payload(root=ROOT):
    """Validate approved inputs afresh on every build; no candidate fallback."""
    approved = Path(root) / "data" / "national_budget" / "approved"
    candidate = approved / "candidates.json"
    decisions = approved / "decisions.json"
    if not candidate.exists() and not decisions.exists():
        return {
            "manifest": {"status": "unavailable", "fiscal_year": 2027, "snapshot_id": None, "retrieved_at": None,
                         "notice": "No human-approved national budget snapshot is available yet.", "disclaimers": []},
            "projects": [], "offices": [],
            "coverage": {"complete": False, "exhaustive_geographic_coverage": False, "approved_records": 0,
                         "limitations": ["No approved snapshot; unavailable is not zero funding."]}, "sources": {},
        }
    if not candidate.is_file() or not decisions.is_file() or candidate.is_symlink() or decisions.is_symlink():
        raise ValueError("Approved publication inputs are missing or symlinked")
    return compile_snapshot(read_json(candidate), read_json(decisions))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    normal = sub.add_parser("normalize")
    normal.add_argument("manifest", type=Path)
    normal.add_argument("--output", type=Path, required=True)
    compile_command = sub.add_parser("compile")
    compile_command.add_argument("candidates", type=Path)
    compile_command.add_argument("decisions", type=Path)
    compile_command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "normalize":
        candidates = normalize(read_json(args.manifest))
        write_json(args.output / "candidates.json", candidates)
        write_json(args.output / "review-report.json", {
            "candidate_sha256": candidates["candidate_sha256"], "coverage": candidates["coverage"],
            "stage_totals_unreviewed_by_scope": {scope: stage_totals([record for record in candidates["projects"] if record["scope"] == scope]) for scope in ("shared", "uncertain")},
            "offices_for_review": [{"id": office["id"], "sha256": digest(office)} for office in candidates["offices"]],
            "records_for_review": [{
                "id": record["id"], "title": record["title"], "record_sha256": record["record_sha256"],
                "scope_provisional": record["scope"], "geographic_match_type": record["geographic_match_type"],
                "query_categories": sorted({reason["category"] for reason in record["inclusion_reasons"]}),
                "house_stage": record["house_stage"], "comparison_group": record["upstream"].get("bridge_group"),
                "flags": record["upstream"]["flags"], "held": record["upstream"].get("held"),
                "detail_collected": bool(record.get("detail_evidence")),
                "source_url": record["upstream"].get("url"), "pdf_url": record["upstream"]["pdf_url"],
                "geographic_review_status": "pending", "source_review_status": "pending",
                "publication_status": "candidate",
            } for record in candidates["projects"]],
            "warning": "INTERNAL CANDIDATES ONLY. Not approved funding attributable to Pangasinan.",
        })
        print(f"Normalized {len(candidates['projects'])} candidates; approved: 0")
    else:
        payload = compile_snapshot(read_json(args.candidates), read_json(args.decisions))
        for name in PUBLIC_FILES:
            write_json(args.output / (name + ".json"), payload[name])


if __name__ == "__main__":
    main()
