"""Independent offline verification of a run's evidence and outputs.

Deliberately re-reads raw evidence without build.py's parsers, so a mapping bug
cannot verify itself. Results bind to the manifest and output hashes; `status`
reports them stale when either changes. Passing is evidence for human review,
never publication approval.
"""
import csv
import json
import re
import tempfile
from pathlib import Path

from .runs import ROOT, Run, file_sha256, now, read_json, write_json

CHECKLIST = ROOT / 'doc' / 'P0-VERIFICATION.md'
AUTO_START = '<!-- web-crawler:auto:start -->'
AUTO_END = '<!-- web-crawler:auto:end -->'
OUTPUTS = ['pangasinan_overview.json', 'pangasinan_lgus.json', 'pangasinan_barangays.json', 'lgu_directory.csv',
           'collection_gaps.csv', 'source_inventory.csv', 'collection_log.csv', 'inconsistencies.json']
# Brief sections 2 and 3: field -> output key.
OVERVIEW_FIELDS = ['official_name', 'psgc', 'region', 'capital', 'population_2024', 'number_of_cities',
                   'number_of_municipalities', 'number_of_barangays', 'land_area_ha', 'coordinates',
                   'seal_logo', 'official_website']
LGU_FIELDS = ['name', 'psgc', 'classification', 'legislative_district', 'population_2024', 'land_area_ha',
              'barangay_count', 'website', 'facebook', 'address', 'contact', 'coordinates']


class Checks:
    def __init__(self):
        self.items = []

    def add(self, name, ok, detail=None, failures=None):
        failures = failures or []
        self.items.append({'check': name, 'result': 'pass' if ok and not failures else 'fail',
                           'detail': detail, 'failures': failures[:25], 'failure_count': len(failures)})


def fingerprint(run_path):
    run_path = Path(run_path)
    out = run_path / 'output'
    return {'manifest_sha256': file_sha256(run_path / 'manifest.json'),
            'outputs': {p.name: file_sha256(p) for p in sorted(out.iterdir())} if out.is_dir() else {}}


def raw_psa_records(run, role, version):
    rows = []
    for e in sorted(run.evidence('psa-psgc', role=role, version=version), key=lambda e: e['page_number']):
        body = json.loads((run.path / e['artifact']).read_bytes())
        rows += [(r, e['artifact'], i) for i, r in enumerate(body['results'])]
        declared = body['count']
    return rows, (declared if rows else None)


def resolve_pointer(document, pointer):
    for part in pointer.strip('/').split('/'):
        document = document[int(part)] if isinstance(document, list) else document[part]
    return document


def osm_inside(extract, node):
    """Point-in-province test assembled here, independently of build.py."""
    from shapely.geometry import MultiLineString, Point
    from shapely.ops import polygonize
    rings = MultiLineString([w['coords'] for w in extract['boundary_ways'] if w['role'] == 'outer']).union(
        MultiLineString([]))
    return any(poly.contains(Point(node['lon'], node['lat'])) for poly in polygonize(rings))


