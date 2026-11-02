// Better Pangasinan: progressive navigation and source-driven LGU discovery.
document.addEventListener('DOMContentLoaded', function () {
  document.documentElement.classList.add('js');
  var toggle = document.querySelector('.nav-toggle');
  var links = document.querySelector('.nav-links');
  if (toggle && links) {
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && links.classList.contains('open')) {
        links.classList.remove('open'); toggle.setAttribute('aria-expanded', 'false'); toggle.focus();
      }
    });
    toggle.addEventListener('click', function () { var open = links.classList.toggle('open'); toggle.setAttribute('aria-expanded', String(open)); });
    links.querySelectorAll('a').forEach(function (anchor) { anchor.addEventListener('click', function () { links.classList.remove('open'); toggle.setAttribute('aria-expanded', 'false'); }); });
  }
  var here = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-links a').forEach(function (anchor) {
    var target = anchor.getAttribute('href');
    if (target === here) anchor.setAttribute('aria-current', 'page');
    else if ((['lgu.html', 'municipality-map.html', 'statistics.html', 'history.html'].includes(here) && target === 'lgus.html') ||
      (['hospitals.html', 'services.html'].includes(here) && target === 'government.html') ||
      (['national-budget.html', 'historical-budget.html', 'budget-context.html', 'budget-hearings.html', 'projects.html', 'finances.html', 'procurement.html', 'project.html', 'map.html', 'legislation.html'].includes(here) && target === 'transparency.html')) anchor.setAttribute('aria-current', 'location');
  });
  // Profiles have their own controller; the directory never assembles a profile.
  var form = document.querySelector('#lgu-search');
  if (!form) return;
  function element(tag, text, className) { var node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; }
  Promise.all([
    fetch('data/public.json').then(function (response) { if (!response.ok) throw new Error('Unavailable'); return response.json(); }),
    fetch('locales/en.json').then(function (response) { return response.ok ? response.json() : {}; }).catch(function () { return {}; })
  ]).then(function (loaded) {
    var data = loaded[0], dictionary = loaded[1];
    if (!Array.isArray(data.lgus)) throw new Error('Invalid directory');
    var mode = document.querySelector('meta[name="data-mode"]')?.content;
    var records = data.lgus.filter(function (record) { return mode === 'test' || (record.is_mock === false && (mode === 'preview' || record.publication_status === 'approved')); });
    var query = document.querySelector('#lgu-query'), type = document.querySelector('#lgu-type'), more = document.querySelector('#lgu-show-more');
    var limit = 12;
    function hydrate() { var params = new URLSearchParams(location.search); query.value = params.get('q') || ''; type.value = ['city', 'municipality'].includes(params.get('type')) ? params.get('type') : ''; }
    function render(reset) {
      if (reset) limit = 12;
      var filtered = records.filter(function (record) { return record.name.toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase()) && (!type.value || record.classification === type.value); });
      var results = document.querySelector('#lgu-results'); results.replaceChildren();
      filtered.slice(0, limit).forEach(function (record) {
        var card = element('article', undefined, 'card lgu-directory-card');
        card.append(element('span', record.classification === 'city' ? 'City' : 'Municipality', 'badge'), element('h2', record.name));
        card.append(element('p', record.population == null ? 'Population not supplied' : Number(record.population).toLocaleString('en-PH') + ' people / ' + (record.population_reference_date || record.reporting_period || 'reference not supplied').slice(0, 4)));
        var link = element('a', 'View profile', 'card-link'); link.href = 'lgu.html?id=' + encodeURIComponent(record.id); card.append(link);
        var details = element('details'); details.append(element('summary', 'Source and geographic code'));
        details.append(element('p', 'Official geographic code (PSGC): ' + (record.psgc || 'Not supplied'), 'source-line'));
        if (record.population_reference_date) details.append(element('p', 'Population reference: ' + record.population_reference_date, 'source-line'));
        if (record.psgc_release) details.append(element('p', 'Administrative listing: ' + record.psgc_release, 'source-line'));
        var source = (data.sources || []).find(function (item) { return item.id === (record.source_ids || [])[0]; });
        if (source) { try { var url = new URL(source.url); if (url.protocol === 'https:' && !url.username && !url.password) { var anchor = element('a', source.publisher || source.name || 'Open source'); anchor.href = url.href; anchor.rel = 'noopener noreferrer'; details.append(anchor); } } catch {} }
        card.append(details); results.append(card);
      });
      document.querySelector('#lgu-result-count').textContent = filtered.length + ' ' + (dictionary['directory.found'] || 'published profiles found') + '. Showing ' + Math.min(limit, filtered.length) + '.';
      document.querySelector('#lgu-empty').hidden = filtered.length > 0;
      if (records.length && !filtered.length) document.querySelector('#lgu-empty h2').textContent = dictionary['directory.no_results'] || 'No matching profiles';
      more.hidden = filtered.length <= limit;
    }
    function updateUrl() { var url = new URL(location.href); if (query.value.trim()) url.searchParams.set('q', query.value.trim()); else url.searchParams.delete('q'); if (type.value) url.searchParams.set('type', type.value); else url.searchParams.delete('type'); history.replaceState(null, '', url); }
    form.addEventListener('submit', function (event) { event.preventDefault(); updateUrl(); render(true); });
    query.addEventListener('input', function () { updateUrl(); render(true); });
    type.addEventListener('change', function () { updateUrl(); render(true); });
    form.addEventListener('reset', function () { setTimeout(function () { updateUrl(); render(true); }, 0); });
    more.addEventListener('click', function () { limit += 12; render(false); });
    window.addEventListener('popstate', function () { hydrate(); render(true); });
    hydrate(); render(true);
  }).catch(function () { document.querySelector('#lgu-result-count').textContent = 'The directory could not be loaded.'; var empty = document.querySelector('#lgu-empty'); empty.hidden = false; empty.querySelector('h2').textContent = 'Directory unavailable'; empty.querySelector('p').textContent = 'Try again or use the official directory below.'; });
});
