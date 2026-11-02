/* Offline, source-bound GAA snapshot. BigInt keeps annual PHP and CSV exact. */
(() => {
  'use strict';
  const host = document.getElementById('historical-budget');
  if (!host) return;
  const el = id => document.getElementById(`hb-${id}`);
  const node = (tag, text) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; return n; };
  const money = value => value === null || value === undefined ? 'Unknown' : BigInt(value).toLocaleString('en-PH');
  const cell = value => {
    let s = value === null || value === undefined ? '' : String(value);
    if (/^[\s]*[=+\-@\t\r]/.test(s)) s = `'${s}`;
    return `"${s.replace(/"/g, '""')}"`;
  };
  const sourceLink = url => { const a = node('a', 'API source'); const u = new URL(url); if (u.protocol !== 'https:' || u.hostname !== 'budget.bettergov.ph') throw Error('Invalid source URL'); a.href = u.href; a.rel = 'noopener noreferrer'; return a; };
  async function get(path) { const r = await fetch(path); if (!r.ok) throw Error(`${path}: HTTP ${r.status}`); return r.json(); }
  let rows, years, departments, selected = [], page = 0;
  const size = 50;
  function render() {
    const year = el('year').value;
    selected = rows.filter(r => (!el('department').value || r.department_id === el('department').value) && (!el('query').value || r.queries.includes(el('query').value)) && r.name.toLowerCase().includes(el('search').value.trim().toLowerCase()));
    el('count').textContent = `${selected.length.toLocaleString()} matching program families. Zero and unknown amounts remain visible.`;
    el('caption').textContent = `FY${year} enacted GAA appropriations, PHP`;
    const totals = years.map(y => {
      let total = 0n, known = 0, positive = 0;
      for (const r of selected) { const amount = r.years[y]?.amount; if (amount !== null && amount !== undefined) { const v = BigInt(amount); total += v; known++; if (v > 0n) positive++; } }
      return { year: y, total, known, positive, unknown: selected.length - known };
    });
    const max = totals.reduce((a, t) => t.total > a ? t.total : a, 0n);
    el('annual').replaceChildren(); el('chart').replaceChildren();
    for (const t of totals) {
      const tr = node('tr');
      [t.year, t.known ? money(t.total) : (selected.length ? 'Unknown' : 'No matching families'), t.positive, `${t.known} / ${selected.length}`, t.unknown].forEach(v => tr.append(node('td', v)));
      el('annual').append(tr);
      const barRow = node('div'); barRow.className = 'hb-bar-row'; barRow.setAttribute('aria-hidden', 'true');
      const bar = node('div'); bar.className = 'hb-bar'; bar.style.width = `${max > 0n ? Number(t.total * 10000n / max) / 100 : 0}%`; bar.title = `FY${t.year}: ${t.known ? money(t.total) : 'Unknown'} PHP`;
      barRow.append(node('span', t.year), bar); el('chart').append(barRow);
    }
    const pages = Math.max(1, Math.ceil(selected.length / size)); page = Math.min(page, pages - 1);
    el('page').textContent = `Page ${page + 1} of ${pages}`; el('prev').disabled = page === 0; el('next').disabled = page >= pages - 1;
    el('rows').replaceChildren();
    for (const r of selected.slice(page * size, (page + 1) * size)) {
      const tr = node('tr'), name = node('td', r.name); name.className = 'hb-name';
      const identity = node('details'); identity.append(node('summary', 'Family identifier'), node('small', r.key)); name.append(identity);
      const amount = node('td', money(r.years[year]?.amount)); amount.className = 'hb-amount';
      const source = node('td'); source.append(sourceLink(r.sources[0]));
      const evidence = node('details'); evidence.append(node('summary', 'Collected queries and source links'), node('p', r.queries.join('; ')));
      for (const url of r.sources) evidence.append(sourceLink(url), node('br'));
      source.append(evidence);
      tr.append(name, node('td', `${departments.get(r.department_id)} / ${r.agency_id}`), amount, source); el('rows').append(tr);
    }
  }
  async function init() {
    try {
      const [manifest, deps, programs, coverage] = await Promise.all(['manifest', 'departments', 'programs', 'coverage'].map(n => get(`data/historical-budget/${n}.json`)));
      if (manifest.stage !== 'enacted_appropriations' || manifest.scale !== 'pesos' || manifest.review?.status !== 'approved' || manifest.years.join(',') !== '2020,2021,2022,2023,2024,2025,2026') throw Error('Invalid reviewed snapshot');
      rows = programs.data; years = programs.years; departments = new Map(deps.data.map(d => [d.id, d.description]));
      for (const y of years) el('year').append(new Option(y, y)); el('year').value = '2026';
      for (const [id, name] of departments) el('department').append(new Option(name, id));
      for (const q of [...new Set(coverage.data.map(r => r.query))].sort()) el('query').append(new Option(q, q));
      for (const c of coverage.data) {
        const tr = node('tr'); [departments.get(c.department_id), c.query, c.matched ?? 'Unknown', c.fetched, c.complete ? 'Exhausted and reconciled' : `Incomplete: ${c.error || 'count or cursor gap'}`].forEach(v => tr.append(node('td', v))); el('coverage').append(tr);
      }
      el('coverage-summary').textContent = `${coverage.data.length} department/query attempts; ${coverage.data.filter(c => c.complete).length} exhausted and count-reconciled. ${manifest.programs} deduplicated families. Optional LGU batches are not assumed collected.`;
      el('sources').textContent = JSON.stringify({ review: manifest.review, sources: manifest.sources, limitations: manifest.limitations, source_commit_note: manifest.source_commit_note }, null, 2);
      el('status').textContent = `Locally reviewed snapshot; retrieved ${manifest.sources.map(s => s.retrieved_at).sort()[0].slice(0, 10)}. ${manifest.complete ? 'All attempted GAA queries exhausted.' : 'Collection is incomplete; see coverage.'}`;
      el('filters').addEventListener('input', () => { page = 0; render(); });
      el('filters').addEventListener('submit', e => e.preventDefault());
      el('filters').addEventListener('reset', () => setTimeout(() => { el('year').value = '2026'; page = 0; render(); }, 0));
      el('prev').onclick = () => { page--; render(); }; el('next').onclick = () => { page++; render(); };
      el('csv').onclick = () => {
        const header = ['department_id', 'agency_id', 'program', ...years.map(y => `gaa_${y}_php`), 'queries', 'family_key', 'source'];
        const values = selected.map(r => [r.department_id, r.agency_id, r.name, ...years.map(y => r.years[y]?.amount), r.queries.join('; '), r.key, r.sources.join('; ')]);
        const csv = [header, ...values].map(r => r.map(cell).join(',')).join('\r\n') + '\r\n';
        const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })); const a = node('a'); a.href = url; a.download = 'gaa-2020-2026-filtered.csv'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      };
      render(); el('content').hidden = false;
    } catch (error) { el('content').hidden = true; el('status').textContent = `Historical data unavailable: ${error.message}. Missing API or publication data is not zero.`; }
  }
  init();
})();
