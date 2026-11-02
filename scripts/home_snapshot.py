"""Lightweight counts derived from validated publication resources, never totals."""


def publication_payload(data, supplemental, national_budget):
    reference = supplemental.get("data/provincial-reference.json", {})
    historical = supplemental.get("data/historical-budget/manifest.json", {})
    hearings = supplemental.get("data/budget-hearings.json", {})
    national = national_budget.get("manifest", {})
    response = hearings.get("response")
    hearing_rows = response.get("data") if isinstance(response, dict) else None
    historical_count = historical.get("programs")
    return {
        "schema_version": 1,
        "transparency": {
            "budget_2027_records": len(national_budget["projects"]) if national.get("status") == "approved" else None,
            "historical_programs": historical_count if type(historical_count) is int and historical_count >= 0 else None,
            "hearing_topics": len(hearing_rows) if isinstance(hearing_rows, list) and not hearings.get("error") else None,
            "local_finance_records": len(data.get("finances", [])),
            "local_budget_observations": len(reference["budget_observations"]) if isinstance(reference.get("budget_observations"), list) else None,
        },
        "government": {"local_governments": len(data.get("lgus", [])), "service_records": len(data.get("services", []))},
        "reference_dates": {"fy2027_retrieved_at": national.get("retrieved_at"), "historical_collected_at": historical.get("collected_at")},
    }
