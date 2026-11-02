(() => {
  'use strict';
  const root = document.getElementById('transparency-snapshot');
  if (!root) return;
  const count = value => Number.isSafeInteger(value) && value >= 0;
  function metric(name, value, label) {
    const node = document.querySelector(`[data-home-metric="${name}"]`);
    if (node && count(value)) {
      const figure = document.createElement('strong'); figure.textContent = value.toLocaleString('en-PH');
      const caption = document.createElement('span'); caption.textContent = label;
      node.replaceChildren(figure, document.createTextNode(' '), caption); node.hidden = false;
    }
  }
  fetch('data/home-snapshot.json').then(response => { if (!response.ok) throw new Error('Unavailable'); return response.json(); }).then(data => {
    if (data.schema_version !== 1 || !data.transparency || !data.government) throw new Error('Invalid summary');
    const info = data.transparency;
    metric('budget', info.budget_2027_records, 'published comparisons');
    metric('historical', info.historical_programs, 'program families');
    metric('hearings', info.hearing_topics, 'published topic matches');
    if (count(info.local_finance_records) && info.local_finance_records > 0) metric('finances', info.local_finance_records, 'structured ledger records');
    else if (count(info.local_budget_observations) && info.local_budget_observations > 0) metric('finances', info.local_budget_observations, 'reported budget observations');
    metric('lgus', data.government.local_governments, 'local profiles');
    if (data.government.service_records === 0) document.querySelector('[data-home-services-status]').textContent = 'Portal registry not yet populated.';
    else metric('services', data.government.service_records, 'published service records');
  }).catch(() => {
    // Destinations remain useful without figures; failure is never a zero count.
    document.querySelectorAll('[data-home-metric]').forEach(node => { node.hidden = true; node.textContent = ''; });
  });
})();
