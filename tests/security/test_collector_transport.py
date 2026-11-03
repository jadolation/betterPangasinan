import io
import zipfile

import httpx
import pytest

from collector.transport import (
    SourceConfig,
    download,
    inspect_xlsx,
    load_source,
    validate_url,
)


def config(**overrides):
    return SourceConfig(
        **dict(
            source_id="psa_psgc",
            agency="PSA",
            enabled=True,
            access_review="approved",
            start_url="https://psa.gov.ph/allowed/data.xlsx",
            allowed_hosts=["psa.gov.ph"],
            allowed_paths=["/allowed/"],
            **overrides,
        )
    )


def workbook():
    from openpyxl import Workbook

    output = io.BytesIO()
    Workbook().save(output)
    return output.getvalue()


def test_registry_is_disabled_and_rejects_unknown_settings():
    source = load_source("psa_psgc")
    assert source.enabled is False and source.start_url is None
    with pytest.raises(ValueError):
        SourceConfig(source_id="x", agency="x", arbitrary_command="evil")
    with pytest.raises(ValueError):
        load_source("../secrets")


@pytest.mark.parametrize(
    "url",
    [
        "http://psa.gov.ph/allowed/a.xlsx",
        "https://psa.gov.ph:444/allowed/a.xlsx",
        "https://user@psa.gov.ph/allowed/a.xlsx",
        "https://127.0.0.1/allowed/a.xlsx",
        "https://psa.gov.ph/not-allowed/a.xlsx",
        "https://psa.gov.ph/allowed/../private/a.xlsx",
        "https://psa.gov.ph/allowed/%2e%2e/private/a.xlsx",
        "https://psa.gov.ph/allowed/a.xlsx?q=x",
    ],
)
def test_url_policy_rejects_ambiguous_or_unapproved_destinations(url):
    with pytest.raises(ValueError):
        validate_url(config(), url, resolver=lambda host: ["8.8.8.8"])


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.1.1.1", "169.254.169.254", "::1", "192.0.2.1"]
)
def test_dns_requires_public_addresses(address):
    with pytest.raises(ValueError):
        validate_url(config(), config().start_url, resolver=lambda host: [address])


def test_live_network_refused_even_after_source_approval():
    with pytest.raises(ValueError, match="network isolation"):
        download(config(), authorized=True)


def test_authorization_is_required_before_injected_transport():
    calls = []
    with pytest.raises(ValueError):
        download(
            config(),
            transport=httpx.MockTransport(lambda request: calls.append(request)),
        )
    assert calls == []


def test_bounded_retry_then_original_bytes_and_attempt_audit():
    raw = workbook()
    statuses = iter([429, 503, 200])
    pauses = []
    result = download(
        config(),
        authorized=True,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                next(statuses),
                content=raw,
                headers={
                    "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "Retry-After": "2",
                },
            )
        ),
        resolver=lambda host: ["8.8.8.8"],
        sleep=pauses.append,
    )
    assert result.body == raw and len(result.attempts) == 3 and pauses == [2.0, 2.0]


@pytest.mark.parametrize("status,expected", [(404, 1), (500, 4), (429, 4)])
def test_http_failures_are_bounded(status, expected):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status)

    with pytest.raises(ValueError, match=f"HTTP_{status}"):
        download(
            config(),
            authorized=True,
            transport=httpx.MockTransport(respond),
            resolver=lambda host: ["8.8.8.8"],
            sleep=lambda seconds: None,
        )
    assert len(calls) == expected


def test_timeout_is_bounded():
    calls = []

    def respond(request):
        calls.append(request)
        raise httpx.ReadTimeout("timeout")

    with pytest.raises(ValueError, match="TIMEOUT"):
        download(
            config(),
            authorized=True,
            transport=httpx.MockTransport(respond),
            resolver=lambda host: ["8.8.8.8"],
            sleep=lambda seconds: None,
        )
    assert len(calls) == 4


