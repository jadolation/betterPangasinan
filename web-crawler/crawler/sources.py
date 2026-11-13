"""Source registry. Each source collects evidence into a run; mapping happens in build.py.

Add a source by writing a collect(run, options) function and registering it in SOURCES.
"""
import json
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.robotparser import RobotFileParser

from . import net
from .runs import ROOT, sha256

PSA_HOST = 'classification.psa.gov.ph'
PSA_SCOPE = {'reg': '1', 'prv': '55'}
PSA_DELAY = 1.5
PSA_MAX_PAGES = 20

PROVINCE_ORIGIN = 'https://www.pangasinan.gov.ph'
PROVINCE_PAGES = {
    'about': '/the-province/about-pangasinan/',
    'geography': '/the-province/geography/',
    'lgus': '/city-municipalities/',
    'directory': '/directory/',
}
DEFAULT_PAGES = ['about', 'geography', 'lgus']
# LGU detail pages are discovered only from links on the official list page.
LGU_LINK = re.compile(r'^https://www\.pangasinan\.gov\.ph/city-municipalities/([a-z0-9]+(?:-[a-z0-9]+)*)/$')
MAX_LGU_PAGES = 60


def candidate_versions(today=None):
    """Quarterly PSGC version names, newest first, from 2024 to the current quarter."""
    today = today or datetime.now(timezone.utc).date()
    current = (today.year, (today.month - 1) // 3 + 1)
    return [f'Q{q}_{y}' for y in range(current[0], 2023, -1) for q in range(4, 0, -1)
            if (y, q) <= current]


def _psa_page(run, secret, path, name, page_size, page, query=None, **meta):
    query = {**(query or PSA_SCOPE), 'page_size': str(page_size), 'page': str(page)}
    artifact, evidence = net.get(PSA_HOST, path, query, secret=secret)
    entry = run.add_evidence('psa-psgc', name, artifact, agency='Philippine Statistics Authority',
                             title='PSGC Classification API ' + path, **evidence, **meta)
    if evidence['http_status'] != 200:
        raise net.FetchError(f'http_{evidence["http_status"]}')
    return entry, json.loads(artifact)


def collect_psa(run, options):
    """Discover released versions, then fetch Pangasinan from the newest geography
    release and from the newest release that carries population observations."""
    secret = net.read_token()
    versions = options.get('psa_versions') or candidate_versions()
    found = []
    for version in versions:
        _, body = _psa_page(run, secret, f'/psgc/{version}/provinces', f'probe-{version}.json', 10, 1,
                            role='version_probe', version=version)
        rows = body.get('results') or []
        found.append({'version': version, 'pangasinan_rows': len(rows),
                      'has_populations': any(r.get('populations') for r in rows)})
        time.sleep(PSA_DELAY)
        if rows and any(f['has_populations'] for f in found):
            break
    available = [f for f in found if f['pangasinan_rows']]
    if not available:
        raise net.FetchError('no_release_found')
    geography = available[0]['version']
    population = next((f['version'] for f in available if f['has_populations']), None)
    run.manifest.setdefault('psa', {}).update(
        {'versions_probed': found, 'geography_release': geography, 'population_release': population})
    run.save_manifest()
    _psa_page(run, secret, f'/psgc/{geography}/regions', f'{geography}-region.json', 10, 1,
              role='region', version=geography, query={'reg': PSA_SCOPE['reg']})
    time.sleep(PSA_DELAY)
    for version, role in dict.fromkeys([(geography, 'geography'), (population, 'population')]):
        if version is None or (role == 'population' and version == geography):
            continue
        expected = None
        for page in range(1, PSA_MAX_PAGES + 1):
            _, body = _psa_page(run, secret, f'/psgc/{version}/all', f'{version}-all-p{page}.json', 500, page,
                                role=role, version=version, page_number=page)
            if expected is not None and body.get('count') != expected:
                raise net.FetchError('count_changed_between_pages')
            expected = body.get('count')
            time.sleep(PSA_DELAY)
            if not body.get('next'):
                break
        else:
            raise net.FetchError('page_limit')
    if population == geography:
        run.manifest['psa']['population_release'] = geography
        run.save_manifest()


def _robots_policy(run, source):
    artifact, evidence = net.get('www.pangasinan.gov.ph', '/robots.txt', accept='text/plain')
    run.add_evidence(source, 'robots.txt', artifact, role='robots', **evidence)
    if evidence['http_status'] != 200 or not (evidence['content_type'] or '').startswith('text/plain'):
        raise net.FetchError('robots_unavailable')
    parser = RobotFileParser()
    parser.parse(artifact.decode('utf8', 'replace').splitlines())
    return parser


def _browser_capture(run, source, ip, paths, delay):
    """Run the Playwright worker for fixed same-origin paths and record its evidence."""
    scratch = Path(tempfile.mkdtemp(dir=run.path))
    try:
        job = {'origin': PROVINCE_ORIGIN, 'ip': ip, 'out_dir': str(scratch), 'delay_ms': int(delay * 1000),
               'paths': [{'key': k, 'path': p} for k, p in paths]}
        proc = subprocess.run(['node', str(Path(__file__).with_name('browser.cjs'))], input=json.dumps(job),
                              capture_output=True, text=True, timeout=60 + len(paths) * (delay + 30), cwd=ROOT)
        report = json.loads(proc.stdout or '{}')
        run.manifest.setdefault('browser', {}).setdefault(source, []).append({
            'browser_version': report.get('browser_version'), 'requests': report.get('requests'),
            'pinned_ip': ip, 'pages': len(paths), 'error': report.get('error')})
        captured = []
        for page in report.get('pages', []):
            meta = {'agency': 'Provincial Government of Pangasinan', 'source_url': page['url'],
                    'final_url': page.get('final_url'), 'retrieved_at': page['retrieved_at'],
                    'http_status': page.get('http_status'), 'content_type': page.get('content_type'),
                    'peer_ip': page.get('peer_ip'), 'page': page['key'], 'collection_method': 'visible_chrome'}
            for kind in ('raw', 'rendered', 'extracted'):
                if page.get(kind):
                    data = (scratch / page[kind]['file']).read_bytes()
                    if sha256(data) != page[kind]['sha256']:
                        raise net.FetchError('browser_artifact_changed')
                    run.add_evidence(source, page[kind]['file'], data, role=kind, **meta)
                    if kind == 'extracted' and page['status'] == 'captured':
                        captured.append((page['key'], json.loads(data)))
            if page['status'] != 'captured':
                run.record_error(source, 'browser', page.get('error', 'failed'), page=page['key'])
        if report.get('error') or proc.returncode:
            raise net.FetchError((report.get('error') or f'browser_exit_{proc.returncode}')[:120])
        return dict(captured)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def collect_province_site(run, options):
    source = 'pangasinan-gov'
    keys = options.get('pages') or DEFAULT_PAGES
    if set(keys) - set(PROVINCE_PAGES):
        raise net.FetchError('unknown_page')
    robots = _robots_policy(run, source)
    delay = float(robots.crawl_delay(net.USER_AGENT) or 3)
    if delay > 30:
        raise net.FetchError('robots_crawl_delay_too_long')

    def permitted(paths):
        ok = [(k, p) for k, p in paths if robots.can_fetch(net.USER_AGENT, PROVINCE_ORIGIN + p)]
        for key, _ in set(paths) - set(ok):
            run.record_error(source, 'robots', 'robots_disallowed', page=key)
        return ok

    paths = permitted([(k, PROVINCE_PAGES[k]) for k in keys])
    if not paths:
        raise net.FetchError('robots_denied_all')
    ip = next(a for a in net.public_addresses('www.pangasinan.gov.ph') if ':' not in a)
    pages = _browser_capture(run, source, ip, paths, delay)
    limit = options.get('lgu_limit')
    if 'lgus' not in pages or limit == 0:
        return
    slugs = list(dict.fromkeys(m[1] for link in pages['lgus']['links'] if (m := LGU_LINK.match(link['href']))))
    run.manifest.setdefault('discovered', {})['pangasinan_gov_lgu_pages'] = len(slugs)
    if len(slugs) > MAX_LGU_PAGES:
        raise net.FetchError('lgu_page_limit')
    detail = permitted([(f'lgu-{slug}', f'/city-municipalities/{slug}/') for slug in slugs[:limit]])
    if detail:
        _browser_capture(run, source, ip, detail, delay)


SOURCES = {
    'psa-psgc': {'collect': collect_psa, 'agency': 'Philippine Statistics Authority',
                 'description': 'PSGC Classification API: geography, hierarchy, income class, population'},
    'pangasinan-gov': {'collect': collect_province_site, 'agency': 'Provincial Government of Pangasinan',
                       'description': 'pangasinan.gov.ph about, geography, LGU list and 48 LGU pages (visible Chrome)'},
}
