(() => {
  'use strict';
  const root = document.getElementById('national-budget');
  if (!root) return;
  const byId = id => document.getElementById(`nb-${id}`);
  const form = byId('filters');
  const money = value => value === null ? 'Unknown' : `PHP ${value.toLocaleString('en-PH')}`;
  const element = (tag, value, className) => {
    const node = document.createElement(tag);
    if (value !== undefined) node.textContent = value;
    if (className) node.className = className;
    return node;
  };
  const amount = value => Number.isSafeInteger(value) ? value : null;
  const office = row => row.upstream.office || '';
  const versions = row => [amount(row.upstream.nep_php), amount(row.upstream[`${row.house_stage}_php`])];
  const comparable = row => !row.upstream.held && row.upstream.bridge_group !== 'scope_review';
  const comparison = row => [row.upstream.bridge_group, row.upstream.status_label].filter(Boolean).join(' / ') || 'Not supplied';
  function link(url, label) {
    try {
      const parsed = new URL(url);
      if (parsed.protocol !== 'https:' || parsed.username || parsed.password) return null;
      const node = element('a', label);
      node.href = parsed.href;
      node.rel = 'noopener noreferrer';
      return node;
    } catch { return null; }
  }
  function sourceLinks(value, target) {
    if (!value || typeof value !== 'object') return;
    Object.entries(value).forEach(([key, item]) => {
      if (typeof item === 'string' && (/url$/i.test(key) || /^https:\/\//.test(item))) {
        const anchor = link(item, key);
        if (anchor) { const p = element('p'); p.append(anchor); target.append(p); }
      } else if (item && typeof item === 'object') sourceLinks(item, target);
    });
  }
  async function load(name) {
    const response = await fetch(`data/national-budget/2027/${name}.json`, { cache: 'no-cache' });
    if (!response.ok) throw new Error(`Unable to load ${name}`);
    const body = await response.text();
    if (name !== 'manifest') {
      const expected = manifest.files?.[`${name}.json`];
      if (typeof expected !== 'string' || !/^[a-f0-9]{64}$/.test(expected)) throw new Error('Missing publication checksum');
      const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(body));
      const actual = [...new Uint8Array(hash)].map(byte => byte.toString(16).padStart(2, '0')).join('');
      if (actual !== expected) throw new Error('Publication files do not match the manifest');
    }
    return JSON.parse(body);
  }
  function validate(rows) {
    const ids = new Set();
    if (!Array.isArray(rows)) throw new Error('Invalid record list');
    for (const row of rows) {
      if (!row || typeof row.id !== 'string' || ids.has(row.id) || typeof row.title !== 'string' ||
          typeof row.dataset !== 'string' || typeof row.upstream_id !== 'string' ||
          !Object.hasOwn({ dpwh: 'hgab3', fmr: 'hgab2', hfep: 'hgab2', nia: 'hgab2' }, row.dataset) ||
          ({ dpwh: 'hgab3', fmr: 'hgab2', hfep: 'hgab2', nia: 'hgab2' })[row.dataset] !== row.house_stage ||
          row.publication_status !== 'approved' || row.snapshot_id !== manifest.snapshot_id ||
          !['geographic', 'office', 'shared', 'uncertain'].includes(row.scope) ||
          !row.upstream || typeof row.upstream !== 'object' ||
          !Array.isArray(row.lgu_associations) || row.lgu_associations.some(lgu => typeof lgu.psgc !== 'string' || typeof lgu.name !== 'string') ||
          typeof row.record_sha256 !== 'string' || typeof row.source_review_status !== 'string' ||
          typeof row.geographic_review_status !== 'string' || !Array.isArray(row.inclusion_reasons)) throw new Error('Invalid comparison record');
      for (const key of ['nep_php', 'hgab2_php', 'hgab3_php', 'house_php', 'api_php', 'delta_php']) {
        const value = row.upstream[key];
        if (!Object.hasOwn(row.upstream, key) || (value !== null && (!Number.isSafeInteger(value) || (key !== 'delta_php' && value < 0)))) throw new Error('Unsafe or missing monetary value');
      }
      if (row.upstream.house_php !== row.upstream[`${row.house_stage}_php`]) throw new Error('House amount does not match stage');
      if (row.upstream.office !== undefined && row.upstream.office !== null && typeof row.upstream.office !== 'string') throw new Error('Invalid office');
      ids.add(row.id);
    }
  }
  function sum(values) {
    const known = values.filter(value => value !== null);
    if (!known.length) return { value: null, count: 0 };
    const total = known.reduce((a, b) => a + BigInt(b), 0n);
    return { value: total <= BigInt(Number.MAX_SAFE_INTEGER) && total >= BigInt(Number.MIN_SAFE_INTEGER) ? Number(total) : null, count: known.length };
  }
  function summary(label, values) {
    const total = sum(values);
    return `${label}: ${money(total.value)} (${total.count}/${values.length} known${total.value === null && total.count ? '; sum outside safe integer range' : ''})`;
  }
  const presentation = window.BudgetViews({ element, money, amount, office, versions, comparable, comparison, link, sourceLinks });
  const groups = { house_only: 'House bill only', nep_only: 'NEP only', unchanged: 'Unchanged', increased: 'Increased', decreased: 'Decreased', other: 'Other / uncertain' };
  const groupKey = row => Object.hasOwn(groups, row.upstream.bridge_group) ? row.upstream.bridge_group : 'other';
  const matchesScope = (row, scope) => !scope || scope === 'all' || row.scope === scope ||
    (scope === 'office' && row.inclusion_reasons.some(reason => reason && typeof reason === 'object' && reason.category === 'office'));
  let selected = [];
  let currentPage = 0;
  const pageSize = 25;
  let publishedRows = [];
  let publicationReady = false;
  let manifest;
  let dialogTrigger;

  function showEvidence(row, trigger) {
    dialogTrigger = trigger;
    byId('record-detail').replaceChildren(presentation.evidence(row, manifest));
    byId('record-dialog').showModal();
    byId('close-dialog').focus();
  }
  byId('close-dialog').addEventListener('click', () => byId('record-dialog').close());
  byId('record-dialog').addEventListener('close', () => {
    if (dialogTrigger?.isConnected) dialogTrigger.focus();
    else if (!document.getElementById('projects').hidden) byId('search').focus();
  });
  function setView(focus = false) {
    if (byId('record-dialog').open) byId('record-dialog').close();
    const view = ['projects', 'offices', 'about-data'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'projects';
    for (const section of root.querySelectorAll('[data-budget-view]')) section.hidden = section.dataset.budgetView !== view;
    for (const anchor of root.querySelectorAll('.tp-nav a')) {
      if (anchor.hash === `#${view}`) anchor.setAttribute('aria-current', 'page');
      else anchor.removeAttribute('aria-current');
    }
    if (focus) {
      const target = document.getElementById(view);
      const heading = target.querySelector('h2');
      if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
      target.scrollIntoView({ block: 'start' });
    }
  }
  window.addEventListener('hashchange', () => setView(true));
  setView();
  byId('advanced-toggle').addEventListener('click', () => {
    const panel = byId('advanced');
    panel.hidden = !panel.hidden;
    byId('advanced-toggle').setAttribute('aria-expanded', String(!panel.hidden));
  });
  function renderSnapshotSummary(rows) {
    byId('summary').replaceChildren();
    const reviewed = rows.filter(row => row.geographic_review_status === 'reviewed').length;
    for (const [label, value, definition] of [
      ['Published records', rows.length, 'Unique comparison identifiers'],
      ['House 3rd reading', rows.filter(row => row.house_stage === 'hgab3').length, 'DPWH comparison records'],
      ['House 2nd reading', rows.filter(row => row.house_stage === 'hgab2').length, 'FMR, health and irrigation records'],
      ['Geographic review', `${reviewed} / ${rows.length}`, 'Records marked reviewed, not exhaustive location coverage'],
    ]) {
      const card = element('div', undefined, 'tp-kpi');
      card.append(element('span', label), element('strong', String(value)), element('small', definition));
      byId('summary').append(card);
    }
    byId('comparisons').replaceChildren();
    for (const stage of ['hgab3', 'hgab2']) {
      const records = rows.filter(row => row.house_stage === stage);
      if (!records.length) continue;
      const section = element('section', undefined, 'nb-comparison-stage');
      section.append(element('h3', `${stage === 'hgab3' ? 'House third reading' : 'House second reading'} / ${records.length} records`));
      const grid = element('div', undefined, 'nb-category-grid');
      for (const [key, label] of Object.entries(groups)) {
        const button = element('button', undefined, 'nb-category');
        button.type = 'button'; button.dataset.group = key; button.dataset.stage = stage;
        button.setAttribute('aria-pressed', 'false');
        button.append(element('span', label), element('strong', String(records.filter(row => groupKey(row) === key).length)));
        button.addEventListener('click', () => {
          form.elements.comparison.value = `group:${key}`;
          form.elements.stage.value = stage;
          render(publishedRows);
        });
        grid.append(button);
      }
      section.append(grid); byId('comparisons').append(section);
    }
  }
  const filterNames = { q: 'Search', dataset: 'Program', comparison: 'Comparison', scope: 'Scope', lgu: 'LGU', office: 'Office', status: 'Source review', geographic: 'Geographic review', stage: 'Reading', sort: 'Sort' };
  function hydrateFilters() {
    const params = new URLSearchParams(location.search);
    for (const name of Object.keys(filterNames)) {
      const field = form.elements[name];
      const isSelect = field.tagName === 'SELECT';
      const fallback = isSelect ? ([...field.options].find(option => option.defaultSelected) || field.options[0]).value : field.defaultValue;
      const value = params.get(name);
      field.value = value !== null && (!isSelect || [...field.options].some(option => option.value === value)) ? value : fallback;
    }
  }
  window.addEventListener('popstate', () => {
    if (!publicationReady) return;
    hydrateFilters();
    render(publishedRows);
    setView();
  });
  function render(rows) {
    currentPage = 0;
    const filters = Object.fromEntries(new FormData(form));
    selected = rows.filter(row => matchesScope(row, filters.scope) &&
      (!filters.q || `${row.title} ${row.id} ${row.upstream_id} ${row.dataset} ${office(row)} ${row.upstream.program || ''}`.toLocaleLowerCase().includes(filters.q.trim().toLocaleLowerCase())) &&
      (!filters.lgu || row.lgu_associations.some(lgu => lgu.psgc === filters.lgu)) &&
      (!filters.dataset || row.dataset === filters.dataset) && (!filters.office || office(row) === filters.office) &&
      (!filters.status || row.source_review_status === filters.status) && (!filters.stage || row.house_stage === filters.stage) &&
      (!filters.comparison || (filters.comparison.startsWith('group:') ? groupKey(row) === filters.comparison.slice(6) : comparison(row) === filters.comparison)) && (!filters.geographic || row.geographic_review_status === filters.geographic));
    selected.sort((a, b) => filters.sort === 'amount'
      ? (versions(b)[1] ?? -Infinity) - (versions(a)[1] ?? -Infinity) || a.id.localeCompare(b.id)
      : (filters.sort === 'id' ? a.upstream_id.localeCompare(b.upstream_id) : a.title.localeCompare(b.title)));
    byId('count').textContent = `${selected.length} budget comparison records. ${filters.scope === 'geographic' ? 'Reviewed geographic lens; not exhaustive coverage.' : 'Not a geographic allocation total.'}`;
    byId('export').disabled = !selected.length;
    const active = Object.entries(filters).filter(([key, value]) => value && !(key === 'scope' && value === 'all') && !(key === 'sort' && value === 'title'));
    byId('active-filters').textContent = active.length ? active.map(([key, value]) => `${filterNames[key]}: ${form.elements[key].selectedOptions?.[0]?.textContent || value}`).join(' / ') : 'No active filters.';
    const advancedCount = active.filter(([key]) => ['scope', 'lgu', 'office', 'status', 'geographic', 'stage'].includes(key)).length;
    byId('advanced-toggle').textContent = `Advanced filters${advancedCount ? ` (${advancedCount} active)` : ''}`;
    for (const button of byId('comparisons').querySelectorAll('button')) button.setAttribute('aria-pressed', String(filters.comparison === `group:${button.dataset.group}` && filters.stage === button.dataset.stage));
    const url = new URL(location.href);
    for (const key of Object.keys(filterNames)) {
      if (active.some(([name]) => name === key)) url.searchParams.set(key, filters[key]);
      else url.searchParams.delete(key);
    }
    history.replaceState(null, '', url);
    byId('totals').replaceChildren();
    for (const stage of ['hgab2', 'hgab3']) {
      const group = selected.filter(row => row.house_stage === stage);
      if (!group.length) continue;
      const card = element('section', undefined, 'card');
      card.append(element('h3', `${stage === 'hgab2' ? 'House second reading' : 'House third reading'}`));
      card.append(element('p', `${group.length} records; ${filters.scope === 'geographic' ? 'geographic-match amounts' : 'selected scope amounts, not attributable provincial funding'}.`));
      const pairs = group.map(versions);
      card.append(element('p', summary('NEP proposal', pairs.map(pair => pair[0]))));
      card.append(element('p', summary('House proposal', pairs.map(pair => pair[1]))));
      card.append(element('p', summary('Comparable-row change', group.map(row => {
        const [nep, house] = versions(row);
        return comparable(row) && nep !== null && house !== null ? amount(house - nep) : null;
      }))));
      byId('totals').append(card);
    }
    renderResults(rows);
  }
  function renderResults(rows) {
    const body = byId('results').querySelector('tbody');
    body.replaceChildren();
    const pages = Math.ceil(selected.length / pageSize);
    currentPage = Math.max(0, Math.min(currentPage, pages - 1));
    byId('pagination').hidden = selected.length <= pageSize;
    byId('page-status').textContent = selected.length ? `Showing ${currentPage * pageSize + 1}-${Math.min((currentPage + 1) * pageSize, selected.length)} of ${selected.length}` : 'Showing 0 of 0';
    byId('previous').disabled = currentPage === 0;
    byId('next').disabled = currentPage + 1 >= pages;
    byId('empty').hidden = selected.length !== 0;
    byId('results').hidden = !selected.length;
    if (!selected.length) {
      const filters = Object.fromEntries(new FormData(form));
      const lguUnmatched = filters.lgu && !rows.some(row => row.lgu_associations.some(lgu => lgu.psgc === filters.lgu));
      byId('empty').textContent = lguUnmatched ? 'No reviewed project matches are available for this LGU yet. This does not mean the LGU has no projects or funding.' : 'No filter matches. This does not mean the selected LGU has no projects or funding.';
    }
    for (const row of selected.slice(currentPage * pageSize, (currentPage + 1) * pageSize)) body.append(presentation.projectRow(row, showEvidence));
  }
  for (const [name, direction] of [['previous', -1], ['next', 1]]) {
    byId(name).addEventListener('click', () => { currentPage += direction; renderResults(publishedRows); });
  }
  function csvCell(value) {
    let output = value === null || value === undefined ? '' : String(value);
    // Spreadsheet parsers may ignore leading spaces and control characters.
    if (/^[\s\u0000-\u001f\u007f]*[=+\-@]/.test(output)) output = `'${output}`;
    return `"${output.replace(/"/g, '""')}"`;
  }
  byId('export').addEventListener('click', () => {
    const header = ['snapshot_id', 'id', 'dataset', 'upstream_id', 'title', 'house_stage', 'scope', 'lgu_psgc', 'office', 'nep', 'house', 'source_delta', 'source_review_status', 'geographic_review_status', 'record_sha256'];
    const csv = [header, ...selected.map(row => [manifest.snapshot_id, row.id, row.dataset, row.upstream_id, row.title, row.house_stage, row.scope, row.lgu_associations.map(lgu => lgu.psgc).join(';'), office(row), ...versions(row), row.upstream.delta_php, row.source_review_status, row.geographic_review_status, row.record_sha256])].map(row => row.map(csvCell).join(',')).join('\r\n');
    const url = URL.createObjectURL(new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8' }));
    const anchor = element('a');
    anchor.href = url;
    anchor.download = 'national-budget-2027-filtered.csv';
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  async function init() {
    byId('status').textContent = 'Loading publication manifest. No approved figures are assumed.';
    try {
      manifest = await load('manifest');
      if (!manifest || !['approved', 'unavailable'].includes(manifest.status)) throw new Error('Invalid manifest');
      byId('meta').append(element('p', typeof manifest.notice === 'string' ? manifest.notice : 'Coverage is limited to explicitly approved records.'));
      for (const notice of Array.isArray(manifest.disclaimers) ? manifest.disclaimers : []) {
        const block = element('aside', undefined, 'nb-warning');
        if (typeof notice === 'string') block.append(element('p', notice));
        else if (notice && typeof notice === 'object') {
          if (typeof notice.title === 'string') block.append(element('h3', notice.title));
          if (typeof notice.body === 'string') block.append(element('p', notice.body));
          const anchor = link(notice.url, 'Read source notice');
          if (anchor) block.append(anchor);
        }
        byId('meta').append(block);
      }
      if (manifest.status === 'unavailable') {
        byId('status').textContent = 'No approved national budget snapshot is available. No provincial or municipal totals are inferred.';
        byId('asof').textContent = 'Publication unavailable / FY2027';
        return;
      }
      if (typeof manifest.snapshot_id !== 'string' || !manifest.snapshot_id || typeof manifest.retrieved_at !== 'string') throw new Error('Missing snapshot identity');
      const [rows, offices, coverage, sources] = await Promise.all(['projects', 'offices', 'coverage', 'sources'].map(load));
      validate(rows);
      publishedRows = rows;
      if (!Array.isArray(offices) || !coverage || Array.isArray(coverage) || typeof coverage !== 'object' || !sources || Array.isArray(sources) || typeof sources !== 'object') throw new Error('Invalid metadata');
      for (const item of [coverage, sources, ...offices]) if (item.snapshot_id !== undefined && item.snapshot_id !== manifest.snapshot_id) throw new Error('Mismatched metadata snapshot');
      if (offices.some(item => !item || typeof item.matched_label !== 'string' || !['A', 'B'].includes(item.tier) || !Array.isArray(item.district_ids) || !item.upstream)) throw new Error('Invalid office metadata');
      const coverageSummary = byId('coverage-summary');
      coverageSummary.replaceChildren(element('h3', coverage.complete === true ? 'Collection coverage' : 'Incomplete collection coverage'));
      coverageSummary.append(element('p', `${rows.length} approved comparison records. ${coverage.complete === true ? 'Configured collection queries are complete.' : 'Some collection work is incomplete or deferred; these figures are not a complete provincial inventory.'} ${coverage.exhaustive_geographic_coverage === true ? 'See the exact approved coverage below.' : 'Exhaustive geographic coverage has not been established.'}`));
      for (const limitation of coverage.limitations || []) if (typeof limitation === 'string') coverageSummary.append(element('p', limitation));
      if (coverage.complete !== true) {
        byId('collection-warning').textContent = 'Collection is incomplete or not established; these records are not a complete provincial inventory.';
        byId('collection-warning').hidden = false;
      }
      byId('snapshot-description').textContent = `Snapshot: ${manifest.snapshot_id}. Retrieved: ${manifest.retrieved_at}. This is a dated snapshot, not a live budget feed.`;
      byId('asof').textContent = `Approved publication / Retrieved ${manifest.retrieved_at.slice(0, 10)} UTC`;
      byId('coverage').textContent = JSON.stringify(coverage, null, 2);
      byId('sources').textContent = JSON.stringify(sources, null, 2);
      sourceLinks(sources, byId('source-links'));
      const populate = (name, values) => [...new Set(values.filter(Boolean))].sort().forEach(value => form.elements[name].append(new Option(name === 'office' ? value : presentation.human(value), value)));
      populate('dataset', ['dpwh', 'fmr', 'hfep', 'nia']);
      populate('office', [...rows.map(office), ...offices.map(item => item.matched_label)]);
      populate('status', rows.map(row => row.source_review_status));
      for (const value of [...new Set(rows.map(comparison))].sort()) byId('source-comparisons').append(new Option(presentation.comparisonLabel(value), value));
      populate('geographic', rows.map(row => row.geographic_review_status));
      const registry = sources.lgu_registry || [];
      if (!Array.isArray(registry) || registry.some(lgu => typeof lgu.psgc !== 'string' || typeof lgu.name !== 'string')) throw new Error('Invalid reviewed registry');
      const lgus = new Map([...registry.map(lgu => [lgu.psgc, lgu.name]), ...rows.flatMap(row => row.lgu_associations.map(lgu => [lgu.psgc, lgu.name]))]);
      [...lgus].sort((a, b) => a[1].localeCompare(b[1])).forEach(([psgc, name]) => form.elements.lgu.append(new Option(name, psgc)));
      hydrateFilters();
      form.addEventListener('submit', event => { event.preventDefault(); render(rows); });
      form.addEventListener('input', event => { if (event.target.name === 'q') render(rows); });
      form.addEventListener('change', event => { if (event.target.tagName === 'SELECT') render(rows); });
      form.addEventListener('reset', () => setTimeout(() => render(rows), 0));
      byId('status').textContent = rows.length ? `Approved snapshot loaded / ${rows.length} published records. Publication does not verify location.` : 'Approved snapshot contains no published comparison records. No funding conclusions can be drawn.';
      renderSnapshotSummary(rows);
      byId('offices').replaceChildren();
      for (const item of offices) byId('offices').append(presentation.officeCard(item, rows, matchesScope));
      if (!offices.length) byId('offices').append(element('p', 'No approved office metadata is available in this snapshot.'));
      byId('offices').hidden = false;
      byId('content').hidden = false;
      render(rows);
      publicationReady = true;
      if (['#projects', '#offices', '#about-data'].includes(location.hash)) {
        requestAnimationFrame(() => document.getElementById(location.hash.slice(1)).scrollIntoView({ block: 'start' }));
      }
    } catch {
      byId('content').hidden = true;
      byId('offices').hidden = true;
      byId('asof').textContent = 'Publication unavailable / FY2027';
      byId('status').textContent = 'Budget data unavailable or invalid. No approved figures can be displayed; this is not evidence of zero funding. Please consult the publication manifest.';
    }
  }
  init();
})();