def verify(run_path, update_checklist=True):
    run = Run(run_path)
    c = Checks()
    out = run.path / 'output'

    # 1. Evidence integrity and secret redaction.
    bad = [e['artifact'] for e in run.manifest['evidence']
           if not (run.path / e['artifact']).is_file() or file_sha256(run.path / e['artifact']) != e['artifact_sha256']]
    listed = {e['artifact'] for e in run.manifest['evidence']}
    on_disk = {str(p.relative_to(run.path)) for p in (run.path / 'evidence').rglob('*') if p.is_file()}
    c.add('evidence_hashes_match_manifest', not bad, f'{len(listed)} artifacts', bad)
    c.add('no_unlisted_evidence_files', on_disk == listed, None, sorted(on_disk ^ listed))
    try:
        from .net import read_token
        secret = read_token()
        leaked = [a for a in listed if secret.encode() in (run.path / a).read_bytes()]
        c.add('no_credential_in_evidence', not leaked, 'scanned with the configured PSA token', leaked)
    except Exception:  # noqa: BLE001 - absence of a token is reported, not fatal
        c.add('no_credential_in_evidence', False, 'token unavailable; scan not performed')
    leaked_urls = [e['artifact'] for e in run.manifest['evidence'] if 'token=' in (e.get('source_url') or '')]
    c.add('no_credential_in_recorded_urls', not leaked_urls, None, leaked_urls)

    # 2. Reproducibility: rebuild into a scratch directory and compare hashes.
    from .build import build
    if not (out / 'build.json').is_file():
        c.add('outputs_present', False, 'run has not been built')
        return finish(run, c, None, update_checklist)
    with tempfile.TemporaryDirectory() as scratch:
        build(run.path, Path(scratch) / 'output')
        rebuilt = {p.name: file_sha256(p) for p in sorted((Path(scratch) / 'output').iterdir())}
    current = {p.name: file_sha256(p) for p in sorted(out.iterdir())}
    c.add('rebuild_reproduces_outputs', rebuilt == current, None,
          sorted(k for k in rebuilt.keys() | current.keys() if rebuilt.get(k) != current.get(k)))
    c.add('required_outputs_present', all((out / f).is_file() for f in OUTPUTS), None,
          [f for f in OUTPUTS if not (out / f).is_file()])

    overview = read_json(out / 'pangasinan_overview.json')
    lgus = read_json(out / 'pangasinan_lgus.json')['records']
    bgys = read_json(out / 'pangasinan_barangays.json')['records']
    ov = overview['record']
    records = [ov, *lgus, *bgys]

    # 3. Independent recount from raw PSA evidence.
    psa = run.manifest.get('psa', {})
    raw, declared = raw_psa_records(run, 'geography', psa.get('geography_release'))
    c.add('psa_pages_cover_declared_count', declared is not None and len(raw) == declared,
          f'{len(raw)} rows, API count {declared}')
    raw_codes = {r['code'].zfill(10): r for r, _, _ in raw}
    out_codes = [r['psgc'] for r in records]
    c.add('psgc_ten_digit_strings', all(isinstance(x, str) and re.fullmatch(r'[0-9]{10}', x) for x in out_codes),
          None, [x for x in out_codes if not (isinstance(x, str) and re.fullmatch(r'[0-9]{10}', x))])
    c.add('psgc_unique', len(set(out_codes)) == len(out_codes), None,
          sorted({x for x in out_codes if out_codes.count(x) > 1}))
    c.add('every_psa_record_exported_once', set(out_codes) == set(raw_codes), None,
          sorted(set(out_codes) ^ set(raw_codes)))
    levels = {r['psgc']: r['geographic_level'] for r in records}
    expected_parent = {'City': {'Prov'}, 'Mun': {'Prov'}, 'Bgy': {'City', 'Mun'}}
    parent_failures = [r['psgc'] for r in records if r['geographic_level'] != 'Prov' and (
        r['parent_psgc'] == r['psgc'] or levels.get(r['parent_psgc']) not in expected_parent[r['geographic_level']])]
    c.add('parents_exist_with_correct_type', not parent_failures and ov['parent_psgc'] is None, None, parent_failures)
    by_level = {lvl: sum(1 for r in raw_codes.values() if r['geographic_level'] == lvl) for lvl in ('City', 'Mun', 'Bgy')}
    c.add('overview_counts_match_raw', (ov['number_of_cities']['value'], ov['number_of_municipalities']['value'],
                                        ov['number_of_barangays']['value']) == (by_level['City'], by_level['Mun'], by_level['Bgy']),
          by_level)
    c.add('lgu_and_barangay_datasets_partitioned',
          all(r['geographic_level'] in ('City', 'Mun') for r in lgus) and all(r['geographic_level'] == 'Bgy' for r in bgys))

    # 4. Field-to-source reconciliation: every evidenced value is re-read from its artifact.
    mismatches, checked = [], 0
    page_text = {}
    for rec in records:
        for key, field in rec.items():
            if not isinstance(field, dict) or field.get('value') is None or not isinstance(field.get('evidence'), dict):
                continue
            ev = field['evidence']
            if 'artifact' not in ev:
                continue
            path = run.path / ev['artifact']
            if file_sha256(path) != ev.get('artifact_sha256'):
                mismatches.append(f'{rec["psgc"]}:{key}:artifact_hash')
                continue
            checked += 1
            if 'json_pointer' in ev and ev['artifact'].startswith('evidence/psa-psgc/'):
                try:
                    source = resolve_pointer(json.loads(path.read_bytes()), ev['json_pointer'])
                except (KeyError, IndexError, ValueError):
                    mismatches.append(f'{rec["psgc"]}:{key}:pointer')
                    continue
                if isinstance(source, dict):
                    source = source.get('area_name') if key in ('name', 'official_name', 'region') \
                        else source.get('population')
                if key.startswith('population'):
                    ok = str(source).strip().replace(',', '') == str(field['value'])
                else:
                    ok = source == field['value'] or (key == 'classification' and
                                                      {'City': 'city', 'Mun': 'municipality'}.get(source) == field['value'])
                if not ok:
                    mismatches.append(f'{rec["psgc"]}:{key}:{source!r}!={field["value"]!r}')
            elif 'quote' in ev:
                text = page_text.setdefault(ev['artifact'], json.loads(path.read_bytes())['text'])
                if ev['quote'] not in text:
                    mismatches.append(f'{rec["psgc"]}:{key}:quote_not_in_page')
                elif (isinstance(field['value'], (int, float)) and key != 'legislative_district'
                      and (str(field['value']) if isinstance(field['value'], int) else f'{field["value"]:g}')
                      not in ev['quote'].replace(',', '')):
                    mismatches.append(f'{rec["psgc"]}:{key}:value_not_in_quote')
            elif 'quotes' in ev:
                text = page_text.setdefault(ev['artifact'], json.loads(path.read_bytes())['text'])
                joined = ' '.join(ev['quotes'])
                v = field['value']
                parts = ([p['number'] for p in v['phones']] + v['emails']) if isinstance(v, dict) else [v]
                if any(q not in text for q in ev['quotes']):
                    mismatches.append(f'{rec["psgc"]}:{key}:quote_not_in_page')
                elif any(part not in joined for part in parts):
                    mismatches.append(f'{rec["psgc"]}:{key}:value_not_in_quotes')
            elif ev['artifact'].startswith('evidence/osm-geofabrik/'):
                extract = page_text.setdefault(ev['artifact'], json.loads(path.read_bytes()))
                node = resolve_pointer(extract, ev['json_pointer'])
                if node['id'] != ev.get('osm_node') or {'lat': node['lat'], 'lon': node['lon']} != field['value']:
                    mismatches.append(f'{rec["psgc"]}:{key}:osm_node_mismatch')
                elif not osm_inside(extract, node):
                    mismatches.append(f'{rec["psgc"]}:{key}:osm_node_outside_province')
            elif 'link_text' in ev:
                links = json.loads(path.read_bytes())['links']
                if not any(a['href'] == field['value'] and a['text'].strip().upper() == ev['link_text'] for a in links):
                    mismatches.append(f'{rec["psgc"]}:{key}:link_not_in_page')
    c.add('field_values_match_cited_evidence', not mismatches, f'{checked} evidenced fields re-read', mismatches)

    # 5. Missingness is explicit; review barriers hold.
    unexplained = [f'{r["psgc"]}:{k}' for r in records for k, f in r.items()
                   if isinstance(f, dict) and 'value' in f and f['value'] is None and not f.get('missing_reason')]
    c.add('missing_values_have_reasons', not unexplained, None, unexplained)
    zero_unknowns = [f'{r["psgc"]}:{k}' for r in records for k, f in r.items()
                     if isinstance(f, dict) and f.get('value') == 0 and 'evidence' not in f]
    c.add('no_unevidenced_zero_values', not zero_unknowns, None, zero_unknowns)
    unsafe = [r['psgc'] for r in records if r.get('review_status') != 'pending' or r.get('is_mock') is not False]
    c.add('records_review_pending_and_not_mock', not unsafe, None, unsafe)
    with (out / 'lgu_directory.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    c.add('directory_csv_matches_lgu_json', [r['psgc'] for r in rows] == [r['psgc'] for r in lgus], f'{len(rows)} rows')

    # 6. Completeness matrix against brief fields (reported, not a pass/fail gate).
    def status(field):
        if field is None:
            return 'not_applicable'
        if isinstance(field, str):
            return 'filled'
        if field.get('value') is not None:
            return 'filled'
        return 'conflict' if 'candidates' in field else 'missing'
    completeness = {'overview': {f: status(ov.get(f)) for f in OVERVIEW_FIELDS},
                    'lgus': {f: {s: sum(status(r.get(f)) == s for r in lgus) for s in ('filled', 'missing', 'conflict')}
                             for f in LGU_FIELDS},
                    'barangays': {'records': len(bgys),
                                  'population_2024_filled': sum(r['population_2024']['value'] is not None for r in bgys)}}
    return finish(run, c, completeness, update_checklist)


def finish(run, c, completeness, update_checklist):
    out = run.path / 'output'
    issues = read_json(out / 'inconsistencies.json')['issues'] if (out / 'inconsistencies.json').is_file() else []
    structural = 'passed' if all(i['result'] == 'pass' for i in c.items) else 'failed'
    filled = completeness and all(v == 'filled' for v in completeness['overview'].values()) and all(
        v['missing'] == 0 and v['conflict'] == 0 for v in completeness['lgus'].values())
    result = {
        'run_id': run.id, 'verified_at': now(), **fingerprint(run.path),
        'validation_status': structural,
        'collection_completeness': 'complete' if filled else 'partial',
        'integration_readiness': 'not_assessed',
        'publication_approval': 'not_approved',
        'source_errors': run.manifest['errors'],
        'checks': c.items, 'completeness': completeness,
        'inconsistency_counts': {t: sum(i['type'] == t for i in issues) for t in sorted({i['type'] for i in issues})},
    }
    write_json(run.path / 'verification.json', result)
    if update_checklist:
        update_doc(run, result)
    return result


def staleness(run_path):
    path = Path(run_path) / 'verification.json'
    if not path.is_file():
        return 'unverified'
    saved = read_json(path)
    current = fingerprint(run_path)
    # verification.json itself is not in output/, so it cannot invalidate itself.
    return 'current' if (saved['manifest_sha256'], saved['outputs']) == (current['manifest_sha256'], current['outputs']) else 'stale'


def update_doc(run, result):
    lines = [AUTO_START, '', f'## Latest automated verification — run `{run.id}`', '',
             'Generated by `web-crawler verify`. Automated results are evidence for human review, not approval. '
             'Re-run `web-crawler status` to see whether these results are stale.', '',
             f'- Verified at: {result["verified_at"]}',
             f'- Manifest SHA-256: `{result["manifest_sha256"]}`',
             f'- PSGC release: {run.manifest.get("psa", {}).get("geography_release")}; '
             f'population release: {run.manifest.get("psa", {}).get("population_release")}',
             f'- Structural validation: **{result["validation_status"]}**; collection completeness: '
             f'**{result["collection_completeness"]}**; publication: **{result["publication_approval"]}**',
             f'- Source errors during collection: {len(result["source_errors"])}', '',
             '| Check | Result | Detail |', '| --- | --- | --- |']
    for item in result['checks']:
        detail = item['detail'] if isinstance(item['detail'], str) else json.dumps(item['detail']) if item['detail'] else ''
        if item['failure_count']:
            detail += f' — {item["failure_count"]} failure(s), e.g. `{item["failures"][0]}`'
        lines.append(f'| {item["check"]} | {item["result"]} | {detail} |')
    if result['completeness']:
        lines += ['', '### Field completeness (brief §2–3)', '', '| Overview field | Status |', '| --- | --- |']
        lines += [f'| {k} | {v} |' for k, v in result['completeness']['overview'].items()]
        lines += ['', '| LGU field | Filled | Missing | Conflict |', '| --- | --- | --- | --- |']
        lines += [f'| {k} | {v["filled"]} | {v["missing"]} | {v["conflict"]} |'
                  for k, v in result['completeness']['lgus'].items()]
    lines += ['', '### Inconsistencies for review', '']
    lines += [f'- {t}: {n}' for t, n in result['inconsistency_counts'].items()] or ['- none flagged']
    lines += ['', f'Details: `data/staging/web-crawler/runs/{run.id}/output/inconsistencies.json`, '
                  '`collection_gaps.csv`, `verification.json`.', '', AUTO_END]
    block = '\n'.join(lines)
    text = CHECKLIST.read_text() if CHECKLIST.is_file() else '# P0 verification checklist\n'
    if AUTO_START in text and AUTO_END in text:
        text = text[:text.index(AUTO_START)] + block + text[text.index(AUTO_END) + len(AUTO_END):]
    else:
        text = text.rstrip() + '\n\n' + block + '\n'
    CHECKLIST.write_text(text)
