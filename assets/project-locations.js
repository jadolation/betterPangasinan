/* Source coordinates are unchanged. Background tiles never supply project geometry. */
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
  const needsReview = p => p.display_status !== 'name_match_elsewhere' && (p.display_status === 'suspicious' || flags(p).some(flag => ['stated_province_coordinate_mismatch', 'municipality_mismatch', 'identical_endpoints', 'invalid_or_missing_coordinate_pair', 'endpoint_distance_over_200km_review'].includes(flag)));
  const money = value => value === null || value === undefined ? 'Unknown (not zero)' : typeof value === 'number' && Number.isSafeInteger(value) ? new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP', maximumFractionDigits: 0 }).format(value) : 'Unavailable: invalid published amount';
  const link = (url, label, parent) => { try { const target = new URL(url); if (target.protocol !== 'https:' || target.username || target.password) return; const a = node('a', label, parent); a.href = target.href; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a; } catch { /* Invalid source links remain excluded, never interpreted as markup. */ } };
  async function load(url, raw = false) { const r = await fetch(url); if (!r.ok) throw Error(`Unavailable source: ${url}`); return raw ? r.text() : r.json(); }
  async function hash(text) { if (!crypto.subtle) throw Error('Source verification requires a secure browser context.'); return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))), n => n.toString(16).padStart(2, '0')).join(''); }
  const mercatorLimit = 85.0511287798;
  const programNames = { fmr: 'Farm-to-market roads', dpwh: 'Public works and infrastructure', hfep: 'Health facilities', nia: 'Irrigation' };
  const programKey = p => ['fmr', 'dpwh'].includes(p.dataset) ? p.dataset : 'other';
  let projects = [], filtered = [], selected = null, page = 0, map, overview, layers = new Map();
  let sourceCollection, boundaryCollection, activeSegment = 0, globalInspection = false, osmLayer = null, boundaryLayer = null;
  let programLayers = {}, previousBasemap = 'osm', tileFailed = false, boundaryAvailable = false;
  const canPlot = pair => point(pair) && (globalInspection || Math.abs(pair[1]) <= mercatorLimit);
  if (matchMedia('(max-width:560px)').matches) $('pl-filter-panel').open = false;
  function navigate(pairOrPairs) {
    if (!map) return;
    const coords = pairOrPairs.filter(point);
    if (!coords.length || coords.some(pair => !canPlot(pair))) return;
    map.fitBounds(coords.map(pair => [pair[1], pair[0]]), { padding: [35, 35], maxZoom: 13, animate: false });
  }
  function select(id, fit = true, segmentIndex = null) {
    const p = projects.find(p => p.id === id); if (!p) return;
    selected = id;
    activeSegment = segmentIndex ?? p.segments.find(s => point(s.start) || point(s.end))?.index ?? 0;
    const layerControl = $(`pl-layer-${programKey(p)}`); if (layerControl) layerControl.checked = true;
    if (needsReview(p)) $('pl-layer-warnings').checked = true;
    applyVisibility();
    const index = filtered.findIndex(p => p.id === id); if (index >= 0) page = Math.floor(index / 25);
    const url = new URL(location.href); url.searchParams.set('project', id); history.replaceState(null, '', url);
    renderList(); renderDetail(p);
    const segment = p.segments.find(s => s.index === activeSegment);
    if (fit && segment) navigate([point(segment.start) ? segment.start : segment.end]);
    for (const [key, group] of layers) group.eachLayer(layer => { if (layer.setStyle) layer.setStyle({ weight: key === id ? 4 : 2 }); });
  }
  function renderDetail(p) {
    const box = $('pl-detail'); box.replaceChildren(); node('h2', p.title, box);
    if (p.title.length > 100) { const full = node('details', undefined, box); node('summary', 'Full project title', full); node('p', p.title, full); }
    node('p', programNames[p.dataset] || 'Other published program', box).className = 'pl-program';
    node('p', statusLabel(p.display_status), box).className = 'pl-assessment';
    const explanations = { suspicious: "The published coordinates do not match the project's stated area. They are shown unchanged.", name_match_elsewhere: 'The source names a place outside Pangasinan; this is a name-based search match, not a confirmed coordinate error.', outside_pangasinan: 'Published coordinates are outside Pangasinan; this alone does not establish an error.', plausible: 'Coordinates agree with the available administrative reference, not an independent survey.', needs_review: 'Some source location details need checking.', unavailable: 'No usable published coordinates are supplied. No pin has been invented.' };
    node('p', explanations[p.display_status] || 'See the geographic assessment details.', box).className = 'pl-warning';
    node('p', `Stated area: ${(p.stated_municipalities || []).map(m => m.name || m.psgc).join(', ') || 'municipality not supplied'}${p.stated_province ? ', ' + p.stated_province : ''}.`, box);
    if (p.stated_barangays?.length) node('p', `Barangay: ${p.stated_barangays.map(value => typeof value === 'string' ? value : value.name || value.raw).join('; ')}`, box);
    const amounts = node('dl', undefined, box); amounts.className = 'pl-budget-pair';
    const reading = p.house_stage === 'hgab3' ? 'third reading' : p.house_stage === 'hgab2' ? 'second reading' : 'reading not supplied';
    for (const [label, value] of [['NEP proposal', p.nep_php], [`House proposal (${reading})`, p.house_php]]) { node('dt', label, amounts); node('dd', money(value), amounts); }
    const segment = p.segments.find(s => s.index === activeSegment);
    const coordinates = node('div', undefined, box); coordinates.className = 'pl-primary-coordinates';
    for (const endpoint of ['start', 'end']) if (segment) node('p', `${endpoint === 'start' ? 'Start' : 'End'}: ${point(segment[endpoint]) ? `longitude ${segment[endpoint][0]}, latitude ${segment[endpoint][1]}` : 'No valid coordinate'}`, coordinates);
    const actions = node('div', undefined, box); actions.className = 'pl-endpoint-actions';
    for (const [label, pairs] of [['View Start', [segment?.start]], ['View End', [segment?.end]], ['View Both', [segment?.start, segment?.end]], ['Go to published location', [point(segment?.start) ? segment.start : segment?.end]]]) {
      const button = node('button', label, actions); button.type = 'button';
      button.disabled = !map || !pairs.every(canPlot); button.addEventListener('click', () => navigate(pairs));
    }
    if (segment?.distance_km > 200) node('p', 'The source endpoints span an unusually large distance. The dashed connection is not a verified route.', box).className = 'pl-warning';
    if (p.segments.some(s => [s.start, s.end].some(pair => point(pair) && !canPlot(pair)))) node('p', 'Some valid source latitudes are outside the Web Mercator basemap range. They are retained in evidence and are not clamped or drawn at a false latitude. Use global-coordinate inspection below the map.', box).className = 'pl-warning';
    const originalLink = node('p', undefined, box); link(p.source_fields?.upstream?.url, 'Open original project', originalLink);
    const coordinateEvidence = node('details', undefined, box); node('summary', `Original coordinates and segments (${p.segments.length})`, coordinateEvidence);
    for (const s of p.segments) {
      node('h3', `Published segment ${s.index + 1}`, coordinateEvidence);
      node('p', `Straight endpoint distance: ${s.distance_km == null ? 'Unavailable' : `${s.distance_km} km`}; not road length.`, coordinateEvidence);
      for (const endpoint of ['start', 'end']) {
         const coord = s[endpoint], line = node('p', `${endpoint === 'start' ? 'Start' : 'End'}: ${point(coord) ? `longitude ${coord[0]}, latitude ${coord[1]}` : 'No valid coordinate'}`, coordinateEvidence); line.className = 'pl-coordinate';
         if (point(coord)) { node('span', ' | ', line); link(`https://www.openstreetmap.org/?mlat=${coord[1]}&mlon=${coord[0]}#map=13/${coord[1]}/${coord[0]}`, 'Open exact coordinate in OpenStreetMap', line); }
         const raw = node('details', undefined, coordinateEvidence); node('summary', `Original ${endpoint} values`, raw); node('pre', JSON.stringify(s[`${endpoint}_raw`] ?? null, null, 2), raw);
      }
      const go = node('button', `View segment ${s.index + 1}`, coordinateEvidence); go.type = 'button'; go.disabled = !map || ![s.start, s.end].filter(point).length || [s.start, s.end].filter(point).some(pair => !canPlot(pair)); go.addEventListener('click', () => { select(p.id, false, s.index); navigate([s.start, s.end].filter(point)); });
      if (p.segments.length > 1) for (const [label, pairs] of [['View Start', [s.start]], ['View End', [s.end]], ['View Both', [s.start, s.end]]]) {
        const action = node('button', `${label} - segment ${s.index + 1}`, coordinateEvidence); action.type = 'button'; action.disabled = !map || !pairs.every(canPlot);
        action.addEventListener('click', () => { select(p.id, false, s.index); navigate(pairs); });
      }
      node('p', `Segment flags: ${(s.flags || []).map(words).join('; ') || 'None supplied'}`, coordinateEvidence);
      if (s.evidence) { const details = node('details', undefined, coordinateEvidence); node('summary', 'Original segment evidence and source fields', details); node('pre', JSON.stringify(s.evidence, null, 2), details); }
    }
    const review = node('details', undefined, box); node('summary', 'Geographic review details', review); node('p', `Review flags: ${flags(p).map(words).join('; ') || 'None supplied'}. These are not findings of fraud.`, review);
    const documents = node('details', undefined, box); node('summary', 'Source documents', documents);
    const sources = p.source_links || [];
    const entries = Array.isArray(sources) ? sources.map((s, i) => [String(i + 1), s]) : Object.entries(sources);
    let sourceCount = 0;
    const documentLabels = { nep: 'Proposed national budget PDF (NEP)', hgab2: 'House bill PDF: second reading', hgab3: 'House bill PDF: third reading' };
    for (const [key, s] of entries) { const url = typeof s === 'string' ? s : s?.url || s?.href; if (url) { const line = node('p', undefined, documents); if (link(url, typeof s === 'string' ? documentLabels[key] || words(key) : s.label || s.title || words(key), line)) sourceCount++; } }
    if (!sourceCount) node('p', 'No valid HTTPS original document link was supplied.', documents);
    const original = p.source_fields?.upstream;
    const references = node('p', undefined, documents);
    link(original?.url, 'Original BetterGov project', references);
    if (typeof p.upstream_id === 'string' && ['dpwh', 'fmr', 'hfep', 'nia'].includes(p.dataset)) {
      references.append(document.createTextNode(' / '));
      link(`https://budget.bettergov.ph/api/v1/hgab/2027/datasets/${p.dataset}/projects/${encodeURIComponent(p.upstream_id)}`, 'Project detail API', references);
    }
    node('p', `Source snapshot: ${p.source_snapshot || 'See publication manifest'}. Document pages: NEP ${original?.nep_page ?? 'not supplied'}; applicable House reading ${original?.[`${p.house_stage}_page`] ?? 'not supplied'}.`, documents);
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
  function applyVisibility() {
    if (!map) return;
    const visible = new Set(filtered.map(p => p.id));
    for (const p of projects) {
      const group = layers.get(p.id), parent = programLayers[programKey(p)];
      if (!group || !parent) continue;
      const show = visible.has(p.id) && (!needsReview(p) || $('pl-layer-warnings').checked);
      if (show && !parent.hasLayer(group)) parent.addLayer(group);
      else if (!show && parent.hasLayer(group)) parent.removeLayer(group);
    }
    for (const key of ['fmr', 'dpwh', 'other']) {
      if ($(`pl-layer-${key}`).checked) programLayers[key].addTo(map);
      else programLayers[key].remove();
    }
    if (boundaryLayer) { if ($('pl-layer-boundaries').checked) boundaryLayer.addTo(map); else boundaryLayer.remove(); }
  }
  function backgroundStatus() {
    if (!map) return;
    const parts = [];
    if (globalInspection) parts.push('Global geographic inspection: exact source latitudes, without remote tiles.');
    else if ($('pl-basemap').value === 'none') parts.push('No remote basemap selected. Local data and source coordinates remain available.');
    else if (tileFailed) parts.push('OpenStreetMap background unavailable. Source markers, connections and available boundaries remain visible.');
    else parts.push('OpenStreetMap background; requests go to the external tile provider.');
    if (!boundaryAvailable) parts.push('Administrative boundaries unavailable; the default overview is an approximate viewport, not a boundary assessment.');
    $('pl-map-status').textContent = parts.join(' ');
  }
  function setBasemap() {
    if (!map) return;
    if (osmLayer) { osmLayer.remove(); osmLayer = null; }
    tileFailed = false;
    if (!globalInspection && $('pl-basemap').value === 'osm') {
      const provider = window.ProjectMapProviders?.osm;
      try {
        const url = new URL(provider.url.replace(/\{[zxy]\}/g, '0'));
        if (url.protocol !== 'https:' || url.username || url.password) throw Error('Invalid provider');
        osmLayer = L.tileLayer(provider.url, { maxZoom: provider.maxZoom, attribution: provider.attribution,
          updateWhenIdle: provider.updateWhenIdle !== false, keepBuffer: provider.keepBuffer ?? 0,
          referrerPolicy: 'strict-origin-when-cross-origin' });
        osmLayer.on('tileerror', () => { tileFailed = true; backgroundStatus(); });
        osmLayer.addTo(map);
      } catch { tileFailed = true; }
    }
    backgroundStatus();
  }
  function createMap() {
    if (!window.L) { $('pl-map').hidden = true; $('pl-map-status').textContent = 'Map library unavailable. Original coordinates and source evidence remain available below.'; return; }
    if (map) map.remove();
    layers = new Map(); boundaryLayer = null;
    map = L.map('pl-map', { crs: globalInspection ? L.CRS.EPSG4326 : L.CRS.EPSG3857, minZoom: globalInspection ? 0 : 2, maxZoom: 19, zoomControl: true });
    map.attributionControl.addAttribution('Published coordinates unchanged | Municipal reference: geoBoundaries / CC BY 3.0 IGO');
    map.createPane('municipalReference').style.zIndex = '350';
    boundaryAvailable = Boolean(boundaryCollection);
    if (boundaryAvailable) {
      try {
        boundaryLayer = L.geoJSON(boundaryCollection, { pane: 'municipalReference', style: { color: '#01407F', weight: 1.2, fillColor: '#EAF2FC', fillOpacity: .03 } });
        boundaryLayer.eachLayer(layer => {
          const properties = layer.feature.properties || {};
          if (properties.name) layer.bindTooltip(node('span', properties.name), { sticky: true });
          layer.on('mouseover', () => layer.setStyle({ weight: 2.2, fillOpacity: .1 }));
          layer.on('mouseout', () => layer.setStyle({ weight: 1.2, fillOpacity: .03 }));
          if (properties.psgc) {
            const info = node('div'); node('strong', properties.name || 'Municipality', info);
            const p = node('p', undefined, info), a = node('a', 'Open LGU profile', p); a.href = `lgu.html?id=${encodeURIComponent('lgu-' + properties.psgc)}`;
            node('p', 'This boundary does not establish a project allocation.', info); layer.bindPopup(info);
          }
        });
        overview = boundaryLayer.getBounds();
      } catch { boundaryAvailable = false; boundaryLayer = null; }
    }
    // Display-only overview, never substituted for any missing project point.
    if (!boundaryAvailable) overview = L.latLngBounds([[15.15, 119.3], [16.8, 121.25]]);
    map.fitBounds(overview, { padding: [15, 15], animate: false });
    programLayers = { fmr: L.layerGroup().addTo(map), dpwh: L.layerGroup().addTo(map), other: L.layerGroup().addTo(map) };
    for (const p of projects) layers.set(p.id, L.featureGroup());
    let unsupported = 0;
    for (const f of sourceCollection.features) {
      const geometry = f.geometry, prop = f.properties, p = projects.find(row => row.id === prop.project_id), group = layers.get(p.id);
      if (geometry.type === 'Point' ? !canPlot(geometry.coordinates) : geometry.coordinates.some(pair => !canPlot(pair))) { unsupported++; continue; }
      const warning = needsReview(p);
      const layer = geometry.type === 'Point' ? L.circleMarker([geometry.coordinates[1], geometry.coordinates[0]], { radius: prop.endpoint === 'end' ? 5 : 7, color: warning ? '#976300' : '#01407F', fillColor: prop.endpoint === 'end' ? '#FBC711' : '#01407F', fillOpacity: .85, weight: warning ? 3 : 2, className: 'pl-map-endpoint' }) : L.polyline(geometry.coordinates.map(pair => [pair[1], pair[0]]), { color: warning ? '#976300' : '#01407F', dashArray: '6 6', weight: 2 });
      const text = node('span', `${warning ? '[!] ' : ''}${statusLabel(p.display_status)}: ${p.title}: ${geometry.type === 'Point' ? prop.endpoint : 'published endpoint connection'}`);
      layer.bindTooltip(text); layer.on('click', () => select(p.id, true, prop.segment_index));
      if (geometry.type === 'Point') layer.on('add', () => {
        const element = layer.getElement(); element.setAttribute('tabindex', '0'); element.setAttribute('role', 'button'); element.setAttribute('aria-label', text.textContent); element.dataset.projectId = p.id;
        element.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(p.id, true, prop.segment_index); } });
      });
      layer.addTo(group);
    }
    $('pl-projection-notice').hidden = !unsupported && !globalInspection;
    $('pl-global-inspect').hidden = !unsupported && !globalInspection;
    $('pl-projection-notice').textContent = globalInspection ? 'Global inspection preserves all valid geographic latitudes. Standard OpenStreetMap tiles are not used in this projection.' : `${unsupported} source coordinate features exceed the Web Mercator latitude range. Their original values are retained; no marker or line is silently clamped. Use exact global-coordinate inspection.`;
    $('pl-global-inspect').textContent = globalInspection ? 'Return to street map projection' : 'Inspect global coordinates without tiles';
    $('pl-basemap').disabled = globalInspection;
    setBasemap(); applyVisibility(); root.dataset.mapReady = 'true';
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
    applyVisibility();
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
    addOptions('dataset', [...new Set(projects.map(p => p.dataset))].sort().map(s => [s, programNames[s] || 'Other published program']));
    addOptions('status', ['plausible', 'suspicious', 'outside_pangasinan', 'name_match_elsewhere', 'unavailable', 'needs_review'].map(value => [value, statusLabel(value)]));
    addOptions('comparison', [...new Set(projects.map(p => p.comparison_status).filter(Boolean))].sort().map(value => [value, words(value)]));
    const municipalities = new Map(projects.flatMap(p => p.stated_municipalities.map(m => [m.psgc || m.name, m.name || m.psgc]))); addOptions('municipality', [...municipalities].sort((a, b) => a[1].localeCompare(b[1])));
    node('p', `Snapshot: ${summary.snapshot_id}. Projects SHA-256: ${summary.source_hashes.projects}. Municipalities SHA-256: ${summary.source_hashes.municipalities}.`, $('pl-sources'));
    node('pre', `Policy: ${JSON.stringify(summary.policy, null, 2)}\nPublished counts: ${JSON.stringify(summary.counts, null, 2)}`, $('pl-sources'));
    node('p', `Source data retrieved: ${manifest.retrieved_at || 'See original publication manifest'}.`, $('pl-sources'));
    if (typeof manifest.notice === 'string') node('p', manifest.notice, $('pl-sources'));
    for (const notice of Array.isArray(manifest.disclaimers) ? manifest.disclaimers : []) {
      if (typeof notice === 'string') node('p', notice, $('pl-sources'));
      else if (typeof notice?.body === 'string') node('p', notice.body, $('pl-sources'));
    }
    sourceCollection = collection;
    try { boundaryCollection = boundaryText === null ? null : JSON.parse(boundaryText); } catch { boundaryCollection = null; }
    createMap();
    form.addEventListener('input', event => { if (event.target.tagName !== 'SELECT') filter(); });
    form.addEventListener('change', event => { if (event.target.tagName === 'SELECT') filter(); });
    form.addEventListener('submit', event => event.preventDefault());
    $('pl-prev').addEventListener('click', () => { page--; renderList(); }); $('pl-next').addEventListener('click', () => { page++; renderList(); });
    $('pl-overview').addEventListener('click', () => { if (map) map.fitBounds(overview, { padding: [15, 15], animate: false }); });
    $('pl-suspicious').addEventListener('click', () => {
      form.elements.dataset.value = ''; form.elements.status.value = ''; form.elements.municipality.value = '';
      form.elements.comparison.value = ''; form.elements.query.value = ''; form.elements.suspicious.checked = true;
      for (const key of ['fmr', 'dpwh', 'other', 'warnings']) $(`pl-layer-${key}`).checked = true;
      filter();
    });
    $('pl-basemap').addEventListener('change', setBasemap);
    for (const id of ['boundaries', 'fmr', 'dpwh', 'other', 'warnings']) $(`pl-layer-${id}`).addEventListener('change', applyVisibility);
    $('pl-reset').addEventListener('click', () => {
      form.reset(); selected = null; page = 0;
      for (const id of ['boundaries', 'fmr', 'dpwh', 'other', 'warnings']) $(`pl-layer-${id}`).checked = true;
      const url = new URL(location.href); url.searchParams.delete('project'); history.replaceState(null, '', url);
      $('pl-detail').replaceChildren(); node('h2', 'Project evidence', $('pl-detail')); node('p', 'Select a project to inspect its published location.', $('pl-detail'));
      filter(); if (map) map.fitBounds(overview, { padding: [15, 15], animate: false });
    });
    $('pl-global-inspect').addEventListener('click', () => {
      if (!globalInspection) previousBasemap = $('pl-basemap').value;
      globalInspection = !globalInspection;
      $('pl-basemap').value = globalInspection ? 'none' : previousBasemap;
      createMap(); if (selected) select(selected, true, activeSegment);
    });
    filter();
    const requested = new URLSearchParams(location.search).get('project');
    if (requested && ids.has(requested)) { const p = ids.get(requested); form.elements.dataset.value = p.dataset; filter(); select(requested); }
    root.dataset.ready = 'true';
  }
  init().catch(error => { $('pl-status').textContent = `Published location evidence could not be loaded or verified. ${error.message} No project coordinates are drawn.`; $('pl-map').hidden = true; $('pl-list').replaceChildren(); for (const button of root.querySelectorAll('button')) button.disabled = true; $('pl-map-status').textContent = 'Map unavailable. Use the downloadable source files or project registry; locations have not been inferred.'; });
})();