def test_redirect_private_target_rejected_before_second_request():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            302, headers={"location": "https://127.0.0.1/allowed/a.xlsx"}
        )

    with pytest.raises(ValueError):
        download(
            config(),
            authorized=True,
            transport=httpx.MockTransport(respond),
            resolver=lambda host: ["8.8.8.8"],
        )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "body,kind",
    [(b"<html>blocked</html>", "text/html"), (b"not zip", "application/octet-stream")],
)
def test_substituted_files_rejected(body, kind):
    with pytest.raises(ValueError):
        download(
            config(),
            authorized=True,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, content=body, headers={"Content-Type": kind}
                )
            ),
            resolver=lambda host: ["8.8.8.8"],
        )


def test_xlsx_limits_and_active_content():
    inspect_xlsx(workbook())
    for name, body in [
        ("xl/vbaProject.bin", b"macro"),
        ("xl/externalLinks/a.xml", b"link"),
        ("xl/worksheets/sheet1.xml", b'<!DOCTYPE x [<!ENTITY e "evil">]>'),
    ]:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("[Content_Types].xml", "types")
            archive.writestr("xl/workbook.xml", "workbook")
            archive.writestr(name, body)
        with pytest.raises(ValueError):
            inspect_xlsx(output.getvalue())
    with pytest.raises(ValueError, match="size"):
        inspect_xlsx(workbook(), max_bytes=10)


@pytest.mark.parametrize(
    "xml",
    [
        '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE x [<!ENTITY e "expanded">]><x>&e;</x>'.encode(
            "utf-16"
        ),
        b"<Relationships><Relationship TargetMode = 'External' Target='https://example.invalid'/></Relationships>",
        b'<Relationships><Relationship TargetMode="Ext&#101;rnal"/></Relationships>',
        '<?xml version="1.0" encoding="UTF-16"?><Relationship TargetMode="External"/>'.encode(
            "utf-16"
        ),
        b"<broken>",
    ],
)
def test_xml_encoding_and_attribute_variants_cannot_bypass_validation(xml):
    original = zipfile.ZipFile(io.BytesIO(workbook()))
    output = io.BytesIO()
    with original, zipfile.ZipFile(output, "w") as archive:
        for entry in original.infolist():
            archive.writestr(
                entry,
                xml if entry.filename == "xl/workbook.xml" else original.read(entry),
            )
    with pytest.raises(ValueError, match="XML"):
        inspect_xlsx(output.getvalue())


@pytest.mark.parametrize(
    "retry_after",
    ["61", "9999999999999999999999999999999", "Thu, 01 Jan 1970 00:02:00 GMT"],
)
def test_long_retry_after_defers_without_early_retry(retry_after):
    calls, pauses = [], []

    def respond(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": retry_after})

    with pytest.raises(ValueError, match="RATE_LIMIT_DEFERRED"):
        download(
            config(),
            authorized=True,
            transport=httpx.MockTransport(respond),
            resolver=lambda host: ["8.8.8.8"],
            sleep=pauses.append,
            now=lambda: 0.0,
        )
    assert len(calls) == 1 and pauses == []


@pytest.mark.parametrize(
    "retry_after,expected",
    [("5", 5.0), ("0", 2.0), ("Thu, 01 Jan 1970 00:00:10 GMT", 10.0)],
)
def test_retry_after_small_duration_or_http_date_honored(retry_after, expected):
    raw = workbook()
    calls, pauses = [], []

    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": retry_after})
        return httpx.Response(
            200, content=raw, headers={"Content-Type": "application/octet-stream"}
        )

    download(
        config(),
        authorized=True,
        transport=httpx.MockTransport(respond),
        resolver=lambda host: ["8.8.8.8"],
        sleep=pauses.append,
        now=lambda: 0.0,
    )
    assert pauses == [expected]


def test_retry_without_header_adds_bounded_injectable_jitter():
    pauses = []
    with pytest.raises(ValueError, match="HTTP_503"):
        download(
            config(),
            authorized=True,
            transport=httpx.MockTransport(lambda request: httpx.Response(503)),
            resolver=lambda host: ["8.8.8.8"],
            sleep=pauses.append,
            jitter=lambda: 0.5,
        )
    assert pauses == [2.5, 2.5, 4.5]
