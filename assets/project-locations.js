/* Source coordinates are displayed unchanged. No geocoding, snapping or tile requests. */
(() => {
  'use strict';
  const root = document.getElementById('project-locations');
  if (!root) return;
  const $ = id => document.getElementById(id), form = $('pl-filters');
  const node = (tag, text, parent) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (parent) parent.append(el); return el; };
  const point = p => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite) && Math.abs(p[0]) <= 180 && Math.abs(p[1]) <= 90;
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const words = value => String(value ?? 'Unknown').replaceAll('_', ' ');
  const statusLabel = value => ({ plausible: 'Geographically plausible', suspicious: 'Suspicious location', outside_pangasinan: 'Outside Pangasinan', name_match_elsewhere: 'Outside Pangasinan - search match', unavailable: 'Location unavailable', needs_review: 'Needs review' })[value] || words(value);
  const flags = p => [...new Set([...(p.location_flags || []), ...p.segments.flatMap(s => s.flags || [])])].filter(flag => flag !== 'inside_province');
  const needsReview = p => ['suspicious', 'needs_review'].includes(p.display_status) || flags(p).some(flag => ['municipality_mismatch', 'identical_endpoints', 'invalid_or_missing_coordinate_pair', 'endpoint_distance_over_200km_review'].includes(flag));
  const money = value => value === null || value === undefined ? 'Unknown (not zero)' : typeof value === 'number' && Number.isSafeInteger(value) ? new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP', maximumFractionDigits: 0 }).format(value) : 'Unavailable: invalid published amount';
  const link = (url, label, parent) => { try { const target = new URL(url); if (target.protocol !== 'https:' || target.username || target.password) return; const a = node('a', label, parent); a.href = target.href; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a; } catch { /* Invalid source links remain excluded, never interpreted as markup. */ } };
  async function load(url, raw = false) { const r = await fetch(url); if (!r.ok) throw Error(`Unavailable source: ${url}`); return raw ? r.text() : r.json(); }
  async function hash(text) { if (!crypto.subtle) throw Error('Source verification requires a secure browser context.'); return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))), n => n.toString(16).padStart(2, '0')).join(''); }
  let projects = [], filtered = [], selected = null, page = 0, map, overview, layers = new Map();
  if (matchMedia('(max-width:560px)').matches) $('pl-filter-panel').open = false;
  function select(id, fit = true) {
    const p = projects.find(p => p.id === id); if (!p) return;
    selected = id;
    const index = filtered.findIndex(p => p.id === id); if (index >= 0) page = Math.floor(index / 25);
    const url = new URL(location.href); url.searchParams.set('project', id); history.replaceState(null, '', url);
    renderList(); renderDetail(p);
    const coords = p.segments.flatMap(s => [s.start, s.end]).filter(point);
    if (fit && map && coords.length) map.fitBounds(coords.map(c => [c[1], c[0]]), { padding: [40, 40], maxZoom: 13 });
    for (const [key, group] of layers) group.eachLayer(layer => { if (layer.setStyle) layer.setStyle({ weight: key === id ? 4 : 2 }); });
  }
  function renderDetail(p) {
    const box = $('pl-detail'); box.replaceChildren(); node('h2', p.title, box);
    node('p', `${String(p.dataset).toUpperCase()} | ${statusLabel(p.display_status)}`, box);
    node('p', `Stated province: ${p.stated_province || 'Not supplied'}. Stated municipalities: ${(p.stated_municipalities || []).map(m => m.name || m.psgc).join(', ') || 'Not supplied'}. Stated barangays: ${(p.stated_barangays || []).map(b => typeof b === 'string' ? b : b.name || b.psgc).join(', ') || 'Not supplied'}.`, box);
    node('p', `Proposed national budget (NEP): ${money(p.nep_php)}. House bill (${p.house_stage === 'hgab3' ? 'third reading' : p.house_stage === 'hgab2' ? 'second reading' : 'reading not supplied'}): ${money(p.house_php)}. Comparison: ${words(p.comparison_status)}. These are proposals, not spending.`, box);
    const warnings = flags(p); node('p', warnings.length ? `Review flags: ${warnings.map(words).join('; ')}. These are not findings of fraud.` : 'No location review flags supplied. This is not independent site verification.', box).className = 'pl-warning';
    const valid = p.segments.flatMap(s => [s.start, s.end]).filter(point);
    const go = node('button', 'Go to published location', box); go.type = 'button'; go.disabled = !map || !valid.length; go.addEventListener('click', () => select(p.id));
    if (!valid.length) node('p', 'Location unavailable: no valid published coordinates. No pin has been invented.', box);
    for (const s of p.segments) {
      node('h3', `Source segment ${s.index}`, box);
      node('p', `Source versions: ${(s.source_versions || []).join(', ') || 'Not supplied'}. Straight endpoint distance: ${s.distance_km === null || s.distance_km === undefined ? 'Unavailable' : `${s.distance_km} km`}.`, box);
      for (const endpoint of ['start', 'end']) {
         const coord = s[endpoint], line = node('p', `${endpoint === 'start' ? 'Start' : 'End'}: ${point(coord) ? `longitude ${coord[0]}, latitude ${coord[1]}` : 'No valid coordinate'}`, box); line.className = 'pl-coordinate';
        if (point(coord)) { node('span', ' | ', line); link(`https://www.openstreetmap.org/?mlat=${coord[1]}&mlon=${coord[0]}#map=13/${coord[1]}/${coord[0]}`, 'Open exact coordinate in OpenStreetMap', line); }
         const raw = node('details', undefined, box); node('summary', `Original ${endpoint} values`, raw); node('pre', JSON.stringify(s[`${endpoint}_raw`] ?? null, null, 2), raw);
      }
      node('p', `Segment flags: ${(s.flags || []).map(words).join('; ') || 'None supplied'}`, box);
      if (s.evidence) { const details = node('details', undefined, box); node('summary', 'Original segment evidence and source fields', details); node('pre', JSON.stringify(s.evidence, null, 2), details); }
    }
    node('h3', 'Original source documents', box);
    const sources = p.source_links || [];
    const entries = Array.isArray(sources) ? sources.map((s, i) => [String(i + 1), s]) : Object.entries(sources);
    let sourceCount = 0;
    const documentLabels = { nep: 'Proposed national budget PDF (NEP)', hgab2: 'House bill PDF: second reading', hgab3: 'House bill PDF: third reading' };
    for (const [key, s] of entries) { const url = typeof s === 'string' ? s : s?.url || s?.href; if (url) { const line = node('p', undefined, box); if (link(url, typeof s === 'string' ? documentLabels[key] || words(key) : s.label || s.title || words(key), line)) sourceCount++; } }
    if (!sourceCount) node('p', 'No valid HTTPS original document link was supplied.', box);
    const original = p.source_fields?.upstream;
    const references = node('p', undefined, box);
    link(original?.url, 'Original BetterGov project', references);
    if (typeof p.upstream_id === 'string' && ['dpwh', 'fmr', 'hfep', 'nia'].includes(p.dataset)) {
      references.append(document.createTextNode(' / '));
      link(`https://budget.bettergov.ph/api/v1/hgab/2027/datasets/${p.dataset}/projects/${encodeURIComponent(p.upstream_id)}`, 'Project detail API', references);
    }
    node('p', `Source snapshot: ${p.source_snapshot || 'See publication manifest'}. Document pages: NEP ${original?.nep_page ?? 'not supplied'}; applicable House reading ${original?.[`${p.house_stage}_page`] ?? 'not supplied'}.`, box);
    if (p.source_fields) { const details = node('details', undefined, box); node('summary', 'Dataset metadata and original project fields', details); node('pre', JSON.stringify(p.source_fields, null, 2), details); }
  }
  function renderList() {
    const list = $('pl-list'); list.replaceChildren();
    for (const p of filtered.slice(page * 25, (page + 1) * 25)) {
      const card = node('article', undefined, list); card.className = 'pl-card'; card.setAttribute('aria-current', String(p.id === selected)); card.dataset.projectId = p.id;
      const button = node('button', p.title, card); button.type = 'button'; button.addEventListener('click', () => select(p.id));
      node('p', `${String(p.dataset).toUpperCase()} | ${statusLabel(p.display_status)} | ${words(p.comparison_status)}`, card);
      node('p', (p.stated_municipalities || []).map(m => m.name || m.psgc).join(', ') || 'Stated municipality unavailable', card);
      if (!p.segments.some(s => point(s.start) || point(s.end))) node('p', 'Location unavailable: no valid published coordinates.', card);
      if (flags(p).length) node('p', `Review: ${flags(p).map(words).join('; ')}`, card).className = 'pl-warning';
    }
    if (!filtered.length) node('p', 'No projects match these filters. No coordinates are inferred.', list);
    $('pl-page').textContent = `${filtered.length ? page + 1 : 0} / ${Math.ceil(filtered.length / 25)}`;
    $('pl-prev').disabled = page === 0; $('pl-next').disabled = (page + 1) * 25 >= filtered.length;
    $('pl-status').textContent = `${filtered.length} unique projects match; ${projects.length} published projects across all programs. ${filtered.filter(p => p.segments.some(s => point(s.start) || point(s.end))).length} matching projects have valid coordinates. Offscreen source locations remain mapped. Page size: 25.`;
  }
  function filter() {
    const f = Object.fromEntries(new FormData(form)), q = (f.query || '').trim().toLowerCase(); page = 0;
    filtered = projects.filter(p => (!f.dataset || p.dataset === f.dataset) && (!f.status || p.display_status === f.status || (f.status === 'outside_pangasinan' && (p.location_flags || []).includes('outside_province'))) && (!f.comparison || p.comparison_status === f.comparison) && (!f.municipality || p.stated_municipalities.some(m => (m.psgc || m.name) === f.municipality)) && (!f.suspicious || needsReview(p)) && (!q || `${p.title} ${p.id}`.toLowerCase().includes(q)));
    const ids = new Set(filtered.map(p => p.id));
    if (selected && !ids.has(selected)) {
      selected = null;
      $('pl-detail').replaceChildren(); node('h2', 'Project evidence', $('pl-detail'));
      node('p', 'The selected project is outside these filters. Choose a matching project to inspect its published location.', $('pl-detail'));
      const url = new URL(location.href); url.searchParams.delete('project'); history.replaceState(null, '', url);
    }
    const totals = [['Geographically plausible', filtered.filter(p => p.display_status === 'plausible').length], ['Suspicious location', filtered.filter(p => p.display_status === 'suspicious').length], ['No usable coordinates', filtered.filter(p => !p.segments.some(s => point(s.start) || point(s.end))).length]];
    $('pl-summary').replaceChildren();
    for (const [label, value] of totals) { const card = node('div', undefined, $('pl-summary')); node('strong', String(value), card); node('span', label, card); }
    if (map) for (const [id, group] of layers) { if (ids.has(id)) group.addTo(map); else group.remove(); }
    renderList();
  }
  function addOptions(name, values) { const select = form.elements.namedItem(name); for (const [value, label] of values) { if (![...select.options].some(o => o.value === value)) { const option = node('option', label, select); option.value = value; } } }
  async function init() {
    const [summary, coordinateText, manifest, boundaryText] = await Promise.all([load('data/project-locations/review-summary.json'), load('data/project-locations/projects.geojson', true), load('data/national-budget/2027/manifest.json'), load('data/geography/municipalities.geojson', true).catch(() => null)]);
    const collection = JSON.parse(coordinateText);
    if (summary.schema_version !== 1 || !summary.snapshot_id || summary.snapshot_id !== manifest.snapshot_id || summary.source_hashes?.projects !== manifest.files?.['projects.json'] || (boundaryText !== null && summary.source_hashes?.municipalities !== await hash(boundaryText))) throw Error('Location sources do not match the published snapshot or reference boundaries.');
    if (!Array.isArray(summary.projects) || collection.type !== 'FeatureCollection' || !Array.isArray(collection.features)) throw Error('Invalid location evidence format.');
    if (summary.files?.['projects.geojson'] && summary.files['projects.geojson'] !== await hash(coordinateText)) throw Error('Coordinate file checksum mismatch.');
    if (collection.snapshot_id && collection.snapshot_id !== summary.snapshot_id) throw Error('Coordinate snapshot mismatch.');
    if (collection.source_hashes && !same(collection.source_hashes, summary.source_hashes)) throw Error('Coordinate source hashes mismatch.');
    const ids = new Map();
    for (const p of summary.projects) {
      if (typeof p.id !== 'string' || ids.has(p.id) || typeof p.title !== 'string' || !Array.isArray(p.segments) || !Array.isArray(p.stated_municipalities)) throw Error('Invalid or duplicate project evidence.');
      const indexes = new Set();
      for (const s of p.segments) { if (!s || !Number.isInteger(s.index) || indexes.has(s.index)) throw Error('Invalid or duplicate source segment.'); indexes.add(s.index); }
      ids.set(p.id, p);
    }
    const expected = new Map();
    const key = (id, index, type, endpoint) => JSON.stringify([id, index, type, endpoint]);
    for (const p of summary.projects) for (const s of p.segments) {
      for (const endpoint of ['start', 'end']) if (point(s[endpoint])) expected.set(key(p.id, s.index, 'Point', endpoint), s[endpoint]);
      if (point(s.start) && point(s.end)) expected.set(key(p.id, s.index, 'LineString', undefined), [s.start, s.end]);
    }
    const seen = new Set();
    for (const f of collection.features) {
      const g = f.geometry, props = f.properties || {}, p = ids.get(props.project_id), s = p?.segments.find(s => s.index === props.segment_index);
      if (!s || !g || !['Point', 'LineString'].includes(g.type)) throw Error('Unmatched source coordinate.');
      let endpoint = props.endpoint;
      if (g.type === 'Point' && endpoint === 'point') endpoint = same(g.coordinates, s.start) ? 'start' : 'end';
      const k = key(p.id, s.index, g.type, g.type === 'Point' ? endpoint : undefined);
      if (!expected.has(k) || seen.has(k) || !same(expected.get(k), g.coordinates)) throw Error('Coordinate content differs from source evidence.');
      seen.add(k);
    }
    if (seen.size !== expected.size) throw Error('Published coordinate features are incomplete.');
    projects = summary.projects;
    addOptions('dataset', [...new Set(projects.map(p => p.dataset))].sort().map(s => [s, String(s).toUpperCase()]));
    addOptions('status', ['plausible', 'suspicious', 'outside_pangasinan', 'name_match_elsewhere', 'unavailable', 'needs_review'].map(value => [value, statusLabel(value)]));
    addOptions('comparison', [...new Set(projects.map(p => p.comparison_status).filter(Boolean))].sort().map(value => [value, words(value)]));
    const municipalities = new Map(projects.flatMap(p => p.stated_municipalities.map(m => [m.psgc || m.name, m.name || m.psgc]))); addOptions('municipality', [...municipalities].sort((a, b) => a[1].localeCompare(b[1])));
    node('p', `Snapshot: ${summary.snapshot_id}. Projects SHA-256: ${summary.source_hashes.projects}. Municipalities SHA-256: ${summary.source_hashes.municipalities}.`, $('pl-sources'));
    node('pre', `Policy: ${JSON.stringify(summary.policy, null, 2)}\nPublished counts: ${JSON.stringify(summary.counts, null, 2)}`, $('pl-sources'));
    if (typeof manifest.notice === 'string') node('p', manifest.notice, $('pl-sources'));
    for (const notice of Array.isArray(manifest.disclaimers) ? manifest.disclaimers : []) {
      if (typeof notice === 'string') node('p', notice, $('pl-sources'));
      else if (typeof notice?.body === 'string') node('p', notice.body, $('pl-sources'));
    }
    if (window.L && boundaryText !== null) {
      map = L.map('pl-map', { crs: L.CRS.EPSG4326, minZoom: 0, maxZoom: 18 });
      map.attributionControl.addAttribution('Source coordinates unchanged | Simplified municipal reference boundaries');
      const boundaries = L.geoJSON(JSON.parse(boundaryText), { style: { color: '#01407F', weight: 1, fillColor: '#eaf2fc', fillOpacity: .6 } }).addTo(map);
      overview = boundaries.getBounds(); map.fitBounds(overview, { padding: [15, 15] });
      boundaries.eachLayer(layer => { const label = layer.feature.properties.name; if (label) { const text = node('span', String(label)); layer.bindTooltip(text, { sticky: true }); } });
      for (let lat = -90; lat <= 90; lat += 10) L.polyline([[lat, -180], [lat, 180]], { interactive: false, color: '#78949f', weight: 1, opacity: .2 }).addTo(map);
      for (let lon = -180; lon <= 180; lon += 10) { L.polyline([[-90, lon], [90, lon]], { interactive: false, color: '#78949f', weight: 1, opacity: .2 }).addTo(map); for (let lat = -80; lat <= 80; lat += 20) L.marker([lat, lon], { interactive: false, icon: L.divIcon({ className: 'pl-grid-label', html: `${lat}, ${lon}`, iconSize: [65, 12] }) }).addTo(map); }
      for (const p of projects) layers.set(p.id, L.featureGroup().addTo(map));
      for (const f of collection.features) {
        const g = f.geometry, prop = f.properties, p = ids.get(prop.project_id), group = layers.get(p.id);
        const warning = needsReview(p);
        const layer = g.type === 'Point' ? L.circleMarker([g.coordinates[1], g.coordinates[0]], { radius: prop.endpoint === 'end' ? 5 : 7, color: warning ? '#976300' : '#01407F', fillColor: prop.endpoint === 'end' ? '#FBC711' : '#01407F', fillOpacity: .8, weight: warning ? 3 : 2, className: 'pl-map-endpoint' }) : L.polyline(g.coordinates.map(c => [c[1], c[0]]), { color: warning ? '#976300' : '#01407F', dashArray: '6 6', weight: 2 });
        const tip = document.createElement('span'); tip.textContent = `${warning ? '[!] ' : ''}${statusLabel(p.display_status)}: ${p.title}: ${g.type === 'Point' ? prop.endpoint : 'straight source connection'}`; layer.bindTooltip(tip); layer.on('click', () => select(p.id));
        if (g.type === 'Point') layer.on('add', () => { const el = layer.getElement(); el.setAttribute('tabindex', '0'); el.setAttribute('role', 'button'); el.setAttribute('aria-label', tip.textContent); el.dataset.projectId = p.id; el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(p.id); } }); });
        layer.addTo(group);
      }
      root.dataset.mapReady = 'true';
    } else { $('pl-map').hidden = true; $('pl-map-status').textContent = `${!window.L ? 'Map library unavailable.' : 'Local boundary reference unavailable; no geographic overview is inferred.'} Project evidence matched to the published snapshot, exact coordinates and source links remain available below.`; }
    form.addEventListener('input', filter); form.addEventListener('submit', e => e.preventDefault());
    $('pl-prev').addEventListener('click', () => { page--; renderList(); }); $('pl-next').addEventListener('click', () => { page++; renderList(); });
    $('pl-overview').addEventListener('click', () => { if (map) map.fitBounds(overview, { padding: [15, 15] }); });
    $('pl-suspicious').addEventListener('click', () => { form.elements.status.value = 'suspicious'; form.elements.suspicious.checked = false; filter(); });
    filter();
    const requested = new URLSearchParams(location.search).get('project');
    if (requested && ids.has(requested)) { const p = ids.get(requested); form.elements.dataset.value = p.dataset; filter(); select(requested); }
    root.dataset.ready = 'true';
  }
  init().catch(error => { $('pl-status').textContent = `Published location evidence could not be loaded or verified. ${error.message} No project coordinates are drawn.`; $('pl-map').hidden = true; $('pl-list').replaceChildren(); for (const button of root.querySelectorAll('button')) button.disabled = true; $('pl-map-status').textContent = 'Map unavailable. Use the downloadable source files or project registry; locations have not been inferred.'; });
})();
