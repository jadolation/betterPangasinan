import pytest
from collector.psa_api import token_from_file, scrub


def test_token_file_is_data_not_shell(tmp_path):
    path = tmp_path / ".env"
    path.write_text('PSA-TOKEN="example-secret"\nOTHER=$(touch /tmp/never)\n')
    assert token_from_file(path) == "example-secret"
    assert "example-secret" not in scrub("token=example-secret", "example-secret")
    path.write_text("OTHER=1\n")
    with pytest.raises(ValueError):
        token_from_file(path)


def test_geography_rejects_duplicate_and_missing_parent():
    from collector.psa_geography import validate

    province = dict(
        code="0105500000", geographic_level="Prov", version="Q2_2024", reg=1, prv=55
    )
    assert validate([province])[0]["parent_psgc"] is None
    with pytest.raises(ValueError, match="duplicate"):
        validate([province, province])
    with pytest.raises(ValueError, match="missing_parent"):
        validate([dict(province, code="0105501001", geographic_level="Bgy")])
