/* One canonical LGU, explicit relationships, and optional derived source views. */
(() => {
  'use strict';
  const host = document.getElementById('profile-content');
  if (!host) return;
  const byId = name => document.getElementById(`profile-${name}`);
  const el = (tag, value, className) => { const node = document.createElement(tag); if (value !== undefined) node.textContent = value; if (className) node.className = className; return node; };
  const number = value => value == null ? 'Not available' : typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('en-PH') : String(value);
  const money = value => value == null ? 'Not supplied' : typeof value === 'number' && Number.isFinite(value) && Number.isSafeInteger(Math.round(value * 100)) ? `PHP ${value.toLocaleString('en-PH', { maximumFractionDigits: 2 })}` : 'See original source amount';
  function sourceLink(url, label = 'Open source') {
    try { const parsed = new URL(url); if (parsed.protocol !== 'https:' || parsed.username || parsed.password) return null; const a = el('a', label); a.href = parsed.href; a.rel = 'noopener noreferrer'; return a; } catch { return null; }
  }
  function published(row) {
    const mode = document.querySelector('meta[name="data-mode"]')?.content;
    return mode === 'test' || (row.is_mock === false && (mode === 'preview' || row.publication_status === 'approved'));
  }
  function linked(row, lgu) { return row.lgu_id === lgu.id || Boolean(lgu.psgc && (row.lgu_psgc === lgu.psgc || row.psgc === lgu.psgc)); }
  function unique(rows) { const seen = new Set(); return rows.filter(row => { const key = row.id || JSON.stringify(row); if (seen.has(key)) return false; seen.add(key); return true; }); }
  function aggregate(lgu, graph, extra) {
    const arrays = ['statistics', 'budget_observations', 'planning_records', 'government', 'hospitals', 'barangays', 'sources'];
    let valid = extra && extra.schema_version === 1 && extra.lgu_id === lgu.id && extra.psgc === (lgu.psgc ?? null) &&
      arrays.every(key => Array.isArray(extra[key]) && extra[key].every(row => row && typeof row === 'object' && !Array.isArray(row))) &&
      extra.barangays.every(row => row.parent_psgc === lgu.psgc && typeof row.name === 'string') &&
      (extra.barangay_count === null || (Number.isSafeInteger(extra.barangay_count) && extra.barangay_count === extra.barangays.length)) &&
      Array.isArray(extra.national?.verified) && Array.isArray(extra.national?.discovery) && Array.isArray(extra.historical?.discovery) ? extra : null;
    if (valid?.legislative) {
      const district = valid.legislative.district;
      const representative = valid.legislative.representative;
      const board = valid.legislative.board_members;
      if (!district || typeof district.id !== 'string' || typeof district.name !== 'string' || !Number.isInteger(district.number) || district.number < 1 || district.number > 6 ||
          !representative || representative.role_type !== 'house_representative' || representative.district_id !== district.id ||
          !Array.isArray(board) || board.length !== 2 || board.some(person => !person || person.role_type !== 'board_member' || person.district_id !== district.id) || new Set(board.map(person => person.id)).size !== 2 ||
          [representative, ...(Array.isArray(board) ? board : [])].some(person => typeof person.id !== 'string' || typeof person.display_name !== 'string') ||
          !Array.isArray(valid.legislative.sources)) valid = { ...valid, legislative: null };
    }
    const local = key => unique((graph[key] || []).filter(row => published(row) && linked(row, lgu)));
    const entities = local('entities');
    const localEntityIds = new Set(entities.map(row => row.id));
    return {
      lgu, extra: valid,
      statistics: unique([...local('statistics'), ...(valid?.statistics || [])]),
      finances: local('finances'), budgetObservations: valid?.budget_observations || [],
      projects: local('projects'), planning: valid?.planning_records || [],
      services: unique((graph.services || []).filter(row => published(row) && (linked(row, lgu) || localEntityIds.has(row.entity_id)))),
      government: [...entities, ...(valid?.government || [])], hospitals: valid?.hospitals || [],
      barangays: valid?.barangays || [],
      sources: unique([...(graph.sources || []).filter(published), ...(valid?.sources || [])]),
    };
  }
  // Pure relationship helper is shared with regression tests, not another data store.
  window.LGUProfileData = { aggregate };
  function evidence(row, model) {
    const details = el('details'); details.append(el('summary', 'Details and source'));
    const ids = row.source_ids || (row.source_id ? [row.source_id] : []);
    for (const id of ids) {
      const source = model.sources.find(item => item.id === id || item.source_id === id);
      if (!source) continue;
      const p = el('p', source.name || source.title || source.publisher || id);
      const a = sourceLink(source.url); if (a) p.append(document.createTextNode(' / '), a);
      details.append(p);
    }
    const link = sourceLink(row.source_url || row.url);
    if (link) { const p = el('p'); p.append(link); details.append(p); }
    for (const [label, value] of [['Reporting period', row.reference_period || row.reporting_period || row.year], ['Source note', row.notes || row.definition], ['Reference date', row.as_of_date], ['Collected', row.collected_at]]) {
      if (value !== undefined && value !== null && value !== '') details.append(el('p', `${label}: ${value}`));
    }
    const technical = el('details'); technical.append(el('summary', 'Original record and identifiers'));
    technical.addEventListener('toggle', () => { if (technical.open && !technical.querySelector('pre')) technical.append(el('pre', JSON.stringify(row, null, 2))); });
    details.append(technical);
    return details;
  }
  function empty(parent, text, href, label) {
    parent.append(el('p', text));
    if (href) { const link = el('a', label); link.href = href; parent.append(link); }
  }
  function renderStatistics(model) {
    const target = byId('statistics'); target.replaceChildren();
    if (!model.statistics.length) return empty(target, 'No local statistical observations are available in this collection.', 'statistics.html', 'Explore provincial statistics');
    const grid = el('div', undefined, 'lgu-stat-grid');
    for (const row of model.statistics) {
      const card = el('article', undefined, 'lgu-stat');
      const name = row.id?.startsWith('population-') ? 'Population' : row.indicator || row.name || 'Local observation';
      const unit = row.unit === 'persons' ? 'People' : row.unit === 'percent' ? '%' : row.unit || 'Unit not supplied';
      card.append(el('h3', name), el('strong', number(row.value)), el('p', `${unit} / ${row.reference_period || row.reporting_period || 'Date not supplied'}`, 'lgu-caption'), evidence(row, model));
      grid.append(card);
    }
    target.append(grid);
  }
  function renderBarangays(model) {
    const input = byId('barangay-search'), list = byId('barangay-list'), more = byId('more-barangays');
    let limit = 8;
    input.disabled = !model.barangays.length;
    function render() {
      const rows = model.barangays.filter(row => row.name.toLocaleLowerCase().includes(input.value.trim().toLocaleLowerCase()));
      list.replaceChildren();
      for (const row of rows.slice(0, limit)) {
        const li = el('li'); const details = el('details'); details.append(el('summary', row.name), el('p', `Official geographic code: ${row.psgc || row.source_code || 'Not supplied'}`)); li.append(details); list.append(li);
      }
      byId('barangay-status').textContent = model.barangays.length ? `${rows.length} matching barangays / ${model.barangays.length} in this collected registry. Showing ${Math.min(limit, rows.length)}.` : 'No barangay records are available in this collection. No count is inferred.';
      more.hidden = rows.length <= limit;
    }
    input.addEventListener('input', () => { limit = 8; render(); });
    more.addEventListener('click', () => { limit += 12; render(); });
    render();
  }
  function renderFinances(model) {
    const target = byId('finances'); target.replaceChildren();
    const rows = [...model.finances.map(record => ({ record, kind: 'ledger' })), ...model.budgetObservations.map(record => ({ record, kind: 'observation' }))];
    if (!rows.length) return empty(target, 'No local finance records are available in this collection.', 'finances.html', 'Explore the provincial finance collections');
    target.append(el('p', 'Reported budgets and financial records are shown separately, not added together. They are not proof of actual spending.', 'lgu-caption'));
    const wrap = el('div', undefined, 'lgu-table-wrap'), table = el('table');
    const caption = el('caption', 'Local financial records and reported budget observations'); caption.className = 'sr-only'; table.append(caption);
    const head = el('thead'), header = el('tr'); for (const text of ['Year', 'Type', 'Reported amount', 'Source context']) { const th = el('th', text); th.scope = 'col'; header.append(th); } head.append(header); table.append(head);
    const body = el('tbody');
    for (const { record, kind } of rows) {
      const row = el('tr');
      const type = kind === 'ledger' ? (record.amount_type || 'Financial record').replace(/_/g, ' ') : record.budget_type || 'Reported budget';
      row.append(el('td', String(record.year || record.reporting_period || 'Not supplied')), el('td', type));
      row.append(el('td', money(kind === 'ledger' ? record.amount : record.amount_php), 'lgu-money'));
      const source = el('td');
      if (record.provincial_review_disposition) source.append(el('p', record.provincial_review_disposition, /part/i.test(record.provincial_review_disposition) ? 'lgu-notice' : ''));
      if (/propos/i.test(type)) source.append(el('p', 'Proposal, not an approved appropriation.', 'lgu-caption'));
      source.append(evidence(record, model)); row.append(source); body.append(row);
    }
    table.append(body); wrap.append(table); target.append(wrap);
  }
  function renderProjects(model) {
    const target = byId('projects'); target.replaceChildren();
    target.append(el('h3', 'Linked local project records'));
    if (!model.projects.length && !model.planning.length) target.append(el('p', 'No local project records are linked to this LGU in the collection.'));
    for (const row of [...model.projects, ...model.planning]) {
      const card = el('article', undefined, 'lgu-record'); card.append(el('h4', row.name || row.title || row.project_name || 'Local project record'), evidence(row, model)); target.append(card);
    }
    const national = model.extra?.national;
    if (national?.verified?.length) {
      target.append(el('h3', 'Reviewed geographic relationships'));
      target.append(el('p', 'A reviewed relationship does not assign an entire shared allocation to this LGU.', 'lgu-caption'));
      for (const row of national.verified) {
        const link = el('a', row.title); link.href = `national-budget.html?q=${encodeURIComponent(row.id)}#projects`; const p = el('p'); p.append(link); target.append(p);
        if (row.has_published_coordinates) { const map = el('a', 'Inspect published coordinates'); map.href = `map.html?project=${encodeURIComponent(row.id)}`; target.append(map); }
      }
    }
    target.append(el('h3', 'Names to explore in national budgets'));
    target.append(el('p', 'These are name matches, not confirmed local projects or local funding. Office-wide records are not assigned to this LGU.', 'lgu-notice'));
    const discovery = national?.discovery || [];
    if (discovery.length) {
      target.append(el('p', `${national.discovery_count} FY2027 title matches; a preview of ${discovery.length} is shown.`));
      for (const row of discovery) {
        const card = el('article', undefined, 'lgu-record'); const a = el('a', row.title); a.href = `national-budget.html?q=${encodeURIComponent(row.id)}#projects`; card.append(a, el('p', `${row.dataset.toUpperCase()} / ${row.house_stage === 'hgab3' ? 'House third reading' : 'House second reading'} / location not verified`, 'lgu-caption'));
        if (row.has_published_coordinates) { const map = el('a', row.location_audit_status === 'suspicious' ? 'Inspect suspicious published location' : 'Inspect published coordinates'); map.href = `map.html?project=${encodeURIComponent(row.id)}`; card.append(map); }
        target.append(card);
      }
    } else target.append(el('p', 'No title matches are supplied in this profile bundle. This does not establish absence of projects.'));
    const query = model.lgu.name.replace(/^City of /i, '');
    const links = el('p');
    for (const [label, url] of [['Search FY2027 proposals', `national-budget.html?q=${encodeURIComponent(query)}#projects`], ['Explore engineering offices', 'national-budget.html#offices'], ['Search historical program names', `historical-budget.html?q=${encodeURIComponent(query)}`]]) {
      const a = el('a', label); a.href = url; links.append(a, document.createTextNode(' / '));
    }
    target.append(links);
    if (model.extra?.historical?.discovery_count) target.append(el('p', `${model.extra.historical.discovery_count} historical program-name matches are available in the separate GAA explorer. Appropriations are not spending.`, 'lgu-caption'));
  }
  function renderGovernment(model) {
    const target = byId('government'); target.replaceChildren();
    const legislative = model.extra?.legislative;
    if (legislative) {
      target.append(el('h3', legislative.district.name));
      const map = el('a', 'Explore this legislative district'); map.href = `municipality-map.html?view=districts&district=${encodeURIComponent(legislative.district.id)}`;
      const action = el('p'); action.append(map); target.append(action);
      const grid = el('div', undefined, 'lgu-representatives');
      for (const official of [legislative.representative, ...legislative.board_members]) {
        const card = el('article', undefined, 'lgu-record');
        card.append(el('p', official.role_type === 'house_representative' ? 'Congressional representative' : 'Provincial board member', 'lgu-caption'), el('h4', official.display_name));
        const link = el('a', 'Profile and official sources'); link.href = `government.html?official=${encodeURIComponent(official.id)}#provincial-leadership`; card.append(link); grid.append(card);
      }
      target.append(grid, el('p', 'District membership does not show who requested or controlled a project.', 'lgu-caption'));
      const source = el('details'); source.append(el('summary', 'District sources and reference dates'));
      for (const item of legislative.sources) {
        if (!item || typeof item.url !== 'string') continue;
        const p = el('p', `${item.publisher} / ${typeof item.retrieved_at === 'string' ? item.retrieved_at.slice(0, 10) : 'Date not supplied'}`); const link = sourceLink(item.url); if (link) p.append(document.createTextNode(' / '), link); source.append(p);
      }
      source.append(el('p', legislative.metadata?.house_verification || 'See each official source for its reference date.')); target.append(source);
    }
    const rows = [...model.government, ...model.services, ...model.hospitals];
    if (!rows.length) return empty(target, legislative ? 'No additional local office or service records are linked in this collection.' : 'No offices, services or facilities are explicitly linked to this LGU in this collection.', 'government.html', 'Browse the provincial government directory');
    target.append(el('p', 'Officeholders and contacts are source-listed; current terms and availability are not inferred.', 'lgu-caption'));
    for (const row of rows) {
      const card = el('article', undefined, 'lgu-record');
      card.append(el('h3', row.name || row.institution || row.office || 'Listed local service'));
      if (row.location) card.append(el('p', row.location));
      if (row.public_contact) {
        card.append(el('p', row.public_contact));
        const numbers = row.public_contact.match(/(?:\(075\)|075)[ -]*\d{3}[ -]*\d{4}|09\d{2}[ -]*\d{3}[ -]*\d{4}/g) || [];
        for (const raw of [...new Set(numbers)]) { const a = el('a', `Call ${raw}`); a.href = 'tel:' + raw.replace(/[^0-9]/g, ''); card.append(a, document.createTextNode(' ')); }
      }
      card.append(evidence(row, model)); target.append(card);
    }
  }
  function renderSources(model) {
    const target = byId('sources'); target.replaceChildren();
    const referenced = new Set(model.lgu.source_ids || []);
    for (const row of [...model.statistics, ...model.finances, ...model.projects, ...model.services, ...model.government]) for (const id of row.source_ids || []) referenced.add(id);
    const sources = model.sources.filter(row => referenced.has(row.id) || row.source_id);
    for (const row of sources) {
      const details = el('details'); details.append(el('summary', row.publisher || row.name || row.title || 'Record source'));
      const a = sourceLink(row.url, row.name || row.title || 'Open original source'); if (a) details.append(a);
      if (row.accessed_date) details.append(el('p', `Source accessed: ${row.accessed_date}`));
      const technical = el('details'); technical.append(el('summary', 'Source identifiers and original notes'), el('pre', JSON.stringify(row, null, 2))); details.append(technical); target.append(details);
    }
    if (model.extra?.geography) {
      const details = el('details'); details.append(el('summary', 'Geographic and barangay sources'));
      details.append(el('p', model.extra.geography.attribution || 'See the geographic manifest.'), el('p', model.extra.geography.barangay_note || 'Barangay release is not established.'));
      const a = el('a', 'Geographic source manifest'); a.href = 'data/geography/manifest.json'; details.append(a); target.append(details);
    }
    const technical = el('details'); technical.append(el('summary', 'Registry identifiers and relationship rules'), el('pre', JSON.stringify({ lgu: model.lgu, association_rules: model.extra?.association_rules || 'Generic records use explicit LGU IDs.' }, null, 2))); target.append(technical);
    if (!sources.length) target.prepend(el('p', 'Source references are not yet published.'));
  }
  async function json(url, optional = false) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try { const response = await fetch(url, { signal: controller.signal }); if (!response.ok) throw new Error('Unavailable'); return await response.json(); }
    catch (error) { if (optional) return null; throw error; }
    finally { clearTimeout(timer); }
  }
  async function init() {
    try {
      const graph = await json('data/public.json');
      if (!Array.isArray(graph.lgus)) throw new Error('Invalid registry');
      const registry = graph.lgus.filter(published);
      const id = new URLSearchParams(location.search).get('id');
      const lgu = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/.test(id || '') ? registry.find(row => row.id === id) : null;
      if (!lgu) { byId('status').replaceChildren(el('p', 'This profile is not available. Choose a published city or municipality.')); const a = el('a', 'Explore LGUs'); a.href = 'lgus.html'; byId('status').append(a); return; }
      byId('name').textContent = lgu.name; document.title = `${lgu.name} | Better Pangasinan`;
      byId('intro').textContent = 'Your community at a glance, with its local records and original sources.';
      const select = byId('selector'); select.replaceChildren();
      for (const row of registry) select.append(new Option(row.name, row.id, false, row.id === id));
      select.disabled = false;
      select.addEventListener('change', () => { location.href = `lgu.html?id=${encodeURIComponent(select.value)}${location.hash}`; });
      byId('status').hidden = true; host.hidden = false;
      const extra = await json(`data/lgu-profiles/${encodeURIComponent(lgu.id)}.json`, true);
      const model = aggregate(lgu, graph, extra);
      byId('optional-status').textContent = model.extra ? '' : 'Additional collections are unavailable; the registry and directly linked records are still shown.';
      for (const [label, value, note] of [
        ['Population', number(lgu.population), lgu.population_reference_date ? `Counted ${lgu.population_reference_date}` : 'Reference date not supplied'],
        ['Barangays', model.extra?.barangay_count == null ? 'Not available' : String(model.extra.barangay_count), 'Collected registry; source version applies'],
        ['LGU type', lgu.classification === 'city' ? 'City' : lgu.classification === 'municipality' ? 'Municipality' : 'Not supplied', 'From the published registry'],
        ['Local statistics', String(model.statistics.length), 'Published observations, not summed'],
      ]) { const card = el('div', undefined, 'lgu-kpi'); card.append(el('span', label), el('strong', value), el('small', note)); byId('kpis').append(card); }
      byId('overview').append(el('p', `${lgu.name} / ${lgu.classification || 'classification not supplied'}.`), el('p', lgu.population_reference_date ? `Population reference: ${lgu.population_reference_date}. Administrative listing: ${lgu.psgc_release || 'not supplied'}.` : 'Reference dates are not yet collected.', 'lgu-caption'));
      if (lgu.psgc) { const a = el('a', 'Open the full municipality map'); a.href = `municipality-map.html?psgc=${encodeURIComponent(lgu.psgc)}`; const p = el('p'); p.append(a); byId('overview').append(p); }
      let mapReady = Promise.resolve();
      if (lgu.psgc && window.createMunicipalityMap) mapReady = window.createMunicipalityMap({ container: byId('map'), mode: 'profile', selectedPsgc: lgu.psgc,
        onSelect: row => { if (row?.psgc && row.psgc !== lgu.psgc) location.href = `lgu.html?id=${encodeURIComponent(row.id)}`; } }).ready;
      else byId('map').textContent = 'A linked municipality geometry is not available.';
      renderStatistics(model); renderBarangays(model); renderFinances(model); renderProjects(model); renderGovernment(model); renderSources(model);
      function activeSection() {
        const name = location.hash || '#overview';
        for (const anchor of host.querySelectorAll('[data-local-section-nav] a')) {
          if (anchor.hash === name) anchor.setAttribute('aria-current', 'location'); else anchor.removeAttribute('aria-current');
        }
      }
      window.addEventListener('hashchange', activeSection); activeSection();
      Promise.resolve(mapReady).then(() => requestAnimationFrame(() => {
        const target = location.hash ? document.getElementById(location.hash.slice(1)) : null;
        if (target && host.contains(target)) target.scrollIntoView({ block: 'start' });
      }));
    } catch { byId('status').hidden = false; byId('status').replaceChildren(el('p', 'This profile could not be loaded. Return to the LGU Explorer or try again.')); host.hidden = true; }
  }
  init();
})();
