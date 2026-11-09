from collector.province_pages import collect


def test_robots_denial_prevents_page_requests(tmp_path):
    calls = []

    def fetch(url, target):
        calls.append(url)
        return dict(
            url=url,
            status=200,
            error=None,
            headers={"content-type": "text/plain"},
            body=b"User-agent: *\nDisallow: /\n",
        )

    report = collect(tmp_path / "run", fetch=fetch, sleep=lambda _: None)
    assert len(calls) == 1
    assert all(r["status"] == "robots_denied" for r in report["sources"])
