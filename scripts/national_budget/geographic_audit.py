"""Recompute a source-coordinate review, never a correction or LGU attribution.

Only explicitly named latitude/longitude fields determine coordinate order. FMR
GeoJSON and OCR text are retained as evidence, not used to guess missing values.
Simplified boundaries have a 200 m review tolerance (UTM 51N); this is not a
survey-precision verification. No land dataset is available to infer offshore.
"""

from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

from pyproj import Geod, Transformer
from shapely import transform
from shapely.geometry import Point, shape
from shapely.ops import unary_union

from .pipeline import public_file_hash

GEOJSON_PATH = "data/project-locations/projects.geojson"
SUMMARY_PATH = "data/project-locations/review-summary.json"
GEOD = Geod(ellps="WGS84")
PROJECT = Transformer.from_crs(4326, 32651, always_xy=True).transform


def _project(coordinates):
    return list(zip(*PROJECT(*zip(*coordinates))))


def _pair(latitude, longitude):
    # Numeric strings are evidence, not published numeric coordinates.
    if (type(latitude) not in (int, float) or type(longitude) not in (int, float)
            or not -90 <= latitude <= 90 or not -180 <= longitude <= 180
            or not math.isfinite(latitude) or not math.isfinite(longitude)):
        return None
    return [longitude, latitude]


def _safe(value):
    """Keep non-JSON synthetic numeric evidence explicit without emitting NaN."""
    if isinstance(value, float) and not math.isfinite(value):
        return {"non_finite_number": repr(value)}
    if isinstance(value, dict):
        return {key: _safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe(item) for item in value]
    return deepcopy(value)


