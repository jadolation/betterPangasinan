import json
from pathlib import Path

import build


def test_root_mirror_is_replaced_only_after_complete_json_write(tmp_path, monkeypatch):
    destination = tmp_path / "barangays.json"
    destination.write_text('[{"name": "original"}]')
    content = json.dumps([{"name": "collected", "psgc": "0105501001"}] * 4000).encode()
    replace = build.os.replace
    calls = []

    def inspect(temporary, target):
        assert json.loads(destination.read_text()) == [{"name": "original"}]
        assert Path(temporary).read_bytes() == content
        calls.append(target)
        replace(temporary, target)

    monkeypatch.setattr(build.os, "replace", inspect)
    build.atomic_write(destination, content)
    assert destination.read_bytes() == content and calls == [destination]
    build.atomic_write(destination, content)
    assert calls == [destination]
    assert list(tmp_path.glob("*.tmp")) == []


def test_failed_atomic_replacement_keeps_the_previous_valid_file(tmp_path, monkeypatch):
    destination = tmp_path / "manifest.json"
    destination.write_text('{"status":"original"}')

    def fail(*args):
        raise OSError("Simulated file replacement failure")

    monkeypatch.setattr(build.os, "replace", fail)
    try:
        build.atomic_write(destination, b'{"status":"new"}')
    except OSError:
        pass
    else:
        raise AssertionError("Expected file replacement failure")
    assert json.loads(destination.read_text()) == {"status": "original"}
    assert list(tmp_path.glob("*.tmp")) == []
