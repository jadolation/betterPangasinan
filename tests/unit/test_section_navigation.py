from html.parser import HTMLParser

import pytest

import build


PAGES = {
    "transparency": "overview", "national-budget": "projects",
    "historical-budget": "historical", "budget-context": "context",
    "budget-hearings": "hearings", "finances": "finances", "methodology": "about",
    "projects": "", "procurement": "", "legislation": "", "map": "",
}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "data-section-item" in attrs:
            self.links.append(attrs)


def test_canonical_sections_and_order():
    assert build.SECTION_NAV_ITEMS == (
        ("overview", "Overview", "transparency.html"),
        ("projects", "2027 Projects", "national-budget.html"),
        ("historical", "Historical Budgets", "historical-budget.html"),
        ("offices", "Offices & Districts", "national-budget.html#offices"),
        ("context", "Context", "budget-context.html"),
        ("hearings", "Hearings", "budget-hearings.html"),
        ("finances", "Local Finances", "finances.html"),
        ("about", "About", "methodology.html#national-budget-methodology"),
    )


@pytest.mark.parametrize("name,selected", PAGES.items())
def test_section_metadata_and_current_item(name, selected):
    meta, body = build.parse_page((build.SRC_PAGES / f"{name}.html").read_text())
    assert meta["section_nav"] == "transparency"
    assert meta.get("section_item", "") == selected
    parser = Links()
    parser.feed(build.render_section_nav(meta))
    assert len(parser.links) == 8
    assert [a["data-section-item"] for a in parser.links if "aria-current" in a] == ([selected] if selected else [])
    assert 'class="tp-nav"' not in body
    assert 'aria-label="Budget evidence"' not in body


def test_navigation_is_explicit_not_inferred_from_title():
    assert build.render_section_nav({"title": "Transparency"}) == ""
    for name in ("index", "lgu", "lgus", "government", "hospitals", "statistics"):
        meta, _ = build.parse_page((build.SRC_PAGES / f"{name}.html").read_text())
        assert not build.render_section_nav(meta)
    with pytest.raises(ValueError, match="Unknown section navigation"):
        build.render_section_nav({"section_nav": "unknown"})
    with pytest.raises(ValueError, match="Unknown transparency section item"):
        build.render_section_nav({"section_nav": "transparency", "section_item": "unknown"})


def test_base_navigation_precedes_main_and_helper_is_global():
    base = (build.SRC_PARTIALS / "base.html").read_text()
    assert base.index("{{HEADER}}") < base.index("{{SECTION_NAV}}") < base.index('<main ')
    assert 'src="assets/section-nav.js"' in base
    assert 'href="assets/transparency.css"' in base
    _, body = build.parse_page((build.SRC_PAGES / "national-budget.html").read_text())
    assert 'id="about-data"' in body


def test_historical_coverage_is_collapsed_without_hiding_summary():
    _, body = build.parse_page((build.SRC_PAGES / "historical-budget.html").read_text())
    assert '<p id="hb-coverage-summary"></p><details>' in body
    assert '<summary>Collection coverage and source qualifications</summary>' in body
    assert 'id="hb-coverage"' in body
    assert 'id="hb-sources"' in body
