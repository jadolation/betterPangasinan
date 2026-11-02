/* All maps share one local source load and one stable projection. */
(() => {
  'use strict';
  const ns = 'http://www.w3.org/2000/svg', instances = new WeakMap();
  let shared, leadership, sequence = 0;
  function loadLeadership() {
    if (!leadership) leadership = fetch('data/government-leadership.json').then(response => response.ok ? response.json() : null).catch(() => null);
    return leadership;
  }
  function districtData(data, records) {
    if (!data || data.schema_version !== 1 || !Array.isArray(data.officials) || !Array.isArray(data.districts) || data.districts.length !== 6) return null;
    const officials = new Map(data.officials.map(p => [p.id, p])), codes = new Set(), ids = new Set(), numbers = new Set();
    if (officials.size !== data.officials.length) return null;
    for (const d of data.districts) {
      if (!d.id || ids.has(d.id) || !Number.isInteger(d.number) || d.number < 1 || d.number > 6 || numbers.has(d.number) || !d.name || !Array.isArray(d.lgu_psgcs) || !d.lgu_psgcs.length || !Array.isArray(d.board_member_ids) || d.board_member_ids.length !== 2 || new Set(d.board_member_ids).size !== 2) return null;
      ids.add(d.id); numbers.add(d.number);
      for (const code of d.lgu_psgcs) { if (!/^\d{10}$/.test(code) || codes.has(code) || !records.some(p => p.psgc === code)) return null; codes.add(code); }
      const rep = officials.get(d.representative_id), board = d.board_member_ids.map(id => officials.get(id));
      if (!rep || !rep.display_name || !rep.position || rep.district_id !== d.id || rep.role_type !== 'house_representative' || board.some(p => !p || !p.display_name || !p.position || p.district_id !== d.id || p.role_type !== 'board_member')) return null;
    }
    return codes.size === 48 ? { districts: data.districts, officials } : null;
  }
  const profile = p => `lgu.html?id=${encodeURIComponent(p.id)}`;
  const polygons = g => g.type === 'Polygon' ? [g.coordinates] : g.coordinates;
  function load() {
    if (!shared) shared = Promise.all(['data/lgus.json', 'data/geography/municipalities.geojson', 'data/geography/manifest.json'].map(async url => {
      const response = await fetch(url);
      if (!response.ok) throw new Error('Source unavailable');
      return response.json();
    })).then(([registry, collection, manifest]) => {
      const byCode = new Map(registry.map(p => [p.psgc, p]));
      const points = collection.features.flatMap(f => polygons(f.geometry).flat(2));
      if (!points.length) throw new Error('No geometry');
      const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
      const xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys);
      const cosine = Math.cos(16 * Math.PI / 180);
      const scale = Math.min(920 / ((xmax - xmin) * cosine), 620 / (ymax - ymin));
      const left = (960 - (xmax - xmin) * cosine * scale) / 2, top = (660 - (ymax - ymin) * scale) / 2;
      const project = p => `${left + (p[0] - xmin) * cosine * scale},${top + (ymax - p[1]) * scale}`;
      const records = collection.features.map(f => {
        const record = byCode.get(f.properties.psgc);
        if (!record || record.id !== f.properties.id) throw new Error('Unmatched geometry');
        return { ...record, geography: { ...f.properties }, path: polygons(f.geometry).map(poly => poly.map(ring => `M${ring.map(project).join('L')}Z`).join('')).join('') };
      }).sort((a, b) => a.name.localeCompare(b.name));
      return { records, manifest };
    });
    return shared;
  }
  function createMunicipalityMap({ container, mode = 'explorer', selectedPsgc = null, view = 'municipalities', selectedDistrictId = null, onSelect, onPreview } = {}) {
    if (!(container instanceof Element)) throw new TypeError('A map container is required');
    if (instances.has(container)) return instances.get(container);
    if (!['home', 'explorer', 'profile'].includes(mode)) throw new TypeError('Unknown map mode');
    container.classList.add('municipality-map'); container.dataset.mapMode = mode;
    const id = `municipality-map-${++sequence}`;
    const node = (tag, text, parent, attribute) => {
      const el = document.createElement(tag);
      if (text !== undefined) el.textContent = text;
      if (attribute) el.setAttribute(attribute, '');
      if (parent) parent.append(el);
      return el;
    };
    const content = node('div', undefined, container);
    const status = node('p', 'Loading published municipality boundaries.', content, 'data-map-status'); status.setAttribute('role', 'status');
    const toggle = node('div', undefined, content); toggle.className = 'municipality-map-toggle'; toggle.setAttribute('role', 'group'); toggle.setAttribute('aria-label', 'Map view'); toggle.hidden = mode === 'profile';
    const viewButtons = ['municipalities', 'districts'].map(value => { const button = node('button', value === 'districts' ? 'Legislative Districts' : 'Municipalities', toggle); button.type = 'button'; button.dataset.mapView = value; button.addEventListener('click', () => setView(value)); return button; });
    const controls = node('div', undefined, content); controls.className = 'municipality-map-controls';
    const searchLabel = node('label', 'Find a city or municipality', controls); searchLabel.htmlFor = `${id}-search`;
    const search = node('input', undefined, controls, 'data-map-search'); search.id = searchLabel.htmlFor; search.type = 'search'; search.placeholder = 'Search name or PSGC';
    const selectLabel = node('label', 'Choose a community', controls); selectLabel.htmlFor = `${id}-select`;
    const selector = node('select', undefined, controls, 'data-map-select'); selector.id = selectLabel.htmlFor;
    const layout = node('div', undefined, content); layout.className = 'municipality-map-layout';
    const canvas = node('div', undefined, layout); canvas.className = 'municipality-map-canvas';
    const svg = document.createElementNS(ns, 'svg'); svg.setAttribute('viewBox', '0 0 960 660'); svg.setAttribute('preserveAspectRatio', 'xMidYMid meet'); svg.setAttribute('role', 'group'); svg.setAttribute('aria-label', 'Pangasinan boundaries. Activate a boundary to select its community.'); svg.setAttribute('data-map-svg', ''); canvas.append(svg);
    const detail = node('aside', undefined, layout, 'data-map-detail'); detail.setAttribute('aria-live', 'polite');
    const credit = node('p', undefined, content, 'data-map-credit'); credit.className = 'municipality-map-credit';
    const sources = node('details', undefined, content); node('summary', 'Sources and boundary limits', sources);
    node('p', 'Population is a dated 2024 census observation, not a current estimate. Administrative listing and boundary dates describe different sources. Simplified boundaries are not a legal survey.', sources);
    const provenance = node('p', undefined, sources);
    const sourceLink = node('a', 'Read source dates, releases and hashes', sources); sourceLink.href = 'data/geography/manifest.json';
    const alternative = node('details', undefined, content); node('summary', 'Text alternative: all community profiles', alternative);
    const list = node('ul', undefined, alternative, 'data-map-list');
    let records = [], selected = selectedPsgc, districtSelected = selectedDistrictId, hovered = null, focused = null, destroyed = false, rendered, canonical = null;
    view = view === 'districts' ? 'districts' : 'municipalities';
    const boundaries = new Map();
    const districtFor = code => canonical?.districts.find(d => d.lgu_psgcs.includes(code));
    function officialLinks(d, parent) {
      for (const id of [d.representative_id, ...d.board_member_ids]) {
        const official = canonical.officials.get(id), paragraph = node('p', undefined, parent);
        node('span', `${official.position}: `, paragraph);
        const link = node('a', official.display_name, paragraph); link.href = `government.html?official=${encodeURIComponent(id)}#provincial-leadership`;
      }
    }
    function renderDistrict() {
      const preview = districtFor(focused || hovered), d = preview || canonical?.districts.find(d => d.id === districtSelected);
      detail.replaceChildren(); rendered = undefined;
      node('span', preview && preview.id !== districtSelected ? 'Preview' : d ? 'Selected district' : 'Explore Pangasinan', detail).className = 'municipality-map-kicker';
      node('h3', d ? d.name : 'Legislative districts', detail);
      if (!canonical) { node('p', 'District information is unavailable. Municipality boundaries and profiles remain available.', detail); return; }
      if (!d) { node('p', 'Choose a district to see its communities and published representatives.', detail); return; }
      node('p', `${d.lgu_psgcs.length} cities and municipalities`, detail); officialLinks(d, detail);
      const members = node('details', undefined, detail); node('summary', 'Member communities', members); const ul = node('ul', undefined, members);
      for (const p of records.filter(p => d.lgu_psgcs.includes(p.psgc))) { const link = node('a', p.name, node('li', undefined, ul)); link.href = profile(p); }
      const direct = node('a', 'Link to this district', node('p', undefined, detail)); direct.href = `municipality-map.html?view=districts&district=${encodeURIComponent(d.id)}`;
      const government = node('a', 'District leadership', node('p', undefined, detail)); government.href = `government.html?district=${encodeURIComponent(d.id)}#provincial-leadership`;
      node('p', 'Districts describe service constituencies, not project sponsorship or budget attribution.', detail).className = 'municipality-map-note';
    }
    function renderDetail() {
      if (view === 'districts') { renderDistrict(); return; }
      const preview = focused || hovered, record = records.find(p => p.psgc === (preview || selected));
      const kicker = preview && preview !== selected ? 'Preview' : record ? 'Selected community' : 'Explore Pangasinan';
      if (rendered === record && detail.firstChild) { detail.firstChild.textContent = kicker; return; }
      rendered = record;
      detail.replaceChildren();
      node('span', kicker, detail).className = 'municipality-map-kicker';
      if (mode === 'profile') { node('h3', record ? record.name : 'Loading boundary reference', detail); return; }
      if (!record) { node('h3', 'Your community, in view', detail); node('p', 'Choose a community from the map or searchable selector to see its published population and profile.', detail); return; }
      node('h3', record.name, detail);
      const facts = node('dl', undefined, detail);
      for (const [label, value] of [['2024 population', Number.isSafeInteger(record.population) ? record.population.toLocaleString('en-PH') : 'Not available'], ['Classification', record.classification === 'city' ? 'City' : 'Municipality'], ['Barangays', record.geography.barangay_count == null ? 'Not available' : String(record.geography.barangay_count)], ['PSGC', record.psgc]]) { node('dt', label, facts); node('dd', value, facts); }
      node('p', `Population reference: ${record.population_reference_date}. PSGC listing: ${record.psgc_release}. Barangay counts use the attributed reference snapshot.`, detail).className = 'municipality-map-note';
      const link = node('a', 'View Profile', detail, 'data-map-profile'); link.href = profile(record); link.className = 'btn btn-primary';
      const district = districtFor(record.psgc);
      if (district) { node('h4', district.name, detail); officialLinks(district, detail); }
    }
    function options() {
      selector.replaceChildren(); node('option', view === 'districts' ? 'Choose a district' : 'Choose a community', selector).value = '';
      const query = search.value.trim().toLocaleLowerCase();
      if (view === 'districts') {
        for (const d of canonical?.districts || []) if (d.id === districtSelected || `${d.name} ${d.number}`.toLocaleLowerCase().includes(query)) node('option', d.name, selector).value = d.id;
        selector.value = districtSelected || ''; return;
      }
      for (const p of records.filter(p => p.psgc === selected || `${p.name} ${p.psgc}`.toLocaleLowerCase().includes(query))) node('option', p.name, selector).value = p.psgc;
      selector.value = selected || '';
    }
    function paint() {
      for (const [code, boundary] of boundaries) {
        const active = view === 'districts' ? !!districtFor(code) && districtFor(code).id === districtSelected : code === selected;
        const preview = view === 'districts' ? !!districtFor(code) && districtFor(code).id === districtFor(focused || hovered)?.id : code === (focused || hovered);
        boundary.toggleAttribute('data-selected', active); boundary.toggleAttribute('data-preview', preview); boundary.setAttribute('aria-pressed', String(active));
        boundary.setAttribute('aria-label', view === 'districts' ? `${districtFor(code)?.name || 'District unavailable'}. ${records.find(p => p.psgc === code).name}. Select district.` : `${records.find(p => p.psgc === code).name}. Select community.`);
      }
      container.dataset.mapView = view;
      for (const button of viewButtons) button.setAttribute('aria-pressed', String(button.dataset.mapView === view));
      searchLabel.textContent = view === 'districts' ? 'Find a legislative district' : 'Find a city or municipality'; search.placeholder = view === 'districts' ? 'Search district name or number' : 'Search name or PSGC'; selectLabel.textContent = view === 'districts' ? 'Choose a district' : 'Choose a community';
      options(); renderDetail();
    }
    function setView(value) { if (destroyed || !['municipalities', 'districts'].includes(value)) return false; view = value; hovered = focused = null; rendered = undefined; search.value = ''; paint(); return true; }
    function selectDistrict(id) { if (destroyed || (id !== null && !canonical?.districts.some(d => d.id === id))) return false; districtSelected = id; paint(); if (onSelect) onSelect(canonical?.districts.find(d => d.id === id) || null); return true; }
    function activate(code) { return view === 'districts' ? selectDistrict(districtFor(code)?.id || null) : select(code); }
    function select(code) {
      if (destroyed || (code !== null && !records.some(p => p.psgc === code))) return false;
      selected = code; paint(); if (onSelect) onSelect(records.find(p => p.psgc === code) || null); return true;
    }
    function preview() { paint(); if (onPreview) onPreview(view === 'districts' ? districtFor(focused || hovered) || null : records.find(p => p.psgc === (focused || hovered)) || null); }
    search.addEventListener('input', options); selector.addEventListener('change', () => view === 'districts' ? selectDistrict(selector.value || null) : select(selector.value || null));
    const instance = { ready: null, select, setView, selectDistrict, destroy() { destroyed = true; content.remove(); instances.delete(container); } };
    instances.set(container, instance); renderDetail();
    const optionalData = loadLeadership();
    instance.ready = load().then(data => {
      if (destroyed) return instance;
      records = data.records; if (!records.some(p => p.psgc === selected)) selected = null;
      for (const p of records) {
        const boundary = document.createElementNS(ns, 'a'); boundary.setAttribute('href', profile(p)); boundary.setAttribute('role', 'button'); boundary.setAttribute('tabindex', '0'); boundary.setAttribute('aria-label', `${p.name}. Select community.`); boundary.dataset.psgc = p.psgc;
        const path = document.createElementNS(ns, 'path'); path.setAttribute('d', p.path); path.setAttribute('fill-rule', 'evenodd');
        const title = document.createElementNS(ns, 'title'); title.textContent = p.name; path.append(title); boundary.append(path); svg.append(boundary); boundaries.set(p.psgc, boundary);
        boundary.addEventListener('click', event => { event.preventDefault(); activate(p.psgc); });
        boundary.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(p.psgc); } });
        boundary.addEventListener('pointerenter', () => { hovered = p.psgc; preview(); }); boundary.addEventListener('pointerleave', () => { hovered = null; preview(); });
        boundary.addEventListener('focus', () => { focused = p.psgc; preview(); }); boundary.addEventListener('blur', () => { focused = null; preview(); });
        const item = node('li', undefined, list); const link = node('a', `${p.name}: ${p.population.toLocaleString('en-PH')} people (2024); ${p.classification}; ${p.geography.barangay_count ?? 'unavailable'} barangays`, item); link.href = profile(p);
      }
      paint(); status.textContent = mode === 'profile' ? 'Boundary reference: the selected community is highlighted.' : `${records.length}/48 published city and municipality boundaries. Select a community to explore its profile.`; credit.textContent = data.manifest.attribution;
      provenance.textContent = `Population: Philippine Statistics Authority, July 1, 2024; administrative listing ${data.manifest.registry_release}. Boundaries represent ${data.manifest.boundary_metadata.boundaryYearRepresented}, built ${data.manifest.boundary_metadata.buildDate}. Barangays: PSGC Cloud, an unofficial snapshot; no official PSA release currency is asserted.`;
      return optionalData.then(value => { if (!destroyed) { try { canonical = districtData(value, records); } catch { canonical = null; } rendered = undefined; paint(); } return instance; });
    }).catch(() => {
      if (!destroyed) { status.textContent = 'Geography could not be loaded. No boundaries or missing statistics are inferred.'; const link = node('a', 'Browse all LGU profiles', detail); link.href = 'lgus.html'; }
      return instance;
    });
    return instance;
  }
  window.createMunicipalityMap = createMunicipalityMap; window.MunicipalityMap = { createMunicipalityMap };
  function initialize() { const query = new URLSearchParams(location.search); document.querySelectorAll('[data-lgu-map]').forEach(container => createMunicipalityMap({ container, mode: container.dataset.mapMode || 'explorer', selectedPsgc: container.dataset.selectedPsgc || query.get('psgc') || null, view: query.get('view') || 'municipalities', selectedDistrictId: query.get('district') || null })); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true }); else initialize();
})();
