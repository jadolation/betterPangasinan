/* Public module views: all dataset text is inserted as text, never markup. */
(() => {
  'use strict';
  const root = document.querySelector('[data-module]');
  if (!root) return;
  const kind = root.dataset.module;
  const status = root.querySelector('[data-status]');
  const results = root.querySelector('[data-results]');
  const form = root.querySelector('[data-filters]');
  const datasets = ['sources', 'entities', 'lgus', 'finances', 'projects', 'procurements', 'contracts', 'legislation', 'documents', 'services', 'statistics', 'geography'];
  let dictionary = {};
  const t = (key, fallback) => typeof dictionary[`modules.${key}`] === 'string' ? dictionary[`modules.${key}`] : fallback;
  const node = (tag, text, parent, className) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = String(text);
    if (className) el.className = className;
    if (parent) parent.append(el);
    return el;
  };
  const title = record => record.title || record.name || record.indicator || record.id;
  const label = value => String(value).replaceAll('_', ' ');
  const link = (parent, text, url) => {
    try {
      const parsed = new URL(url, document.baseURI);
      if (!['http:', 'https:'].includes(parsed.protocol)) return;
      const a = node('a', text, parent);
      a.href = parsed.href;
    } catch { /* Invalid source URLs are not made interactive. */ }
  };
  const ids = record => record.source_ids || (record.source_id ? [record.source_id] : []);
  const metadata = (record, parent) => {
    const dl = node('dl', undefined, parent);
    for (const field of ['id', 'year', 'reporting_period', 'category', 'status', 'verification_status', 'publication_status', 'availability', 'entity_id', 'responsible_entity_id', 'lgu_id', 'unit', 'currency', 'methodology', 'requirements', 'processing_time', 'fees']) {
      if (record[field] === undefined || record[field] === null) continue;
      node('dt', label(field), dl);
      node('dd', typeof record[field] === 'object' ? JSON.stringify(record[field]) : record[field], dl);
    }
    if (record.value !== undefined) {
      node('dt', 'Observation', dl);
      node('dd', record.value === null ? 'Unknown' : record.value, dl);
    }
  };
  let data;
  const sources = (record, parent) => {
    node('h4', t('sources', 'Sources'), parent);
    if (!ids(record).length) node('p', t('source_unavailable', 'Source references unavailable.'), parent);
    for (const id of ids(record)) {
      const source = data.sources.find(item => item.id === id);
      const p = node('p', undefined, parent);
      if (!source) { p.textContent = `Source unavailable: ${id}`; continue; }
      node('span', `${title(source)}${source.accessed_at ? ` (accessed ${source.accessed_at})` : ''} `, p);
      if (source.url) link(p, t('open_source', 'Open original source'), source.url);
    }
  };
  const relationships = (record, parent) => {
    const projectIds = record.project_ids || (record.project_id ? [record.project_id] : []);
    for (const id of projectIds) {
      const project = data.projects.find(item => item.id === id);
      if (project) link(node('p', undefined, parent), `Project: ${title(project)}`, `project.html?id=${encodeURIComponent(id)}`);
      else node('p', `Linked project unavailable: ${id}`, parent);
    }
    const procurements = data.procurements.filter(item => item.project_id === record.id || (item.project_ids || []).includes(record.id) || (record.procurement_ids || []).includes(item.id));
    for (const procurement of procurements) link(node('p', undefined, parent), `Procurement: ${title(procurement)}`, `procurement.html?id=${encodeURIComponent(procurement.id)}`);
    const contracts = data.contracts.filter(item => item.procurement_id === record.id || (record.contract_ids || []).includes(item.id) || record.contract_id === item.id);
    for (const contract of contracts) {
      const section = node('section', undefined, parent);
      node('h4', `Contract: ${title(contract)}`, section);
      metadata(contract, section);
      if (contract.amount !== undefined) node('p', `Contract value: ${contract.amount === null ? 'Unknown' : contract.amount} ${contract.currency || ''}`, section);
      sources(contract, section);
    }
    if (kind === 'project' && !procurements.length) node('p', 'No linked procurement records are published.', parent);
  };
  const card = record => {
    const article = node('article', undefined, results, 'card');
    const h = node('h3', undefined, article);
    if (kind === 'projects') link(h, title(record), `project.html?id=${encodeURIComponent(record.id)}`);
    else if (kind === 'procurements' && !new URLSearchParams(location.search).get('id')) link(h, title(record), `procurement.html?id=${encodeURIComponent(record.id)}`);
    else h.textContent = title(record);
    if (record.description) node('p', record.description, article);
    metadata(record, article);
    relationships(record, article);
    sources(record, article);
  };
  // Currency values use decimal strings and integer minor units, not floating-point sums.
  const minor = value => {
    if (typeof value === 'number') {
      if (!Number.isFinite(value) || Math.abs(value) > Number.MAX_SAFE_INTEGER / 100) return null;
      value = String(value);
    }
    if (typeof value !== 'string' || !/^-?\d+(\.\d{1,2})?$/.test(value)) return null;
    const negative = value.startsWith('-');
    const [whole, fraction = ''] = value.replace('-', '').split('.');
    const result = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
    return negative ? -result : result;
  };
  const decimal = value => `${value < 0n ? '-' : ''}${(value < 0n ? -value : value) / 100n}.${String((value < 0n ? -value : value) % 100n).padStart(2, '0')}`;
  const finance = records => {
    if (!records.length) return;
    const tableWrap = node('div', undefined, results);
    tableWrap.style.overflowX = 'auto';
    tableWrap.tabIndex = 0;
    tableWrap.setAttribute('role', 'region');
    tableWrap.setAttribute('aria-label', 'Financial records table');
    const table = node('table', undefined, tableWrap);
    node('caption', 'Published financial records. Unknown amounts are not zero.', table);
    const header = node('tr', undefined, node('thead', undefined, table));
    for (const text of ['Record', 'Year', 'Category', 'Amount type', 'Amount', 'Currency / unit', 'Sources']) {
      const th = node('th', text, header); th.scope = 'col';
    }
    const body = node('tbody', undefined, table);
    for (const record of records) {
      const tr = node('tr', undefined, body);
      const th = node('th', title(record), tr); th.scope = 'row';
      for (const value of [record.year, record.category, label(record.amount_type || 'Unknown'), record.amount === null ? 'Unknown' : record.amount, `${record.currency || 'Unknown'} / ${record.unit || 'Unknown'}`]) node('td', value ?? 'Unknown', tr);
      sources(record, node('td', undefined, tr));
    }
    const selected = new FormData(form);
    const compatible = selected.get('year') && selected.get('amount_type') && new Set(records.map(r => `${r.year}|${r.amount_type}|${r.currency}|${r.unit}|${r.is_mock}`)).size === 1 && records.every(r => r.currency && r.unit && minor(r.amount) !== null);
    if (!compatible) { node('p', 'No combined total: select one year and amount type; all amounts, currencies and units must be compatible and known.', results); return; }
    const values = records.map(r => minor(r.amount));
    node('p', `Total for this selection: ${decimal(values.reduce((a, b) => a + b, 0n))} ${records[0].currency} (${records[0].unit}).`, results);
    const chart = node('figure', undefined, results);
    node('figcaption', t('chart_caption', 'Amount comparison. Exact values appear in the table above.'), chart);
    const max = values.reduce((a, b) => b > a ? b : a, 0n);
    records.forEach((record, index) => {
      const p = node('p', `${title(record)}: ${record.amount} ${record.currency} `, chart);
      if (values[index] >= 0n && max > 0n) {
        const bar = node('meter', undefined, p);
        bar.min = 0; bar.max = 100; bar.value = Number(values[index] * 10000n / max) / 100;
        bar.setAttribute('aria-label', `${title(record)}: ${record.amount} ${record.currency}`);
      }
    });
  };
  async function map(records) {
    results.replaceChildren();
    records.forEach(card);
    const usable = records.filter(r => r.geometry && r.license && r.verification_status === 'verified');
    if (!usable.length) { status.textContent = 'No reviewed, licensed geometry is available. No boundaries or project pins are drawn.'; node('p', 'No reviewed geographic records can be displayed. Browse the project registry for non-geographic records.', results); return; }
    status.textContent = 'Loading map library. The text alternative remains available.';
    const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'; document.head.append(css);
    try {
      await new Promise((resolve, reject) => {
        const script = document.createElement('script'); script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'; script.onload = resolve; script.onerror = reject; document.body.append(script);
      });
      const element = document.getElementById('project-map'); element.hidden = false;
      const view = window.L.map(element);
      const bounds = [];
      const groups = { projects: window.L.layerGroup().addTo(view), boundaries: window.L.layerGroup().addTo(view) };
      for (const record of usable) {
        const layer = window.L.geoJSON(record.geometry).bindPopup(() => node('span', title(record)));
        layer.addTo(groups[record.geometry.type === 'Point' ? 'projects' : 'boundaries']); bounds.push(layer.getBounds());
      }
      for (const [name, group] of Object.entries(groups)) {
        const input = form.elements.namedItem(name);
        input.disabled = !group.getLayers().length;
        input.checked = !input.disabled;
        input.addEventListener('change', () => { if (input.checked) group.addTo(view); else view.removeLayer(group); });
      }
      const combined = window.L.latLngBounds(bounds); view.fitBounds(combined, { maxZoom: 13 });
      const tiles = window.L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>' }).addTo(view);
      tiles.on('tileerror', () => { status.textContent = 'Background tiles could not load. Reviewed geometry and the text alternative remain available.'; });
      const layerNames = { 'Reviewed project locations': groups.projects, 'Reviewed boundaries': groups.boundaries };
      window.L.control.layers({}, layerNames).addTo(view);
      view.on('overlayadd overlayremove', () => {
        for (const [name, group] of Object.entries(groups)) form.elements.namedItem(name).checked = view.hasLayer(group);
      });
      status.textContent = 'Reviewed geometry loaded. The same records appear in the text alternative.';
    } catch { status.textContent = 'The map could not load. Use the equivalent sourced text records below.'; }
  }
  async function start() {
    try {
      const response = await fetch('locales/en.json');
      if (response.ok) {
        const loaded = await response.json();
        if (loaded && typeof loaded === 'object' && !Array.isArray(loaded)) dictionary = loaded;
      }
    } catch { /* The reviewed English interface is the fallback. */ }
    try {
      const response = await fetch('data/public.json');
      if (!response.ok) throw new Error('Aggregate unavailable');
      data = await response.json();
      if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('Invalid dataset');
    } catch {
      data = {};
      try {
        const needed = new Set(['sources', kind === 'project' ? 'projects' : kind]);
        if (['projects', 'project', 'procurements'].includes(kind)) ['projects', 'procurements', 'contracts'].forEach(name => needed.add(name));
        if (kind === 'legislation') needed.add('documents');
        await Promise.all([...needed].map(async name => {
          const response = await fetch(`data/${name}.json`);
          if (!response.ok) {
            if (name === kind || (kind === 'project' && name === 'projects') || name === 'sources') throw new Error('Dataset unavailable');
            data[name] = []; return;
          }
          data[name] = await response.json();
        }));
      } catch { status.textContent = t('load_error', 'Published data could not be loaded. Availability is unknown; this does not mean there are no public records. Please try again later.'); return; }
    }
    const testMode = document.querySelector('meta[name="data-mode"]')?.content === 'test';
    for (const name of datasets) data[name] = Array.isArray(data[name]) ? data[name].filter(record => testMode || (record.is_mock === false && record.publication_status === 'approved')) : [];
    // The registry uses reporting_period for years and PHP as the monetary unit.
    for (const name of datasets) data[name] = data[name].map(record => ({
      ...record,
      year: record.year ?? (/^\d{4}$/.test(record.reporting_period || '') ? record.reporting_period : undefined),
      currency: record.currency ?? (record.unit === 'PHP' ? 'PHP' : undefined)
    }));
    let records = data[kind] || [];
    if (kind === 'legislation') records = [...data.legislation, ...data.documents];
    const selectedLgu = new URLSearchParams(location.search).get('lgu');
    if (selectedLgu) {
      records = records.filter(record => record.lgu_id === selectedLgu);
      if (!records.length) status.textContent = 'No reviewed records are published for the selected LGU. This is a portal coverage gap, not evidence of noncompliance.';
      else node('p', `Showing records explicitly linked to LGU identifier: ${selectedLgu}`, form?.parentNode || root);
    }
    if (kind === 'project') {
      const id = new URLSearchParams(location.search).get('id');
      const record = data.projects.find(item => item.id === id);
      if (!record) { status.textContent = id ? 'Project not found. This identifier is not in the published registry.' : 'No project selected. Choose a record from the project registry.'; return; }
      status.textContent = 'Published project record'; card(record); return;
    }
    if (kind === 'geography') { await map(records); return; }
    for (const select of form.querySelectorAll('select')) {
      const values = [...new Set(records.map(record => record[select.name]).filter(value => value !== null && value !== undefined))].sort();
      for (const value of values) { const option = node('option', label(value), select); option.value = value; }
    }
    const render = () => {
      const filters = new FormData(form);
      const id = kind === 'procurements' ? new URLSearchParams(location.search).get('id') : null;
      const filtered = records.filter(record => (!id || record.id === id) && [...filters].every(([key, value]) => !value || (key === 'q' ? JSON.stringify(record).toLowerCase().includes(value.toLowerCase().trim()) : String(record[key]) === value)));
      results.replaceChildren();
      if (!records.length) return;
      status.textContent = filtered.length ? `${filtered.length} published record${filtered.length === 1 ? '' : 's'} match your selection.` : t('no_matches', 'No published records match this selection. Clear filters to browse the collection.');
      if (kind === 'finances') finance(filtered); else filtered.forEach(card);
    };
    form.addEventListener('submit', event => { event.preventDefault(); render(); });
    form.addEventListener('input', render);
    form.addEventListener('change', render);
    form.addEventListener('reset', () => { setTimeout(render, 0); });
    render();
  }
  start().catch(() => { status.textContent = 'This view could not be displayed. Consult the original sources or try again later.'; });
})();
