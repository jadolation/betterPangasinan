(() => {
  'use strict';
  const host = document.getElementById('budget-context'); if (!host) return;
  const output = document.getElementById('bc-content'), status = document.getElementById('bc-status');
  const node = (tag, text) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; return e; };
  const amount = x => x === null || x === undefined ? 'Unknown' : /^-?\d+$/.test(String(x)) ? BigInt(x).toLocaleString('en-PH') : String(x);
  function link(url, text) { const a = node('a', text); const u = new URL(url); if (u.protocol !== 'https:' || u.hostname !== 'budget.bettergov.ph') return node('span', 'Source URL unavailable'); a.href = u.href; a.rel = 'noopener noreferrer'; return a; }
  function table(parent, caption, headings, rows) { const wrap = node('div'); wrap.className = 'hb-scroll'; const t = node('table'); t.append(node('caption', caption)); const head = node('thead'), tr = node('tr'); headings.forEach(h => { const th = node('th', h); th.scope = 'col'; tr.append(th); }); head.append(tr); const body = node('tbody'); rows.forEach(values => { const r = node('tr'); values.forEach(v => r.append(node('td', v ?? 'Unknown'))); body.append(r); }); t.append(head, body); wrap.append(t); parent.append(wrap); }
  function provenance(parent, snapshot) { const p = node('p', `Retrieved ${snapshot.retrieved_at}; HTTP ${snapshot.status ?? 'unavailable'}. `); p.append(link(snapshot.source, 'Original API')); parent.append(p); }
  const titles = {nep_overview: 'FY2027 NEP national overview', nep_departments: 'FY2027 NEP departments', nep_dpwh: 'FY2027 NEP: whole DPWH department', nep_regions: 'FY2027 NEP regional context', budget_cycle_overview: 'Budget-cycle coverage: Current New Appropriations only', budget_cycle_dpwh: 'DPWH budget-cycle availability'};
  function context(data) {
    for (const [key, snapshot] of Object.entries(data.datasets)) {
      const section = node('section'); section.append(node('h2', titles[key] || key)); provenance(section, snapshot);
      if (snapshot.error) { section.append(node('p', `Unavailable: ${snapshot.error}. No zero amounts or execution results inferred.`)); output.append(section); continue; }
      const response = snapshot.response, d = response.data;
      section.append(node('p', `Source units: ${response.meta.currency || 'unspecified'} / ${response.meta.scale || response.meta.units || 'unspecified'}.`));
      if (key.startsWith('nep_')) {
        if (d.department) table(section, 'Whole department, not provincial funding', ['Department', 'FY2027 NEP proposal PHP', 'FY2026 GAA baseline PHP'], [[d.department.description, amount(d.department.amount), amount(d.department.base_amount)]]);
        if (d.national) table(section, 'National context, not Pangasinan', ['Stage / fiscal year', 'PHP'], [['FY2027 NEP proposal', amount(d.national.amount)], ['FY2026 GAA baseline', amount(d.national.base_amount)]]);
        const rows = Array.isArray(d) ? d : key === 'nep_overview' ? d.departments : d.regions;
        if (Array.isArray(rows)) table(section, key === 'nep_regions' ? 'All source regions; Region I is not Pangasinan' : 'Source overview rows, distinct budget versions', ['Name / code', 'FY2027 NEP proposal PHP', 'FY2026 GAA baseline PHP', 'Difference PHP'], rows.map(r => [r.description || r.name || r.code, amount(r.amount), amount(r.base_amount), amount(r.delta)]));
      } else {
        section.append(node('p', 'Current New Appropriations only, narrower than the main GAA series. Expense-class total rows overlap their components and must not be added to them. No cross-stage or cross-year sums.'));
        if (d.note) section.append(node('p', d.note));
        if (Array.isArray(d.subjects)) table(section, 'Subject-specific available years by stage', ['Subject', 'Department', 'Stage', 'Fiscal years'], d.subjects.flatMap(s => Object.entries(s.coverage || {}).map(([stage, years]) => [s.display_name, s.canonical_portal_department_id, stage, years.join(', ')])));
      }
      const details = node('details'); details.append(node('summary', 'Full source response, source metadata and scope')); details.append(node('pre', JSON.stringify(response, null, 2))); section.append(details); output.append(section);
    }
  }
  function hearings(data) {
    provenance(output, data); output.append(node('p', `${data.coverage.returned} topic matches for ${data.coverage.query}. ${data.coverage.complete ? 'Below the documented result cap.' : 'Incomplete or capped result set.'} ${data.coverage.pagination}.`));
    if (data.error) { output.append(node('p', `Hearing data unavailable: ${data.error}`)); return; }
    const rows = data.response.data;
    const form = node('form'), searchLabel = node('label', 'Search collected hearing topics'), search = node('input'); search.type = 'search'; searchLabel.append(search);
    const yearLabel = node('label', 'Fiscal year'), year = node('select'); year.append(new Option('All source fiscal years', '')); [...new Set(rows.map(r => String(r.hearing.fiscal_year)))].sort().forEach(y => year.append(new Option(y, y))); yearLabel.append(year);
    form.append(searchLabel, yearLabel); form.onsubmit = e => e.preventDefault(); output.append(form);
    const count = node('p'); count.setAttribute('role', 'status'); const results = node('div'); output.append(count, results);
    function render() {
      const filtered = rows.filter(r => (!year.value || String(r.hearing.fiscal_year) === year.value) && JSON.stringify(r).toLowerCase().includes(search.value.toLowerCase())); results.replaceChildren(); count.textContent = `${filtered.length} matching topics`;
      for (const row of filtered) {
        const h = row.hearing, t = row.topic, article = node('article'); article.append(node('h2', t.topic), node('p', `FY${h.fiscal_year} hearing / ${h.hearing_date} / ${h.agency || 'Agency unspecified'} / Source topic status: ${t.status}`), node('p', t.summary), node('p', `Reported outcome, not funding approval: ${t.outcome}`), link(t.url || h.page_url, `${h.title} / topic video`));
        for (const m of row.matching_moments || []) { const p = node('p', `${m.speaker || 'Speaker uncertain'}: ${m.said} `); p.append(link(m.url, `Verify at ${m.timestamp}`)); article.append(p); }
        results.append(article);
      }
    }
    form.addEventListener('input', render); render();
  }
  async function init() { try { const isHearings = host.dataset.context === 'hearings'; const response = await fetch(`data/budget-${isHearings ? 'hearings' : 'context'}.json`); if (!response.ok) throw Error(`HTTP ${response.status}`); const data = await response.json(); if (isHearings) hearings(data); else context(data); status.textContent = 'Reviewed local snapshot, not a live refresh. Sources and retrieval dates accompany each dataset.'; } catch (error) { output.replaceChildren(); status.textContent = `Data unavailable: ${error.message}. Missing data is not zero.`; } }
  init();
})();