def publication_payload(root, projects, manifest):
    """Return two derived public objects; do not read stale derived outputs.

    projects is the current public list, serialized by pipeline.public_file_hash
    exactly as the builder emits it. Boundaries are hashed as actual file bytes.
    """
    projects_hash = public_file_hash(projects)  # Reject NaN/Infinity: no public JSON bytes exist.
    ids = [project["id"] for project in projects]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate project IDs in public snapshot")
    manifest_available = manifest.get("status") != "unavailable"
    if manifest_available and any(project.get("snapshot_id") != manifest.get("snapshot_id") for project in projects):
        raise ValueError("Project source snapshot differs from manifest")
    boundary_bytes = None
    if manifest_available:
        try:
            boundary_bytes = (Path(root) / "data/geography/municipalities.geojson").read_bytes()
        except FileNotFoundError:
            pass
    boundaries = json.loads(boundary_bytes) if boundary_bytes is not None else {"features": []}
    geometries = {}
    registry = []
    for feature in boundaries["features"]:
        geometry = shape(feature["geometry"])
        if geometry.geom_type not in ("Polygon", "MultiPolygon") or geometry.is_empty or not geometry.is_valid:
            raise ValueError("Invalid municipality boundary geometry")
        item = feature["properties"]
        geometries.setdefault(item["psgc"], []).append(geometry)
        if not any(row["psgc"] == item["psgc"] for row in registry):
            registry.append(item)
    if boundary_bytes is not None and not geometries:
        raise ValueError("Empty municipality boundary collection")
    geometries = {psgc: unary_union(items) for psgc, items in geometries.items()}
    province = unary_union(list(geometries.values())) if geometries else None
    projected = transform(province, _project) if province is not None else None
    projected_municipalities = {psgc: transform(geometry, _project) for psgc, geometry in geometries.items()}
    audit_available = province is not None
    unavailable_reason = (None if audit_available else "source_manifest_unavailable" if not manifest_available
                          else "municipality_boundaries_unavailable")
    features, reviews = [], []

    def coverage(pair, geometry, projected_geometry):
        if geometry.covers(Point(pair)):
            return "covered"
        # Avoid projecting remote/global points into an inappropriate UTM zone.
        west, south, east, north = geometry.bounds
        if west - .02 <= pair[0] <= east + .02 and south - .02 <= pair[1] <= north + .02:
            if projected_geometry.distance(transform(Point(pair), _project)) <= 200:
                return "within_tolerance"
        return "excluded"

    def position(pair):
        if not audit_available:
            return "boundary_audit_unavailable"
        return {"covered": "inside_province", "within_tolerance": "near_province_boundary",
                "excluded": "outside_province"}[coverage(pair, province, projected)]

    for project in projects:
        upstream = project.get("upstream") or {}
        title = project.get("title", "")
        claim_titles = [title]
        barangays = []
        structured_province = False
        if project.get("dataset") == "fmr":
            for detail in project.get("detail_evidence", []):
                record = detail.get("envelope", {}).get("data", {}).get("record") or {}
                for version in ("nep", "house"):
                    source = record.get(version)
                    if isinstance(source, dict):
                        if isinstance(source.get("title"), str):
                            claim_titles.append(source["title"])
                        structured_province |= source.get("province") == "Pangasinan"
                        for field in ("barangay", "barangays"):
                            values = source.get(field)
                            for value in values if isinstance(values, list) else [values]:
                                if isinstance(value, str) and value.strip() and not any(item["name"] == value for item in barangays):
                                    barangays.append({"name": value, "raw": value,
                                        "source_path": f"detail_evidence.envelope.data.record.{version}.{field}"})
        claim_text = "\n".join(claim_titles)
        # Only isolated comma-delimited mentions; do not guess route fragments,
        # official PSGCs, or a parent municipality from a barangay name.
        for source_title in claim_titles:
            for match in re.finditer(r"(?:^|,)\s*((?:Brgy\.?|Barangay)\s+([^,;\n]+))(?=,|$)", source_title, re.I):
                name = match[2].strip()
                if (not re.search(r"\b(?:FMR|road|to|and|phase|construction)\b|[+/]", name, re.I)
                        and not any(item["name"].casefold() == name.casefold() for item in barangays)):
                    barangays.append({"name": name, "raw": match[1], "source_path": "project_or_source_title"})
        # A named barangay in a foreign municipality is positive evidence;
        # office or source region alone is deliberately not such evidence.
        elsewhere = bool(re.search(r"\bNew\s+Pangasinan\b.*(?:\bKoronadal\b.*\bSouth\s+Cotabato\b|\bIsulan\b.*\bSultan\s+Kudarat\b)", claim_text, re.I))
        province_claim = (structured_province or bool(re.search(r",\s*(?:Province\s+of\s+)?Pangasinan\b|\bProvince\s+of\s+Pangasinan\b", claim_text, re.I))) and not elsewhere
        municipalities = []
        if province_claim:
            for item in registry:
                name = item["name"]
                aliases = {name, re.sub(r"^City of | City$", "", name)}
                if any(re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", claim_text, re.I) for alias in aliases):
                    municipalities.append({"psgc": item["psgc"], "name": name})
        row = {key: deepcopy(project.get(key)) for key in (
            "id", "upstream_id", "title", "dataset", "fiscal_year", "house_stage",
            "geographic_review_status", "record_sha256")}
        row.update(nep_php=upstream.get("nep_php"), house_php=upstream.get("house_php"),
                   comparison_status=upstream.get("bridge_group"),
                   stated_province="Pangasinan" if province_claim else None,
                   stated_municipalities=municipalities, stated_barangays=barangays,
                   location_flags=["name_match_elsewhere"] if elsewhere else [], segments=[],
                   source_fields=_safe({"upstream": upstream, "lgu_associations": project.get("lgu_associations", []),
                                        "geographic_match_type": project.get("geographic_match_type")}),
                   source_links=deepcopy(upstream.get("pdf_url", {})),
                   source_snapshot=project.get("snapshot_id"),
                   coordinate_basis="fmr_source_endpoints" if project.get("dataset") == "fmr" else "api_published_point",
                   boundary_audit_status="available" if audit_available else "unavailable")
        project_feature_start = len(features)
        candidates = []
        if project.get("dataset") == "fmr":
            for detail_index, detail in enumerate(project.get("detail_evidence", [])):
                record = detail.get("envelope", {}).get("data", {}).get("record") or {}
                for version in ("nep", "house"):
                    source = record.get(version)
                    if not isinstance(source, dict):
                        continue
                    segments = source.get("segments") or []
                    for segment in segments:
                        candidates.append((version, segment, {"source_path": f"detail_evidence[{detail_index}].envelope.data.record.{version}",
                            "response_id": detail.get("response_id"), "segment": _safe(segment),
                            "source_record": _safe(source)}))
                    # Preserve named points even when no segment could be paired.
                    paired_ids = {pid for segment in segments for pid in segment.get("point_ids", [])}
                    for point in source.get("points", []):
                        if point.get("id") not in paired_ids and not any(
                            point.get("latitude") == segment.get(role + "_latitude") and
                            point.get("longitude") == segment.get(role + "_longitude")
                            for segment in segments for role in ("start", "end")):
                            candidates.append((version, {"start_latitude": point.get("latitude"),
                                "start_longitude": point.get("longitude"), "standalone": True,
                                "role": point.get("role", "point")}, {"source_path": f"detail_evidence[{detail_index}].envelope.data.record.{version}.points",
                                "point": _safe(point), "source_record": _safe(source)}))
        else:
            if upstream.get("lat") is not None or upstream.get("lon") is not None:
                candidates.append(("api", {"start_latitude": upstream.get("lat"),
                    "start_longitude": upstream.get("lon"), "standalone": True,
                    "role": "api_published_point"}, {"source_path": "upstream", "lat": _safe(upstream.get("lat")), "lon": _safe(upstream.get("lon"))}))
        seen, point_counts = {}, Counter()
        for version, segment, evidence in candidates:
            start_raw = {"latitude": _safe(segment.get("start_latitude")), "longitude": _safe(segment.get("start_longitude"))}
            end_raw = {"latitude": _safe(segment.get("end_latitude")), "longitude": _safe(segment.get("end_longitude"))}
            start = _pair(segment.get("start_latitude"), segment.get("start_longitude"))
            end = _pair(segment.get("end_latitude"), segment.get("end_longitude"))
            standalone = segment.get("standalone", False)
            key = json.dumps([start_raw, end_raw, standalone, segment.get("role")], sort_keys=True)
            if key in seen:
                prior = seen[key]
                if version not in prior["source_versions"]:
                    prior["source_versions"].append(version)
                prior["evidence"].append(evidence)
                if "duplicate_segment" not in prior["flags"]:
                    prior["flags"].append("duplicate_segment")
                continue
            flags = []
            if start is None or (end is None and not standalone):
                flags.append("invalid_or_missing_coordinate_pair")
            distance = None
            if start is not None and end is not None:
                distance = 0.0 if start == end else GEOD.inv(*start, *end)[2] / 1000
                if start == end:
                    flags.append("identical_endpoints")
                if distance > 200:
                    flags.append("endpoint_distance_over_200km_review")
            entry = {"index": len(row["segments"]), "source_versions": [version], "start": start,
                     "end": end, "start_raw": start_raw, "end_raw": end_raw,
                     "distance_km": distance, "flags": flags, "evidence": [evidence]}
            seen[key] = entry
            row["segments"].append(entry)
            for endpoint, pair in (("point" if standalone else "start", start), ("end", end)):
                if pair is None:
                    continue
                status = position(pair)
                entry["start_status" if endpoint in ("start", "point") else "end_status"] = status
                if status != "inside_province" and status not in flags:
                    flags.append(status)
                if status == "outside_province" and province_claim:
                    flags.append("stated_province_coordinate_mismatch")
                if municipalities and audit_available:
                    municipality_results = {item["psgc"]: coverage(pair, geometries[item["psgc"]],
                        projected_municipalities[item["psgc"]]) for item in municipalities}
                    entry.setdefault("municipality_checks", {})[endpoint] = municipality_results
                    if all(value == "excluded" for value in municipality_results.values()):
                        if "municipality_mismatch" not in flags:
                            flags.append("municipality_mismatch")
                    elif "within_tolerance" in municipality_results.values() and "covered" not in municipality_results.values():
                        if "near_municipality_boundary" not in flags:
                            flags.append("near_municipality_boundary")
                point_counts[tuple(pair)] += 1
                features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": pair},
                    "properties": {"project_id": project["id"], "segment_index": entry["index"],
                        "endpoint": endpoint, "status": status, "role": segment.get("role", endpoint)}})
            if start is not None and end is not None:
                features.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [start, end]},
                    "properties": {"project_id": project["id"], "segment_index": entry["index"],
                        "endpoint": None, "status": "source_segment", "role": "road_endpoints"}})
        for segment in row["segments"]:
            if any(pair is not None and point_counts[tuple(pair)] > 1 for pair in (segment["start"], segment["end"])):
                segment["flags"].append("repeated_point")
        flags = sorted({flag for segment in row["segments"] for flag in segment["flags"]})
        row["location_flags"] = sorted(set(row["location_flags"] + flags))
        has_points = any(s["start"] is not None or s["end"] is not None for s in row["segments"])
        row["display_status"] = (
            "needs_review" if has_points and not audit_available else
            "unavailable" if not audit_available else
            "name_match_elsewhere" if elsewhere else
            "unavailable" if not has_points else
            "suspicious" if any(flag in flags for flag in (
                "stated_province_coordinate_mismatch", "municipality_mismatch", "endpoint_distance_over_200km_review")) else
            "outside_pangasinan" if "outside_province" in flags else
            "needs_review" if not province_claim or any(flag in flags for flag in (
                "invalid_or_missing_coordinate_pair", "identical_endpoints", "repeated_point",
                "near_province_boundary", "near_municipality_boundary")) else "plausible")
        for feature in features[project_feature_start:]:
            feature["properties"]["geographic_position"] = feature["properties"]["status"]
            feature["properties"]["status"] = row["display_status"]
        reviews.append(row)
    summary = {"schema_version": 1, "snapshot_id": manifest.get("snapshot_id"),
        "status": "available" if audit_available else "unavailable", "unavailable_reason": unavailable_reason,
        "source_hashes": {"projects": projects_hash, "municipalities": hashlib.sha256(boundary_bytes).hexdigest() if boundary_bytes is not None else None},
        "policy": {"coordinate_order": "Named longitude,latitude only; no geographic ordering inference",
            "boundary_tolerance_m": 200, "boundary_distance_crs": "EPSG:32651",
            "endpoint_distance": "pyproj.Geod WGS84 ellipsoid", "endpoint_anomaly_km": 200,
            "anomaly_meaning": "REVIEW heuristic, not proof of error or wrongdoing",
            "attribution": "Title matches are source claims only; original LGU association and pending review unchanged",
            "province_claim": "Explicit comma-delimited Pangasinan suffix, Province of Pangasinan, or FMR province field; bare province query matches are inclusion only",
            "municipality_matching": "Exact token registry names and City of / City aliases, with explicit province context; not confirmed attribution",
            "municipality_check": "Each valid endpoint must be covered by at least one stated municipality Polygon/MultiPolygon or within 200 m in UTM51N; holes are excluded",
            "plausible": "Automated consistency with explicit project geography only, not independent survey/site verification",
            "unavailable_boundaries": "Whole boundary audit unavailable; valid source points and lines remain unchanged with needs_review status; no fabricated boundary hash",
            "display_statuses": ["plausible", "suspicious", "outside_pangasinan", "name_match_elsewhere", "unavailable", "needs_review"],
            "namesakes": "New Pangasinan with Koronadal/South Cotabato or Isulan/Sultan Kudarat in project/source title; source region and office are not physical-location evidence",
            "nonfinite_numbers": "Numeric validator rejects nonfinite pairs; publication rejects non-JSON source snapshots rather than inventing an emitted-byte hash",
            "api_points": "API-published point, not precise verification", "offshore": "Not assessed: no reliable land source",
            "default_dataset": "fmr"},
        "counts": {"projects": len(reviews), "by_program": dict(Counter(r["dataset"] for r in reviews)),
            "by_status": dict(Counter(r["display_status"] for r in reviews)),
            "by_program_status": {program: dict(Counter(r["display_status"] for r in reviews if r["dataset"] == program))
                                  for program in sorted({r["dataset"] for r in reviews})}}, "projects": reviews}
    collection = {"type": "FeatureCollection", "snapshot_id": summary["snapshot_id"], "status": summary["status"],
                  "unavailable_reason": unavailable_reason,
                  "source_hashes": deepcopy(summary["source_hashes"]), "features": features}
    summary["files"] = {"projects.geojson": public_file_hash(collection)}
    return {GEOJSON_PATH: collection, SUMMARY_PATH: summary}


def validate_publication_payload(root, projects, manifest, payload):
    """Reject stale, altered, partial, or differently bound derived artifacts."""
    if payload != publication_payload(root, projects, manifest):
        raise ValueError("Stale or altered project-location publication payload")
    return True
