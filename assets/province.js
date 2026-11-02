(() => {
  'use strict';
  const root = document.getElementById('province-summary');
  if (!root) return;
  const node = (tag, text, parent) => { const element = document.createElement(tag); if (text !== undefined) element.textContent = text; if (parent) parent.append(element); return element; };
  fetch('data/province-profile.json').then(response => { if (!response.ok) throw new Error('Unavailable'); return response.json(); }).then(data => {
    const preview = document.querySelector('meta[name="data-mode"][content="preview"]') !== null;
    if (!(data.status === 'available' || (preview && data.status === 'preview')) || !data.profile || data.profile.publication_status !== 'approved') throw new Error('No published profile');
    const profile = data.profile;
    if (['population', 'cities', 'municipalities', 'lgu_count', 'barangays_reported'].some(key => !Number.isSafeInteger(profile[key]) || profile[key] < 0) || typeof profile.psgc !== 'string' || !Array.isArray(data.sources)) throw new Error('Invalid provincial reference');
    const cards = root.querySelector('[data-province-kpis]');
    const values = [
      ['Population', profile.population, `Persons as of ${profile.population_reference_date}`],
      ['Cities', profile.cities, 'Derived from the published LGU registry'],
      ['Municipalities', profile.municipalities, 'Derived from the published LGU registry'],
      ['Barangays reported', profile.barangays_reported, 'Provincial reference count, not collected map coverage'],
      ['Capital', profile.capital, 'Provincial reference information'],
      ['Province PSGC', profile.psgc, `Administrative listing ${profile.administrative_listing_as_of}`],
    ];
    for (const [label, value, note] of values) {
      const card = node('div', undefined, cards); card.className = 'province-kpi';
      node('span', label, card); node('strong', typeof value === 'number' ? value.toLocaleString('en-PH') : value, card); node('small', note, card);
    }
    const sources = root.querySelector('[data-province-sources]');
    node('span', `Population reference: ${profile.population_reference_date}. LGU listing: ${profile.administrative_listing_as_of}. Sources: `, sources);
    for (const source of data.sources || []) {
      const url = new URL(source.url);
      if (url.protocol !== 'https:' || url.username || url.password) continue;
      const anchor = node('a', source.publisher || source.name, sources); anchor.href = url.href; anchor.rel = 'noopener noreferrer'; sources.append(document.createTextNode(' / '));
    }
    root.querySelector('[data-province-status]').textContent = `${profile.lgu_count} ${preview ? 'source-backed city and municipal profiles in the development preview' : 'reviewed city and municipal profiles published'}. Population is a dated census observation, not a current estimate.`;
  }).catch(() => { root.querySelector('[data-province-kpis]').replaceChildren(); root.querySelector('[data-province-status]').textContent = 'The provincial reference summary could not be loaded. No missing statistics are replaced with zero.'; });
})();
