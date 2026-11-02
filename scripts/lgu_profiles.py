"""Small derived profile bundles. Never infer location from an office or a title."""

import re


def aliases(record):
    values = {record["name"].strip().casefold()}
    if record.get("classification") == "city":
        base = re.sub(r"^city of\s+|\s+city$", "", record["name"].strip(), flags=re.I)
        values.update({base.casefold(), (base + " City").casefold(), ("City of " + base).casefold()})
    return values


def named(record, names, fields):
    return any(isinstance(record.get(field), str) and record[field].strip().casefold() in names for field in fields)


def linked(record, lgu):
    code = lgu.get("psgc")
    return record.get("lgu_id") == lgu["id"] or bool(code and (record.get("lgu_psgc") == code or record.get("psgc") == code))


def unique(records):
    result, seen = [], set()
    for row in records:
        key = row.get("id") or (row.get("source_id"), row.get("lgu"), row.get("geography"), row.get("indicator"), row.get("reference_period"), row.get("year"), row.get("budget_type"), row.get("institution"), row.get("office"), row.get("name"), row.get("location"))
        if key not in seen:
            seen.add(key); result.append(row)
    return result


def discovery(records, names, title):
    # Whole-name matching is a discovery aid only, including possible namesakes.
    terms = [re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", re.I) for name in names]
    return [row for row in records if isinstance(title(row), str) and any(term.search(title(row)) for term in terms)]


def publication_payloads(data, supplemental, national_budget):
    reference = supplemental.get("data/provincial-reference.json", {})
    barangays = supplemental.get("data/geography/barangays.json", [])
    geo = supplemental.get("data/geography/manifest.json", {})
    historical = supplemental.get("data/historical-budget/programs.json", {}).get("data", [])
    profiles = {}
    registry = data["lgus"]
    alias_owners = {}
    for lgu in registry:
        for name in aliases(lgu):
            alias_owners.setdefault(name, set()).add(lgu["id"])
    for lgu in registry:
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", lgu["id"]):
            raise ValueError("Unsafe LGU profile filename")
        names = {name for name in aliases(lgu) if len(alias_owners[name]) == 1}
        can_join_reference = bool(lgu.get("psgc") and not lgu.get("is_mock"))
        local_barangays = [row for row in barangays if row.get("parent_psgc") == lgu.get("psgc")] if can_join_reference else []
        local_statistics = [row for row in reference.get("statistics", []) if named(row, names, ("geography", "lgu"))] if can_join_reference else []
        local_budgets = [row for row in reference.get("budget_observations", []) if named(row, names, ("lgu",))] if can_join_reference else []
        local_projects = [row for row in reference.get("project_leads", []) if linked(row, lgu) or named(row, names, ("lgu",))] if can_join_reference else []
        local_government = [row for row in reference.get("government_offices", []) if linked(row, lgu) or named(row, names, ("lgu", "municipality"))] if can_join_reference else []
        local_hospitals = [row for row in reference.get("hospital_contacts", []) if linked(row, lgu) or named(row, names, ("lgu", "municipality", "location"))] if can_join_reference else []
        if can_join_reference:
            for page in reference.get("official_pages", []):
                if page.get("id") != "directory":
                    continue
                for row in page.get("rows", []):
                    # Only an explicit comma-separated locality in the source,
                    # not a town word embedded in a facility's name, is joined.
                    if len(row) >= 2 and "," in row[0]:
                        parts = [part.strip() for part in row[0].split(",")]
                        if any(part.casefold() in names for part in parts[1:]):
                            local_hospitals.append({"institution": parts[0], "location": ", ".join(parts[1:]), "public_contact": row[1],
                                                    "source_url": page.get("source_url") or page.get("url"), "collected_at": page.get("collected_at"),
                                                    "as_of_date": page.get("as_of_date"), "original_row": row})
        candidates = national_budget.get("projects", []) if can_join_reference else []
        verified = [row for row in candidates if row.get("geographic_review_status") == "reviewed" and any(
            association.get("psgc") == lgu["psgc"] and association.get("review_status") == "reviewed" for association in row.get("lgu_associations", []))]
        verified_ids = {row["id"] for row in verified}
        name_matches = [row for row in discovery(candidates, names, lambda row: row.get("title")) if row["id"] not in verified_ids]
        historical_matches = discovery(historical, names, lambda row: row.get("program_name", row.get("name", ""))) if can_join_reference else []
        # Only a few identifiers/titles are included. Complete evidence remains in
        # the specialist explorer, not a duplicated budget ledger for every LGU.
        def budget_preview(row):
            return {key: row.get(key) for key in ("id", "title", "dataset", "house_stage", "scope", "geographic_review_status", "source_review_status")}
        historical_preview = [{key: row.get(key) for key in ("key", "fam_key", "name", "department_id")} for row in historical_matches[:3]]
        selected = local_statistics + local_budgets + local_projects + local_government + local_hospitals
        source_ids = {row.get("source_id") for row in selected if row.get("source_id")}
        source_urls = {row["source_url"] for row in selected if row.get("source_url")}
        sources = [row for row in reference.get("sources", []) if row.get("source_id") in source_ids or row.get("url") in source_urls]
        profiles["data/lgu-profiles/" + lgu["id"] + ".json"] = {
            "schema_version": 1, "lgu_id": lgu["id"], "psgc": lgu.get("psgc"),
            "statistics": unique(local_statistics), "budget_observations": unique(local_budgets),
            "planning_records": unique(local_projects), "government": unique(local_government), "hospitals": unique(local_hospitals),
            "barangays": local_barangays, "barangay_count": len(local_barangays) if local_barangays else None,
            "geography": {key: geo.get(key) for key in ("attribution", "registry_release", "barangay_note", "boundary_metadata", "barangay_source")} if can_join_reference else None,
            "national": {"snapshot_id": national_budget.get("manifest", {}).get("snapshot_id"), "verified": [budget_preview(row) for row in verified],
                         "discovery_count": len(name_matches), "discovery": [budget_preview(row) for row in name_matches[:3]],
                         "office_note": "Office associations do not establish a municipality's allocation."},
            "historical": {"discovery_count": len(historical_matches), "discovery": historical_preview},
            "sources": sources,
            "association_rules": "Generic records use LGU IDs or geographic codes. Provincial reference labels use an exact, unique registry-name crosswalk. Budget title matches are unverified discovery only; office jurisdiction never establishes location.",
        }
    return profiles
