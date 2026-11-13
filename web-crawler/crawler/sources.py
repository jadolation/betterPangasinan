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
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from . import net
from .runs import ROOT, STAGING, sha256

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


def _browser_capture(run, source, ip, paths, delay, origin=PROVINCE_ORIGIN,
                     agency='Provincial Government of Pangasinan', record_failures=True):
    """Run the Playwright worker for fixed same-origin paths and record its evidence.
    Returns {key: extracted page} for captured pages and {key: error} for failed ones."""
    scratch = Path(tempfile.mkdtemp(dir=run.path))
    try:
        job = {'origin': origin, 'ip': ip, 'out_dir': str(scratch), 'delay_ms': int(delay * 1000),
               'paths': [{'key': k, 'path': p} for k, p in paths]}
        proc = subprocess.run(['node', str(Path(__file__).with_name('browser.cjs'))], input=json.dumps(job),
                              capture_output=True, text=True, timeout=60 + len(paths) * (delay + 30), cwd=ROOT)
        report = json.loads(proc.stdout or '{}')
        run.manifest.setdefault('browser', {}).setdefault(source, []).append({
            'browser_version': report.get('browser_version'), 'requests': report.get('requests'),
            'origin': origin, 'pinned_ip': ip, 'pages': len(paths), 'error': report.get('error')})
        captured, failed = [], {}
        for page in report.get('pages', []):
            meta = {'agency': agency, 'source_url': page['url'],
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
                failed[page['key']] = page.get('error', 'failed')
                if record_failures:
                    run.record_error(source, 'browser', failed[page['key']], page=page['key'])
        if report.get('error') or proc.returncode:
            raise net.FetchError((report.get('error') or f'browser_exit_{proc.returncode}')[:120])
        return dict(captured), failed
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
    pages, _ = _browser_capture(run, source, ip, paths, delay)
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


LGU_SITE = re.compile(r'^https?://((?:[a-z0-9-]+\.)+gov\.ph)/?$')
LGU_SITE_DELAY = 3


def lgu_websites(run):
    """{slug: url} for WEBSITE links on captured provincial LGU pages (same run)."""
    sites = {}
    for entry in run.evidence('pangasinan-gov', role='extracted'):
        if entry['page'].startswith('lgu-'):
            links = {a['href'] for a in json.loads(run.read(entry))['links'] if a['text'].strip().upper() == 'WEBSITE'}
            if len(links) == 1:
                sites[entry['page'][4:]] = links.pop()
    return sites


def collect_lgu_sites(run, options):
    """For each .gov.ph site linked from the provincial LGU pages: robots.txt, homepage,
    then the same-site Contact page, all in visible Chrome. One site failing does not
    stop the others; every skip and failure is recorded."""
    source = 'lgu-sites'
    sites = lgu_websites(run)
    if not sites:
        raise net.FetchError('requires_pangasinan_gov_lgu_pages_in_same_run')
    for slug, url in sorted(sites.items())[:options.get('lgu_limit')]:
        match = LGU_SITE.match(url)
        if not match:
            run.record_error(source, 'scope', 'not_a_gov_ph_root_url', page=slug, url=url)
            continue
        host = match[1]
        variants = [host, host[4:] if host.startswith('www.') else 'www.' + host]
        try:
            statuses = []
            for suffix, host in zip(('', '-alt'), variants):  # sites often serve only www or only bare host
                origin, key = f'https://{host}', f'{slug}-robots{suffix}'
                try:
                    ip = next(a for a in net.public_addresses(host) if ':' not in a)
                except (OSError, StopIteration) as error:
                    statuses.append(f'{host}:dns_{type(error).__name__}')
                    continue
                robots_pages, robots_failed = _browser_capture(
                    run, source, ip, [(key, '/robots.txt')], LGU_SITE_DELAY, origin,
                    agency=f'LGU website ({host})', record_failures=False)
                status = robots_failed.get(key)
                statuses.append(f'{host}:{status}')
                if status in (None, 'http_404'):
                    break
            else:
                run.record_error(source, 'robots', 'robots_unavailable', page=slug, attempts=statuses)
                continue
            robots = RobotFileParser()
            robots.parse((robots_pages.get(key, {}).get('text') or '').splitlines() if status is None else [])
            if not robots.can_fetch(net.USER_AGENT, origin + '/'):
                run.record_error(source, 'robots', 'robots_disallowed', page=slug)
                continue
            pages, _ = _browser_capture(run, source, ip, [(f'{slug}-home', '/')], LGU_SITE_DELAY, origin,
                                        agency=f'LGU website ({host})')
            home = pages.get(f'{slug}-home')
            contact = sorted({urlsplit(a['href']).path for a in (home or {}).get('links', [])
                              if a['href'] and urlsplit(a['href']).netloc == host
                              and urlsplit(a['href']).path not in ('', '/')  # in-page anchors: home covers them
                              and 'contact' in (a['href'] + ' ' + a['text']).lower()})
            if not contact:
                run.record_error(source, 'discover', 'no_contact_link', page=slug)
                continue
            path = contact[0]
            if not robots.can_fetch(net.USER_AGENT, origin + path):
                run.record_error(source, 'robots', 'robots_disallowed', page=f'{slug}-contact')
                continue
            run.manifest.setdefault('discovered', {}).setdefault('lgu_contact_pages', {})[slug] = origin + path
            _browser_capture(run, source, ip, [(f'{slug}-contact', path)], LGU_SITE_DELAY, origin,
                             agency=f'LGU website ({host})')
        except (net.FetchError, StopIteration, OSError) as error:
            run.record_error(source, 'site', str(error) or type(error).__name__, page=slug)


OSM_HOST = 'download.geofabrik.de'
OSM_LATEST = '/asia/philippines-latest.osm.pbf'
OSM_DATED = re.compile(r'^https://download\.geofabrik\.de/asia/(philippines-[0-9]{6}\.osm\.pbf)$')
OSM_MAX_BYTES = 1_500_000_000


def osm_extract_file(run, options):
    """Resolve and cache the dated Geofabrik extract; returns its local path."""
    source = 'osm-geofabrik'
    _, redirect = net.get(OSM_HOST, OSM_LATEST, accept='*/*', max_bytes=10_000)
    match = OSM_DATED.match(redirect.get('location') or '')
    if redirect['http_status'] not in (301, 302, 303, 307, 308) or not match:
        raise net.FetchError('geofabrik_latest_not_resolved')
    name = match[1]
    md5_body, md5_meta = net.get(OSM_HOST, f'/asia/{name}.md5', accept='text/plain', max_bytes=1000)
    run.add_evidence(source, f'{name}.md5', md5_body, role='checksum', agency='Geofabrik (OpenStreetMap data)',
                     license='ODbL 1.0, (c) OpenStreetMap contributors', resolved_from=OSM_HOST + OSM_LATEST,
                     **md5_meta)
    expected_md5 = md5_body.decode().split()[0]
    cache = STAGING / 'cache'
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / name
    if not path.exists():
        meta = net.download(OSM_HOST, f'/asia/{name}', path, OSM_MAX_BYTES)
        (cache / f'{name}.json').write_text(json.dumps(meta, indent=2))
    import hashlib
    md5 = hashlib.md5()
    with open(path, 'rb') as stream:
        while chunk := stream.read(1 << 20):
            md5.update(chunk)
    if md5.hexdigest() != expected_md5:
        path.rename(path.with_suffix('.pbf.rejected'))
        raise net.FetchError('osm_md5_mismatch')
    return path


OSM_PROVINCE_RELATION = 1504701  # Pangasinan; checked against its ref tag below
OSM_PLACES = ('city', 'town')


def collect_osm(run, options):
    """Extract from the cached Geofabrik file: the Pangasinan province relation with its
    boundary way geometry, its subarea relations, and every city/town place node in the
    province bounding box. Matching to PSGC happens offline in build.py."""
    import osmium
    path = osm_extract_file(run, options)
    province, subareas = None, {}
    for rel in osmium.FileProcessor(str(path), osmium.osm.RELATION):
        if rel.id == OSM_PROVINCE_RELATION:
            province = {'id': rel.id, 'tags': dict(rel.tags),
                        'members': [{'type': m.type, 'ref': m.ref, 'role': m.role} for m in rel.members]}
    if not province or province['tags'].get('ref') != '0105500000':
        raise net.FetchError('osm_province_relation_changed')
    sub_ids = {m['ref'] for m in province['members'] if m['role'] == 'subarea' and m['type'] == 'r'}
    for rel in osmium.FileProcessor(str(path), osmium.osm.RELATION):
        if rel.id in sub_ids:
            subareas[rel.id] = {'id': rel.id, 'tags': dict(rel.tags)}
    way_ids = {m['ref'] for m in province['members'] if m['type'] == 'w' and m['role'] in ('outer', 'inner', '')}
    ways = {}
    for way in osmium.FileProcessor(str(path), osmium.osm.WAY):
        if way.id in way_ids:
            ways[way.id] = [n.ref for n in way.nodes]
    needed = {n for refs in ways.values() for n in refs}
    coords, places = {}, []
    for node in osmium.FileProcessor(str(path), osmium.osm.NODE):
        if node.id in needed:
            coords[node.id] = (node.location.lon, node.location.lat)
        if node.tags.get('place') in OSM_PLACES:
            places.append({'id': node.id, 'lat': node.location.lat, 'lon': node.location.lon,
                           'tags': {k: v for k, v in node.tags
                                    if k in ('name', 'place', 'ref', 'old_ref', 'wikidata') or k.startswith('is_in')}})
    if missing := sorted(n for n in needed if n not in coords):
        raise net.FetchError(f'osm_boundary_nodes_missing:{len(missing)}')
    lons = [c[0] for c in coords.values()]
    lats = [c[1] for c in coords.values()]
    places = [p for p in places if min(lats) <= p['lat'] <= max(lats) and min(lons) <= p['lon'] <= max(lons)]
    body = json.dumps({
        'extract': path.name, 'province': province,
        'boundary_ways': [{'id': w, 'role': next(m['role'] for m in province['members'] if m['ref'] == w),
                           'coords': [coords[n] for n in ways[w]]} for w in sorted(ways)],
        'subareas': [subareas[r] for r in sorted(subareas)],
        'places': sorted(places, key=lambda p: p['id']),
    }, ensure_ascii=False).encode()
    cache_meta = json.loads((path.parent / f'{path.name}.json').read_text())
    run.add_evidence('osm-geofabrik', 'pangasinan-osm.json', body, role='extract',
                     agency='Geofabrik (OpenStreetMap data)', license='ODbL 1.0, (c) OpenStreetMap contributors',
                     official_source=False, title=f'Pangasinan boundary and places from {path.name}',
                     **{k: cache_meta[k] for k in ('source_url', 'retrieved_at', 'http_status', 'response_sha256',
                                                   'last_modified')})

SOURCES = {
    'psa-psgc': {'collect': collect_psa, 'agency': 'Philippine Statistics Authority',
                 'description': 'PSGC Classification API: geography, hierarchy, income class, population'},
    'pangasinan-gov': {'collect': collect_province_site, 'agency': 'Provincial Government of Pangasinan',
                       'description': 'pangasinan.gov.ph about, geography, LGU list and 48 LGU pages (visible Chrome)'},
    'lgu-sites': {'collect': collect_lgu_sites, 'agency': 'City and municipal governments',
                  'description': 'Contact pages of .gov.ph LGU sites linked from pangasinan.gov.ph (visible Chrome)'},
    'osm-geofabrik': {'collect': collect_osm, 'agency': 'OpenStreetMap contributors via Geofabrik (not official)',
                      'description': 'Dated Philippines extract (cached, md5-checked): LGU seat/label coordinates'},
}
