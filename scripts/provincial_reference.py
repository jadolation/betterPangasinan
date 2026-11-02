"""Dedicated source-preserving provincial reference publication and HTML collection."""
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

DATASETS = ('statistics', 'hospital_directory_observations', 'budget_observations',
            'legislation_index', 'project_leads', 'lgu_registry_2024', 'collection_gaps')
PAGES = {
    'directory': 'https://www.pangasinan.gov.ph/directory/',
    'disaster-services': 'https://www.pangasinan.gov.ph/department/provincial-disaster-risk-reduction-and-management-office/services/',
    'history': 'https://www.pangasinan.gov.ph/history/',
    'about': 'https://www.pangasinan.gov.ph/about-pangasinan/',
}


class PublicHTML(HTMLParser):
    """Read actual table cells and Elementor public text, excluding executable content."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.cell = None
        self.row = None
        self.rows = []
        self.text = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self.skip += 1
        if tag == 'tr':
            self.row = []
        if tag in ('td', 'th'):
            self.cell = []
        if tag == 'a' and attrs.get('href', '').startswith('https://'):
            self.links.append(attrs['href'])

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self.skip = max(0, self.skip - 1)
        if tag in ('td', 'th') and self.cell is not None:
            if self.row is not None:
                self.row.append(' '.join(' '.join(self.cell).split()))
            self.cell = None
        if tag == 'tr' and self.row is not None:
            if any(self.row):
                self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.text.append(data.strip())
            if self.cell is not None:
                self.cell.append(data.strip())


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')


def normalize(root):
    root = Path(root)
    out = root / 'data/provincial_reference'
    out.mkdir(parents=True, exist_ok=True)
    research = root / 'Better_Pangasinan_Research_Batch_01'
    sources = json.loads((research / 'source_inventory.json').read_text())
    save_json(out / 'sources.json', sources)
    for name in DATASETS:
        rows = json.loads((research / (name + '.json')).read_text())
        save_json(out / (name + '.json'), [dict(row, id=f'{name}-{i:03}',
            publication_review='publication_reviewed', collected_date='2026-10-31',
            reference_collection_status='supplied_research') for i, row in enumerate(rows, 1)])


def collect(root):
    out = Path(root) / 'data/provincial_reference'
    raw = out / 'raw'
    raw.mkdir(parents=True, exist_ok=True)
    records, log = [], []
    for name, url in PAGES.items():
        stamp = datetime.now(timezone.utc).isoformat()
        try:
            with urlopen(Request(url, headers={'User-Agent': 'BetterPangasinan/1.0 public reference collection'}), timeout=60) as response:
                html = response.read().decode('utf-8')
                final_url = response.url
            (raw / (name + '.html')).write_text(html, encoding='utf-8')
            parser = PublicHTML()
            parser.feed(html)
            text = parser.text
            if name == 'directory':
                start = text.index('OFFICES')
                text = text[start:text.index('Back', start)]
            elif name == 'disaster-services':
                start = text.index('24/7 Operations and Early Warning System')
                text = text[start:text.index('Back', start)]
            else:
                start = next(i for i, value in enumerate(text) if len(value) > 200)
                end = next((i for i in range(start, len(text)) if text[i] == 'Back'), len(text))
                text = text[start:end]
            records.append(dict(id=name, source_id='live-' + name, source_url=url,
                collected_at=stamp, collection_status='official_html_collected',
                as_of_date=None, rows=parser.rows, text=text,
                links=sorted(set(parser.links))))
            log.append(dict(url=url, final_url=final_url, collected_at=stamp, status='collected'))
        except Exception as exc:
            log.append(dict(url=url, collected_at=stamp, status='failed', error=str(exc)))
    save_json(raw / 'collection-log.json', log)
    save_json(out / 'official_pages.json', records)


def publication_payload(root):
    root = Path(root)
    folder = root / 'data/provincial_reference'
    bundle = {'metadata': {'publication_review': 'publication_reviewed',
        'review_basis': 'User approved supplied research for display as-is; not independent official verification.',
        'research_collected_date': '2026-10-31',
        'notice': 'Source collection dates are not reporting periods or proof of current terms. Budget observations are not actual expenditure; project leads are not awards.'},
        'sources': json.loads((folder / 'sources.json').read_text()),
        'official_pages': json.loads((folder / 'official_pages.json').read_text())}
    for name in DATASETS:
        bundle[name] = json.loads((folder / (name + '.json')).read_text())
    import jsonschema
    jsonschema.validate(bundle, json.loads((root / 'schemas/provincial_reference.schema.json').read_text()))
    source_ids = [s['source_id'] for s in bundle['sources']]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError('Duplicate source IDs')
    ids = set()
    for page in bundle['official_pages']:
        if page['id'] in ids:
            raise ValueError('Duplicate official page ID')
        ids.add(page['id'])
        if page['source_id'] in source_ids:
            raise ValueError('Duplicate official source ID')
        source_ids.append(page['source_id'])
    for name in DATASETS:
        for row in bundle[name]:
            if row['id'] in ids:
                raise ValueError('Duplicate record ID')
            ids.add(row['id'])
            if row.get('source_id') and row['source_id'] not in source_ids:
                raise ValueError('Unknown source ID: ' + row['source_id'])
    for source in bundle['sources']:
        if not re.match(r'^https://[^/]+/', source['url']):
            raise ValueError('Source URL must be HTTPS')
    for name in DATASETS:
        for row in bundle[name]:
            if row.get('source_url') and not row['source_url'].startswith('https://'):
                raise ValueError('Record URL must be HTTPS')
    return {'data/provincial-reference.json': bundle}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['normalize', 'collect', 'validate'])
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if args.action == 'validate':
        publication_payload(args.root)
    else:
        globals()[args.action](args.root)
