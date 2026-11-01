(() => {
  'use strict';
  const root = document.getElementById('transparency');
  if (!root) return;
  const status = (node, state, text) => {
    node.dataset.state = state;
    node.textContent = text;
  };
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  async function body(url) {
    const response = await fetch(url, { cache: 'no-cache' });
    if (!response.ok) throw new Error('Publication unavailable');
    return response.text();
  }
  async function budget() {
    const target = document.getElementById('tp-budget-status');
    try {
      const base = 'data/national-budget/2027/';
      const manifest = JSON.parse(await body(`${base}manifest.json`));
      if (!object(manifest) || !['approved', 'unavailable'].includes(manifest.status)) throw new Error('Invalid manifest');
      if (manifest.status === 'unavailable') {
        status(target, 'empty', 'No approved national budget snapshot is currently published. No funding conclusions can be drawn.');
        return;
      }
      if (typeof manifest.snapshot_id !== 'string' || !manifest.snapshot_id || typeof manifest.retrieved_at !== 'string') throw new Error('Missing snapshot identity');
      const [rows, offices, coverage, sources] = await Promise.all(['projects', 'offices', 'coverage', 'sources'].map(async name => {
        const expected = manifest.files?.[`${name}.json`];
        if (typeof expected !== 'string' || !/^[a-f0-9]{64}$/.test(expected)) throw new Error('Missing checksum');
        const text = await body(`${base}${name}.json`);
        const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
        const actual = [...new Uint8Array(hash)].map(byte => byte.toString(16).padStart(2, '0')).join('');
        if (actual !== expected) throw new Error('Checksum mismatch');
        return JSON.parse(text);
      }));
      if (!Array.isArray(rows) || !Array.isArray(offices) || !object(coverage) || !object(sources)) throw new Error('Invalid publication');
      const ids = new Set();
      for (const row of rows) {
        if (!object(row) || typeof row.id !== 'string' || !row.id || ids.has(row.id) || row.publication_status !== 'approved' || row.snapshot_id !== manifest.snapshot_id) throw new Error('Invalid published record');
        ids.add(row.id);
      }
      for (const item of [coverage, sources, ...offices]) {
        if (!object(item) || (item.snapshot_id !== undefined && item.snapshot_id !== manifest.snapshot_id)) throw new Error('Invalid metadata snapshot');
      }
      status(target, rows.length ? 'available' : 'empty', rows.length
        ? `${rows.length.toLocaleString('en-PH')} approved comparison records published. ${coverage.complete === true ? 'Configured collection queries are complete.' : 'Collection coverage is incomplete or not established.'} Exhaustive geographic coverage is not implied.`
        : 'Approved snapshot contains no published comparison records. No funding conclusions can be drawn.');
      const meta = document.getElementById('tp-budget-meta');
      meta.textContent = `Snapshot: ${manifest.snapshot_id}. Retrieved: ${manifest.retrieved_at}. A dated publication, not a live budget feed.`;
      meta.hidden = false;
      document.getElementById('tp-budget-provenance').hidden = false;
    } catch {
      status(target, 'unavailable', 'Budget availability could not be verified. Data may be unavailable or invalid; this is not evidence of zero funding. Consult the publication manifest.');
    }
  }
  async function local() {
    const targets = [...root.querySelectorAll('[data-local]')];
    try {
      const data = JSON.parse(await body('data/public.json'));
      if (!object(data)) throw new Error('Invalid dataset');
      for (const target of targets) {
        const names = target.dataset.local.split(',');
        if (names.some(name => !Array.isArray(data[name]) || data[name].some(row => !object(row)))) {
          status(target, 'unavailable', 'Availability could not be verified for this collection. No record count is assumed.');
          continue;
        }
        const count = names.reduce((total, name) => total + data[name].filter(row => row.is_mock === false && row.publication_status === 'approved').length, 0);
        status(target, count ? 'available' : 'empty', count
          ? `${count.toLocaleString('en-PH')} approved local ${count === 1 ? 'record' : 'records'} published.`
          : 'No approved local records are currently published in this collection. This is a portal coverage gap.');
      }
    } catch {
      for (const target of targets) status(target, 'unavailable', 'Local data availability could not be verified. No record count is assumed.');
    }
  }
  budget();
  local();
})();
