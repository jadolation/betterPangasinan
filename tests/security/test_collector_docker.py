"""Container contract: offline defaults, explicit live profile, private build context."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_offline_service_stays_isolated_and_live_requires_profile():
    config = yaml.safe_load((ROOT / "compose.collector.yaml").read_text())
    offline = config["services"]["collector"]
    assert offline["network_mode"] == "none"
    assert offline["read_only"] is True
    live = config["services"]["practice"]
    assert live["profiles"] == ["practice"]
    assert live["entrypoint"] == ["python", "-m", "collector.practice"]
    assert live["read_only"] is True
    assert live["networks"] == ["practice"]
    assert live["volumes"] == ["./data/staging:/app/data/staging"]
    assert live["cap_drop"] == ["ALL"]
    assert "environment" not in live


def test_image_contains_live_and_database_test_runtime():
    dockerfile = (ROOT / "Dockerfile.collector").read_text()
    assert "curl" in dockerfile and "ca-certificates" in dockerfile
    assert "--require-hashes" in dockerfile
    assert "COPY scripts ./scripts" in dockerfile
    assert "COPY migrations ./migrations" in dockerfile
    assert "COPY data/national_budget/config.json" in dockerfile
    assert "USER 10001" in dockerfile
    ignore = (ROOT / "Dockerfile.collector.dockerignore").read_text().splitlines()
    assert ignore[0] == "**"
    assert "!data/national_budget/config.json" in ignore
    assert "!data/**" not in ignore
    assert "!data/staging/**" not in ignore
