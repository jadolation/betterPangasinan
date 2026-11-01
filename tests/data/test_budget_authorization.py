"""Publication authorization does not establish source/geographic verification."""

import pytest

from scripts.national_budget import pipeline as budget
from test_national_budget import STAMP, decisions, manifest


def authorized(candidates):
    review = decisions(candidates)
    review["authorization"] = {
        "kind": "explicit_user_publication", "scope": "publication_only",
        "statement": "Synthetic test publication approval only", "authorized_at": STAMP,
        "recorded_by": "Synthetic test recorder", "original_candidate_sha256": candidates["candidate_sha256"],
        "source_values_sha256": budget.digest({row["id"]: budget.digest(row["upstream"]) for row in candidates["projects"]}),
    }
    for decision in review["projects"]:
        decision.update(scope="uncertain", geographic_review_status="pending", source_review_status="reviewed_with_warnings")
    return review


def test_explicit_publication_authorization_preserves_pending_geography():
    candidates = budget.normalize(manifest())
    review = authorized(candidates)
    result = budget.compile_snapshot(candidates, review)
    assert result["manifest"]["review"]["authorization"] == review["authorization"]
    assert result["projects"][0]["geographic_review_status"] == "pending"
    assert result["coverage"]["requiring_geographic_review"] == 1
    assert result["coverage"]["stage_totals_by_scope"]["geographic"] == {}


@pytest.mark.parametrize("changes", [
    {"scope": "geographic"}, {"geographic_review_status": "reviewed"}, {"source_review_status": "reviewed"},
])
def test_publication_only_authorization_does_not_verify_other_claims(changes):
    candidates = budget.normalize(manifest())
    review = authorized(candidates)
    review["projects"][0].update(changes)
    with pytest.raises(ValueError, match="Publication-only"):
        budget.compile_snapshot(candidates, review)


def test_authorization_is_bound_to_original_budget_values():
    candidates = budget.normalize(manifest())
    review = authorized(candidates)
    review["authorization"]["source_values_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Source values changed"):
        budget.compile_snapshot(candidates, review)


def test_recorded_application_cannot_precede_user_authorization():
    candidates = budget.normalize(manifest())
    review = authorized(candidates)
    review["authorization"]["authorized_at"] = "2026-10-26T11:00:00Z"
    with pytest.raises(ValueError, match="predate user authorization"):
        budget.compile_snapshot(candidates, review)
