import pytest

from collector.practice import public_addresses, practice


def response(url, target, **kwargs):
    body = (
        b"User-agent: *\nAllow: /\n"
        if url.endswith("/robots.txt")
        else b"<html><p>Public reference page</p></html>"
    )
    if "/api/" in url:
        body = b'{"meta": {}, "data": {"datasets": []}}'
    return {
        "url": url,
        "status": 200,
        "headers": {
            "content-type": "text/plain"
            if url.endswith("/robots.txt")
            else "application/json"
            if "/api/" in url
            else "text/html"
        },
        "body": body,
        "remote_ip": "1.1.1.1",
        "error": None,
    }


def test_practice_real_mode_is_explicit_and_source_config_unchanged(tmp_path):
    with pytest.raises(ValueError, match="authorization"):
        practice(tmp_path, authorized=False, fetch=response, sleep=lambda _: None)


def test_practice_preserves_evidence_and_leaves_psa_disabled(tmp_path):
    report = practice(tmp_path, authorized=True, fetch=response, sleep=lambda _: None)
    assert report["is_mock"] is False
    assert report["auto_publish"] is False
    rows = {r["source_id"]: r for r in report["sources"]}
    assert rows["psa_psgc"]["status"] == "disabled_in_current_configuration"
    assert rows["province_about"]["status"] == "collected_for_review"
    assert rows["budget_overview"]["status"] == "collected_for_review"
    assert report["requests"] == 5
    assert (tmp_path / "manifest.json").exists()
    assert all(r["review_status"] == "pending" for r in report["sources"])
    assert all("sha256" in a for a in report["artifacts"])


def test_robots_denial_stops_before_page(tmp_path):
    def denied(url, target, **kwargs):
        assert url.endswith("/robots.txt")
        return {**response(url, target), "body": b"User-agent: *\nDisallow: /\n"}

    report = practice(tmp_path, authorized=True, fetch=denied, sleep=lambda _: None)
    assert report["requests"] == 3
    assert all(
        r["status"] in ("robots_denied", "disabled_in_current_configuration")
        for r in report["sources"]
    )


def test_challenge_and_404_do_not_become_success(tmp_path):
    def blocked(url, target, **kwargs):
        value = response(url, target)
        if "pangasinan.gov" in url:
            value.update(headers={"cf-mitigated": "challenge"})
        if "/api/" in url:
            value.update(status=404, body=b"<html>Not found</html>")
        return value

    report = practice(tmp_path, authorized=True, fetch=blocked, sleep=lambda _: None)
    rows = {r["source_id"]: r for r in report["sources"]}
    assert rows["province_about"]["status"] == "access_challenge"
    assert rows["budget_overview"]["status"] == "http_404"


def test_private_dns_rejected_before_connection():
    with pytest.raises(ValueError, match="public"):
        public_addresses(
            "psa.gov.ph",
            resolver=lambda *a, **k: [(None, None, None, None, ("127.0.0.1", 443))],
        )


def test_budget_uses_existing_collector_base_endpoint(tmp_path):
    from scripts.national_budget.collect import settings

    urls = []

    def fetch(url, target):
        urls.append(url)
        return response(url, target)

    practice(tmp_path, authorized=True, fetch=fetch, sleep=lambda _: None)
    api_urls = [url for url in urls if "/api/" in url]
    assert api_urls == [settings()["api_base"]]


def test_province_canonical_redirect_is_checked_and_preserved(tmp_path):
    def fetch(url, target):
        value = response(url, target)
        if url == "https://www.pangasinan.gov.ph/about-pangasinan/":
            value.update(
                status=301,
                body=b"",
                headers={
                    "location": "https://www.pangasinan.gov.ph/the-province/about-pangasinan/"
                },
            )
        return value

    report = practice(tmp_path, authorized=True, fetch=fetch, sleep=lambda _: None)
    row = next(r for r in report["sources"] if r["source_id"] == "province_about")
    assert row["status"] == "collected_for_review"
    assert row["effective_url"].endswith("/the-province/about-pangasinan/")
    assert any(a["status"] == 301 for a in report["artifacts"])


def test_redirect_cannot_escape_source(tmp_path):
    def fetch(url, target):
        assert "127.0.0.1" not in url
        value = response(url, target)
        if not url.endswith("/robots.txt"):
            value.update(
                status=302, headers={"location": "https://127.0.0.1/latest/meta-data/"}
            )
        return value

    report = practice(tmp_path, authorized=True, fetch=fetch, sleep=lambda _: None)
    assert all(
        row["status"] in ("disabled_in_current_configuration", "redirect_denied")
        for row in report["sources"]
    )
