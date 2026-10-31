import json
import shutil
from pathlib import Path

import pytest

import build


def snapshot(directory):
    return {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


def test_production_artifact_is_isolated_and_reproducible(tmp_path):
    output = tmp_path / "public"
    build.build(output=output, root_compatibility=False)
    first = snapshot(output)
    build.build(output=output, root_compatibility=False)
    assert first == snapshot(output)
    assert (output / "logo.svg").read_bytes() == (build.ROOT / "logo.svg").read_bytes()
    assert (output / "assets" / "style.css").exists()
    assert json.loads((output / "data" / "public.json").read_text()) == {key: [] for key in build.DATASETS}
    assert not any(part in {"tests", "fixtures", "src", "schemas", ".git", ".kilo"} for path in first for part in Path(path).parts)
    for page in build.SRC_PAGES.glob("*.html"):
        assert (output / page.name).exists()


def test_fixture_build_is_populated_but_separate(tmp_path):
    output = tmp_path / "synthetic"
    build.build("test", output, root_compatibility=False)
    records = json.loads((output / "data" / "public.json").read_text())
    assert len(records["lgus"]) == 4
    assert all(record["is_mock"] for dataset in records.values() for record in dataset)


def test_bad_data_does_not_replace_output(tmp_path):
    output = tmp_path / "public"
    build.build(output=output, root_compatibility=False)
    before = snapshot(output)
    with pytest.raises(ValueError):
        build.build(output=output, data_dir=build.ROOT / "data" / "fixtures", root_compatibility=False)
    assert before == snapshot(output)


def test_refuses_unowned_output(tmp_path):
    (tmp_path / "keep.txt").write_text("user work")
    with pytest.raises(ValueError, match="not owned"):
        build.build(output=tmp_path, root_compatibility=False)
    assert (tmp_path / "keep.txt").read_text() == "user work"


def test_refuses_source_output():
    with pytest.raises(ValueError, match="Unsafe"):
        build.build(output=build.ROOT / "src", root_compatibility=False)


def test_front_matter_and_template():
    meta, body = build.parse_page("---\ntitle: Test\ndescription: Example\n---\n<p>Body</p>\n")
    assert meta["title"] == "Test"
    assert body == "<p>Body</p>"
    assert build.fill("{{BODY}}", {"BODY": body}) == body
    with pytest.raises(SystemExit):
        build.parse_page("missing metadata")


def test_optional_dictionary_and_escaped_metadata(tmp_path, monkeypatch):
    source = tmp_path / "src"
    pages = source / "pages"
    partials = source / "partials"
    pages.mkdir(parents=True)
    partials.mkdir()
    (pages / "index.html").write_text('---\ntitle: <unsafe>\ndescription: "quote"\n---\nBody')
    (partials / "base.html").write_text("{{TITLE}} {{DESCRIPTION}} {{BODY}}")
    (partials / "header.html").write_text("")
    (partials / "footer.html").write_text("")
    monkeypatch.setattr(build, "SRC_PAGES", pages)
    monkeypatch.setattr(build, "SRC_PARTIALS", partials)
    # The production repository deliberately need not contain a locale file.
    output = tmp_path / "out"
    build.build(output=output, root_compatibility=False)
    text = (output / "index.html").read_text()
    assert "&lt;unsafe&gt;" in text and "&quot;quote&quot;" in text


def test_dictionary_is_optional_escaped_and_strict_when_present(tmp_path, monkeypatch):
    shutil.copytree(build.ROOT / "schemas", tmp_path / "schemas")
    shutil.copytree(build.ROOT / "data" / "production", tmp_path / "data" / "production")
    pages = tmp_path / "src" / "pages"
    partials = tmp_path / "src" / "partials"
    locales = tmp_path / "src" / "locales"
    pages.mkdir(parents=True)
    partials.mkdir()
    locales.mkdir()
    page = pages / "index.html"
    page.write_text('---\ntitle: Test\ndescription: Test\n---\nFallback content')
    (partials / "base.html").write_text("<head></head>{{BODY}}")
    (partials / "header.html").write_text("")
    (partials / "footer.html").write_text("")
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "SRC_PAGES", pages)
    monkeypatch.setattr(build, "SRC_PARTIALS", partials)
    output = tmp_path / "public"
    build.build(output=output, root_compatibility=False)
    assert "Fallback content" in (output / "index.html").read_text()
    page.write_text('---\ntitle: Test\ndescription: Test\n---\n{{t:flat}} {{t:nested.label}}')
    (locales / "en.json").write_text(json.dumps({"flat": "<script>", "nested": {"label": '"quoted"'}}))
    build.build(output=output, root_compatibility=False)
    text = (output / "index.html").read_text()
    assert "&lt;script&gt; &quot;quoted&quot;" in text
    assert '<meta name="data-mode" content="production">' in text
    before = snapshot(output)
    (locales / "en.json").write_text("{}")
    with pytest.raises(ValueError, match="Missing English translation"):
        build.build(output=output, root_compatibility=False)
    assert snapshot(output) == before
