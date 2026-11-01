(() => {
  'use strict';
  const root = document.getElementById('national-budget');
  if (!root) return;
  const byId = id => document.getElementById(`nb-${id}`);
  const form = byId('filters');
  const money = value => value === null ? 'Unknown' : `PHP ${value.toLocaleString('en-PH')}`;
  const text = value => typeof value === 'string' ? value : JSON.stringify(value);
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
  let selected = [];
  let currentPage = 0;
  const pageSize = 25;
  let publishedRows = [];
  let manifest;
  let approvedOffices = [];
  const matchesScope = (row, scope) => !scope || scope === 'all' || row.scope === scope ||
    (scope === 'office' && row.inclusion_reasons.some(reason => reason && typeof reason === 'object' && reason.category === 'office'));
  function renderOffices(filters) {
    const target = byId('offices');
    target.hidden = filters.scope !== 'office';
    target.replaceChildren();
    if (target.hidden) return;
    target.append(element('h2', 'Approved office context'), element('p', 'Whole-office NEP covers a different scope from named-project House comparisons. Do not subtract district headlines or add co-served districts. The like-for-like figures below use upstream FY2027 named-project records, not whole-office NEP. These separately approved source-ledger aggregates are not recomputed from the filtered project cards.'));
    const offices = approvedOffices.filter(item => !filters.office || item.matched_label === filters.office);
    if (!offices.length) target.append(element('p', 'No approved office metadata matches this selection.'));
    for (const item of offices) {
      const card = element('article', undefined, 'card');
      const raw = item.upstream || {};
      const fy = raw.fy2027 || {};
      card.append(element('h3', item.matched_label), element('p', `Tier ${item.tier}. Serving districts: ${item.district_ids.join('; ')}. Office totals are not split between districts.`));
      card.append(element('p', `Co-served district context: ${(raw.co_served_districts || []).map(district => district.label || district.id).join('; ') || 'None listed'}.`));
      const whole = (raw.years || []).find(year => year.fy === 2027 && year.stage === 'nep' && year.matched_label === item.matched_label);
      card.append(element('p', `Whole-office NEP (context only): ${money(amount(whole?.php))}. Not used for named-project change.`));
      card.append(element('p', `FY2027 named-project NEP: ${money(amount(fy.nep_php))}; House third reading (hgab3): ${money(amount(fy.hgab3_php))}. Versions are compared, never added.`));
      if (typeof raw.tier_text === 'string') card.append(element('p', raw.tier_text));
      const details = element('details');
      details.append(element('summary', 'Original office comparison metadata'), element('pre', JSON.stringify(fy, null, 2)));
      card.append(details);
      target.append(card);
    }
  }
  function render(rows, resetPage = true) {
    if (resetPage) currentPage = 0;
    const filters = Object.fromEntries(new FormData(form));
    selected = rows.filter(row => matchesScope(row, filters.scope) &&
      (!filters.q || `${row.title} ${row.id} ${row.upstream_id}`.toLocaleLowerCase().includes(filters.q.trim().toLocaleLowerCase())) &&
      (!filters.lgu || row.lgu_associations.some(lgu => lgu.psgc === filters.lgu)) &&
      (!filters.dataset || row.dataset === filters.dataset) && (!filters.office || office(row) === filters.office) &&
      (!filters.status || row.source_review_status === filters.status) && (!filters.stage || row.house_stage === filters.stage) &&
      (!filters.comparison || comparison(row) === filters.comparison) && (!filters.geographic || row.geographic_review_status === filters.geographic));
    renderOffices(filters);
    selected.sort((a, b) => filters.sort === 'amount'
      ? (versions(b)[1] ?? -Infinity) - (versions(a)[1] ?? -Infinity) || a.id.localeCompare(b.id)
      : (filters.sort === 'id' ? a.upstream_id.localeCompare(b.upstream_id) : a.title.localeCompare(b.title)));
    byId('count').textContent = `${selected.length} budget comparison records. ${filters.scope === 'geographic' ? 'Reviewed geographic lens; not exhaustive coverage.' : 'Not a geographic allocation total.'}`;
    byId('export').disabled = !selected.length;
    byId('totals').replaceChildren();
    for (const stage of ['hgab2', 'hgab3']) {
      const group = selected.filter(row => row.house_stage === stage);
      if (!group.length) continue;
      const card = element('section', undefined, 'card');
      card.append(element('h3', `${stage === 'hgab2' ? 'House second reading' : 'House third reading'} (${stage})`));
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
    byId('results').replaceChildren();
    const pages = Math.ceil(selected.length / pageSize);
    currentPage = Math.max(0, Math.min(currentPage, pages - 1));
    byId('pagination').hidden = selected.length <= pageSize;
    byId('page-status').textContent = selected.length ? `Showing ${currentPage * pageSize + 1}-${Math.min((currentPage + 1) * pageSize, selected.length)} of ${selected.length}` : 'Showing 0 of 0';
    byId('previous').disabled = currentPage === 0;
    byId('next').disabled = currentPage + 1 >= pages;
    if (!selected.length) {
      const lguUnmatched = filters.lgu && !rows.some(row => row.lgu_associations.some(lgu => lgu.psgc === filters.lgu));
      byId('results').append(element('p', lguUnmatched ? 'No reviewed project matches are available for this LGU yet. This does not mean the LGU has no projects or funding.' : 'No filter matches. This does not mean the selected LGU has no projects or funding.', 'nb-empty'));
    }
    for (const row of selected.slice(currentPage * pageSize, (currentPage + 1) * pageSize)) {
      const card = element('article', undefined, 'card');
      card.append(element('p', `${row.dataset.toUpperCase()} · ${row.house_stage} · ${row.scope}`, 'nb-badge'), element('h3', row.title));
      const [nep, house] = versions(row);
      const dl = element('dl');
      for (const [label, value] of [['NEP proposal', money(nep)], [`House proposal (${row.house_stage})`, money(house)], ['Office', office(row) || 'Not supplied'], ['LGU associations', row.lgu_associations.map(lgu => `${lgu.name} (${lgu.psgc})`).join('; ') || 'No reviewed LGU match'], ['Source review', row.source_review_status], ['Geographic review', row.geographic_review_status]]) dl.append(element('dt', label), element('dd', value));
      card.append(dl, element('p', `Source review warning/status: ${row.source_review_status}. Publication approval does not clear upstream evidence flags.`, 'nb-warning'));
      card.append(element('p', `Comparison status: ${comparison(row)}${row.upstream.held ? ' (held)' : ''}. Source-supplied change: ${money(row.upstream.delta_php)}.${comparable(row) ? '' : ' Excluded from comparable-row change totals.'}`));
      if ((row.upstream.flags || []).includes('nep_evidence_review')) card.append(element('p', 'NEP evidence needs review: the source has flagged the proposal-side evidence for checking. The displayed comparison is not independently verified; publication approval does not resolve this warning.', 'nb-warning'));
      for (const version of ['nep', row.house_stage]) {
        const anchor = link(row.upstream.pdf_url?.[version], version === 'nep' ? 'Original NEP PDF' : `Original House PDF (${version})`);
        const p = element('p');
        if (anchor) p.append(anchor);
        else p.textContent = `${version === 'nep' ? 'NEP' : `House (${version})`} PDF: no valid HTTPS source link supplied.`;
        card.append(p);
      }
      if (row.scope === 'shared') card.append(element('p', 'Shared umbrella allocation: no Pangasinan share is inferred.', 'nb-warning'));
      const details = element('details');
      details.append(element('summary', 'Evidence, original fields and identifiers'));
      details.append(element('p', `Record ${row.id}; original ID ${row.upstream_id}; snapshot ${manifest.snapshot_id}; SHA-256 ${row.record_sha256}`));
      details.append(element('p', `Inclusion reasons: ${row.inclusion_reasons.map(text).join('; ')}`));
      sourceLinks(row.upstream, details);
      details.append(element('pre', JSON.stringify(row.upstream, null, 2)));
      details.append(element('pre', JSON.stringify(row.lgu_associations, null, 2)));
      card.append(details);
      byId('results').append(card);
    }
  }
  for (const [name, direction] of [['previous', -1], ['next', 1]]) {
    byId(name).addEventListener('click', () => {
      currentPage += direction;
      render(publishedRows, false);
    });
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
        return;
      }
      if (typeof manifest.snapshot_id !== 'string' || !manifest.snapshot_id || typeof manifest.retrieved_at !== 'string') throw new Error('Missing snapshot identity');
      const [rows, offices, coverage, sources] = await Promise.all(['projects', 'offices', 'coverage', 'sources'].map(load));
      validate(rows);
      publishedRows = rows;
      if (!Array.isArray(offices) || !coverage || Array.isArray(coverage) || typeof coverage !== 'object' || !sources || Array.isArray(sources) || typeof sources !== 'object') throw new Error('Invalid metadata');
      for (const item of [coverage, sources, ...offices]) if (item.snapshot_id !== undefined && item.snapshot_id !== manifest.snapshot_id) throw new Error('Mismatched metadata snapshot');
      if (offices.some(item => !item || typeof item.matched_label !== 'string' || !['A', 'B'].includes(item.tier) || !Array.isArray(item.district_ids) || !item.upstream)) throw new Error('Invalid office metadata');
      approvedOffices = offices;
      const coverageSummary = byId('coverage-summary');
      coverageSummary.append(element('h2', coverage.complete === true ? 'Collection coverage' : 'Incomplete collection coverage'));
      coverageSummary.append(element('p', `${rows.length} approved comparison records. ${coverage.complete === true ? 'Configured collection queries are complete.' : 'Some collection work is incomplete or deferred; these figures are not a complete provincial inventory.'} ${coverage.exhaustive_geographic_coverage === true ? 'See the exact approved coverage below.' : 'Exhaustive geographic coverage has not been established.'}`));
      for (const limitation of coverage.limitations || []) if (typeof limitation === 'string') coverageSummary.append(element('p', limitation));
      byId('meta').append(element('p', `Snapshot: ${manifest.snapshot_id}. Retrieved: ${manifest.retrieved_at}. This is a dated snapshot, not a live budget feed.`));
      byId('coverage').textContent = JSON.stringify(coverage, null, 2);
      byId('sources').textContent = JSON.stringify(sources, null, 2);
      sourceLinks(sources, byId('source-links'));
      const populate = (name, values) => [...new Set(values.filter(Boolean))].sort().forEach(value => form.elements[name].append(new Option(value, value)));
      populate('dataset', ['dpwh', 'fmr', 'hfep', 'nia']);
      populate('office', [...rows.map(office), ...offices.map(item => item.matched_label)]);
      populate('status', rows.map(row => row.source_review_status));
      populate('comparison', rows.map(comparison));
      populate('geographic', rows.map(row => row.geographic_review_status));
      const registry = sources.lgu_registry || [];
      if (!Array.isArray(registry) || registry.some(lgu => typeof lgu.psgc !== 'string' || typeof lgu.name !== 'string')) throw new Error('Invalid reviewed registry');
      const lgus = new Map([...registry.map(lgu => [lgu.psgc, lgu.name]), ...rows.flatMap(row => row.lgu_associations.map(lgu => [lgu.psgc, lgu.name]))]);
      [...lgus].sort((a, b) => a[1].localeCompare(b[1])).forEach(([psgc, name]) => form.elements.lgu.append(new Option(name, psgc)));
      form.addEventListener('submit', event => { event.preventDefault(); render(rows); });
      form.addEventListener('input', () => render(rows));
      form.addEventListener('change', () => render(rows));
      form.addEventListener('reset', () => setTimeout(() => render(rows), 0));
      byId('status').textContent = rows.length ? 'Approved snapshot loaded. Source and geographic review statuses remain independent.' : 'Approved snapshot contains no published comparison records. No funding conclusions can be drawn.';
      byId('content').hidden = false;
      render(rows);
    } catch {
      byId('content').hidden = true;
      byId('status').textContent = 'Budget data unavailable or invalid. No approved figures can be displayed; this is not evidence of zero funding. Please consult the publication manifest.';
    }
  }
  init();
})();
