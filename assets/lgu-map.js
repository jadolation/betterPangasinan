/* All maps share one local source load and one stable projection. */
(() => {
  'use strict';
  const ns = 'http://www.w3.org/2000/svg', instances = new WeakMap();
  let shared, sequence = 0;
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
  function createMunicipalityMap({ container, mode = 'explorer', selectedPsgc = null, onSelect, onPreview } = {}) {
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
    let records = [], selected = selectedPsgc, hovered = null, focused = null, destroyed = false, rendered;
    const boundaries = new Map();
    function renderDetail() {
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
    }
    function options() {
      selector.replaceChildren(); node('option', 'Choose a community', selector).value = '';
      const query = search.value.trim().toLocaleLowerCase();
      for (const p of records.filter(p => p.psgc === selected || `${p.name} ${p.psgc}`.toLocaleLowerCase().includes(query))) node('option', p.name, selector).value = p.psgc;
      selector.value = selected || '';
    }
    function paint() {
      for (const [code, boundary] of boundaries) {
        boundary.toggleAttribute('data-selected', code === selected); boundary.toggleAttribute('data-preview', code === (focused || hovered)); boundary.setAttribute('aria-pressed', String(code === selected));
      }
      options(); renderDetail();
    }
    function select(code) {
      if (destroyed || (code !== null && !records.some(p => p.psgc === code))) return false;
      selected = code; paint(); if (onSelect) onSelect(records.find(p => p.psgc === code) || null); return true;
    }
    function preview() { paint(); if (onPreview) onPreview(records.find(p => p.psgc === (focused || hovered)) || null); }
    search.addEventListener('input', options); selector.addEventListener('change', () => select(selector.value || null));
    const instance = { ready: null, select, destroy() { destroyed = true; content.remove(); instances.delete(container); } };
    instances.set(container, instance); renderDetail();
    instance.ready = load().then(data => {
      if (destroyed) return instance;
      records = data.records; if (!records.some(p => p.psgc === selected)) selected = null;
      for (const p of records) {
        const boundary = document.createElementNS(ns, 'a'); boundary.setAttribute('href', profile(p)); boundary.setAttribute('role', 'button'); boundary.setAttribute('tabindex', '0'); boundary.setAttribute('aria-label', `${p.name}. Select community.`); boundary.dataset.psgc = p.psgc;
        const path = document.createElementNS(ns, 'path'); path.setAttribute('d', p.path); path.setAttribute('fill-rule', 'evenodd');
        const title = document.createElementNS(ns, 'title'); title.textContent = p.name; path.append(title); boundary.append(path); svg.append(boundary); boundaries.set(p.psgc, boundary);
        boundary.addEventListener('click', event => { event.preventDefault(); select(p.psgc); });
        boundary.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(p.psgc); } });
        boundary.addEventListener('pointerenter', () => { hovered = p.psgc; preview(); }); boundary.addEventListener('pointerleave', () => { hovered = null; preview(); });
        boundary.addEventListener('focus', () => { focused = p.psgc; preview(); }); boundary.addEventListener('blur', () => { focused = null; preview(); });
        const item = node('li', undefined, list); const link = node('a', `${p.name}: ${p.population.toLocaleString('en-PH')} people (2024); ${p.classification}; ${p.geography.barangay_count ?? 'unavailable'} barangays`, item); link.href = profile(p);
      }
      paint(); status.textContent = mode === 'profile' ? 'Boundary reference: the selected community is highlighted.' : `${records.length}/48 published city and municipality boundaries. Select a community to explore its profile.`; credit.textContent = data.manifest.attribution;
      provenance.textContent = `Population: Philippine Statistics Authority, July 1, 2024; administrative listing ${data.manifest.registry_release}. Boundaries represent ${data.manifest.boundary_metadata.boundaryYearRepresented}, built ${data.manifest.boundary_metadata.buildDate}. Barangays: PSGC Cloud, an unofficial snapshot; no official PSA release currency is asserted.`;
      return instance;
    }).catch(() => {
      if (!destroyed) { status.textContent = 'Geography could not be loaded. No boundaries or missing statistics are inferred.'; const link = node('a', 'Browse all LGU profiles', detail); link.href = 'lgus.html'; }
      return instance;
    });
    return instance;
  }
  window.createMunicipalityMap = createMunicipalityMap; window.MunicipalityMap = { createMunicipalityMap };
  function initialize() { document.querySelectorAll('[data-lgu-map]').forEach(container => createMunicipalityMap({ container, mode: container.dataset.mapMode || 'explorer', selectedPsgc: container.dataset.selectedPsgc || new URLSearchParams(location.search).get('psgc') || null })); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true }); else initialize();
})();
