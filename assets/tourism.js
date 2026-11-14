(() => {
  'use strict';
  const root = document.querySelector('[data-tourism]');
  if (!root) return;
  const status = root.querySelector('[data-tourism-status]');
  const results = root.querySelector('[data-tourism-results]');
  const detailHost = root.querySelector('[data-tourism-detail]');
  const empty = root.querySelector('[data-tourism-empty]');
  const form = root.querySelector('form');
  const search = root.querySelector('#tr-search');
  const category = root.querySelector('#tr-category');
  const municipality = root.querySelector('#tr-municipality');
  const hidden = root.querySelector('#tr-hidden');
  const foodHost = document.querySelector('[data-tourism-food]');

  const CATEGORY_LABELS = { beach: 'Beach', island: 'Island', falls: 'Falls', cave: 'Cave', heritage: 'Heritage',
    pilgrimage: 'Pilgrimage', nature: 'Nature', festival: 'Festival' };
  const MODE_LABELS = { bus: 'Bus', jeepney: 'Jeepney', van: 'Van', tricycle: 'Tricycle', boat: 'Boat', walk: 'Walk' };

  const node = (tag, text, cls) => {
    const el = document.createElement(tag);
    if (text !== undefined && text !== null) el.textContent = text;
    if (cls) el.className = cls;
    return el;
  };
  const safeLink = (label, url) => {
    const link = node('a', label);
    try { if (new URL(url).protocol === 'https:') link.href = url; } catch (_) { /* Invalid URL stays plain text. */ }
    return link;
  };
  const localAsset = path => (/^assets\/tourism\/[a-z0-9-]+\.(jpg|webp|svg)$/.test(path || '') ? path : '');
  const lguLink = (id, names) => {
    const link = node('a', names.get(id) || 'City or municipality profile');
    link.href = `lgu.html?id=${encodeURIComponent(id)}`;
    return link;
  };
  const longDate = iso => new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

  let data = null;
  let names = new Map();
  let attractions = new Map();
  let foods = new Map();
  let sources = new Map();
  let map = null;
  let openerId = null;

  const params = () => new URLSearchParams(location.search);
  const writeState = (spot, push) => {
    const next = new URLSearchParams();
    if (search.value.trim()) next.set('q', search.value.trim());
    if (category.value) next.set('category', category.value);
    if (municipality.value) next.set('municipality', municipality.value);
    if (hidden.checked) next.set('hidden', '1');
    if (spot) next.set('spot', spot);
    const url = `${location.pathname}${next.toString() ? `?${next}` : ''}${location.hash}`;
    history[push ? 'pushState' : 'replaceState'](null, '', url);
  };
  const readState = () => {
    const p = params();
    search.value = p.get('q') || '';
    category.value = [...category.options].some(o => o.value === p.get('category')) ? p.get('category') : '';
    municipality.value = [...municipality.options].some(o => o.value === p.get('municipality')) ? p.get('municipality') : '';
    hidden.checked = p.get('hidden') === '1';
  };

  const photoElement = (photo, small) => {
    const img = node('img');
    img.src = localAsset(small && photo.file_small ? photo.file_small : photo.file);
    img.alt = photo.alt;
    img.loading = small ? 'lazy' : 'eager';
    img.decoding = 'async';
    return img;
  };
  const chips = item => {
    const wrap = node('div', null, 'tr-chips');
    if (item.is_hidden_spot) wrap.append(node('span', 'Hidden spot', 'tr-badge-hidden'));
    item.categories.forEach(c => wrap.append(node('span', CATEGORY_LABELS[c] || c, 'tr-chip')));
    return wrap;
  };

  const matches = item => {
    const q = search.value.trim().toLowerCase();
    if (category.value && !item.categories.includes(category.value)) return false;
    if (municipality.value && item.lgu_id !== municipality.value) return false;
    if (hidden.checked && !item.is_hidden_spot) return false;
    if (!q) return true;
    return [item.name, item.summary, item.barangay, names.get(item.lgu_id), ...item.categories.map(c => CATEGORY_LABELS[c])]
      .filter(Boolean).join(' ').toLowerCase().includes(q);
  };

  const renderCards = () => {
    const shown = data.attractions.filter(matches);
    results.replaceChildren(...shown.map(item => {
      const card = node('article', null, 'tr-card');
      card.dataset.categories = item.categories.join(' ');
      card.dataset.id = item.id;
      const media = node('div', null, 'tr-card-media');
      media.append(photoElement(item.photo, true));
      const body = node('div', null, 'tr-card-body');
      const heading = node('h3');
      const link = node('a', item.name, 'tr-card-link');
      link.href = `tourism.html?spot=${encodeURIComponent(item.id)}`;
      link.addEventListener('click', event => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
        event.preventDefault();
        openSpot(item.id, true);
      });
      heading.append(link);
      const place = node('p', null, 'tr-card-place');
      place.append(item.barangay ? `Brgy. ${item.barangay.replace(/\s*\(.*\)$/, '')}, ` : '', lguLink(item.lgu_id, names));
      body.append(chips(item), heading, place, node('p', item.summary, 'tr-card-summary'));
      card.append(media, body);
      return card;
    }));
    empty.hidden = shown.length > 0;
    status.textContent = `${plural(shown.length, 'place')} shown`;
  };

  const section = (title, ...children) => {
    const el = node('section', null, 'tr-detail-section');
    el.append(node('h3', title), ...children);
    return el;
  };
  const sourceList = ids => {
    const list = node('ul', null, 'tr-source-list');
    [...new Set(ids)].forEach(id => {
      const s = sources.get(id);
      if (!s) return;
      const li = node('li');
      li.append(safeLink(s.title || s.url, s.url), ` — ${s.publisher}`);
      list.append(li);
    });
    return list;
  };

  const renderRoute = route => {
    const wrap = node('div', null, 'tr-route');
    wrap.append(node('h4', route.origin));
    const steps = node('ol');
    route.legs.forEach(leg => {
      const li = node('li');
      li.append(node('span', MODE_LABELS[leg.mode] || leg.mode, `tr-leg-mode tr-mode-${leg.mode}`));
      const text = node('div', null, 'tr-leg-text');
      text.append(node('strong', `${leg.from} to ${leg.to}`));
      const meta = [leg.operator, leg.duration_text, leg.fare_text && `${leg.fare_text} (approx., as of ${longDate(leg.fare_as_of)})`].filter(Boolean);
      if (meta.length) text.append(node('span', meta.join(' · '), 'tr-leg-meta'));
      if (leg.notes) text.append(node('span', leg.notes, 'tr-leg-notes'));
      li.append(text);
      steps.append(li);
    });
    wrap.append(steps);
    if (route.gap_note) wrap.append(node('p', route.gap_note, 'tr-gap'));
    const cite = node('p', 'Route source: ', 'tr-route-source');
    route.source_ids.forEach((id, i) => { const s = sources.get(id); if (s) cite.append(i ? ', ' : '', safeLink(s.publisher, s.url)); });
    wrap.append(cite);
    return wrap;
  };

  const renderMap = (host, item) => {
    if (map) { map.remove(); map = null; }
    const provider = window.ProjectMapProviders && window.ProjectMapProviders.osm;
    if (!window.L || !provider) { host.append(node('p', 'The map could not load. Use the OpenStreetMap link below.', 'tr-map-fallback')); return; }
    const { lat, lon } = item.coordinates;
    map = L.map(host, { scrollWheelZoom: false, attributionControl: true }).setView([lat, lon], 13);
    L.tileLayer(provider.url, { maxZoom: provider.maxZoom, attribution: provider.attribution,
      updateWhenIdle: provider.updateWhenIdle, keepBuffer: provider.keepBuffer }).addTo(map);
    L.marker([lat, lon], { title: item.name, alt: item.name, keyboard: false,
      icon: L.divIcon({ className: 'tr-marker', iconSize: [22, 22], iconAnchor: [11, 11] }) }).addTo(map);
  };

  const renderDetail = id => {
    const item = attractions.get(id);
    detailHost.hidden = false;
    const article = node('article', null, 'tr-detail');
    const back = node('button', 'Back to all places', 'btn btn-outline tr-back');
    back.type = 'button';
    back.dataset.tourismBack = '';
    back.addEventListener('click', closeSpot);
    if (!item) {
      const missing = node('h2', 'We could not find that place');
      missing.tabIndex = -1;
      article.append(back, missing, node('p', 'The link may be outdated. Choose a place from the list below.'));
      detailHost.replaceChildren(article);
      return missing;
    }
    const figure = node('figure', null, 'tr-detail-figure');
    const caption = node('figcaption');
    caption.append(`Photo: ${item.photo.author}, `, safeLink(item.photo.license, item.photo.license_url), ' · ', safeLink('Image source', item.photo.source_url));
    figure.append(photoElement(item.photo, false), caption);

    const title = node('h2', item.name);
    title.tabIndex = -1;
    const head = node('div', null, 'tr-detail-head');
    head.append(chips(item), title, node('p', item.summary, 'tr-detail-summary'));

    const where = node('p');
    where.append(item.barangay ? `Brgy. ${item.barangay}, ` : '', lguLink(item.lgu_id, names), ', Pangasinan');
    const mapHost = node('div', null, 'tr-map');
    mapHost.setAttribute('role', 'region');
    mapHost.setAttribute('aria-label', `Map of ${item.name}`);
    const { lat, lon } = item.coordinates;
    const osm = node('p', null, 'tr-map-links');
    const osmLink = safeLink('Open in OpenStreetMap', `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=15/${lat}/${lon}`);
    osm.append(osmLink);
    const coordSource = sources.get(item.coordinate_source_id);
    if (coordSource) osm.append(' · Pin from ', safeLink(coordSource.publisher, coordSource.url));

    const how = [node('p', 'Fares follow government-prescribed tariffs and change often, so this guide lists operators and steps, not prices.', 'tr-tariff-note'), ...item.routes.map(renderRoute)];
    if (item.private_vehicle_note) {
      const car = node('p', null, 'tr-private');
      car.append(node('strong', 'By private vehicle: '), item.private_vehicle_note);
      how.push(car);
    }

    const foodList = node('ul', null, 'tr-link-list');
    item.food_ids.map(f => foods.get(f)).filter(Boolean).forEach(food => {
      const li = node('li');
      const a = node('a', food.name);
      a.href = `#food-${food.id}`;
      li.append(a, ` — from ${names.get(food.lgu_id) || 'Pangasinan'}`);
      foodList.append(li);
    });
    const eat = foodList.children.length ? foodList : node('p', 'No local food is listed near this place yet.');

    const nearby = item.nearby_ids.map(n => attractions.get(n)).filter(Boolean);
    const hiddenNear = nearby.filter(n => n.is_hidden_spot);
    const others = nearby.filter(n => !n.is_hidden_spot);
    const spotList = list => {
      const ul = node('ul', null, 'tr-link-list');
      list.forEach(n => {
        const li = node('li');
        const a = node('a', n.name);
        a.href = `tourism.html?spot=${encodeURIComponent(n.id)}`;
        a.addEventListener('click', event => { event.preventDefault(); openSpot(n.id, true); });
        li.append(a, ` — ${names.get(n.lgu_id) || ''}`);
        ul.append(li);
      });
      return ul;
    };
    const hiddenSection = [hiddenNear.length ? spotList(hiddenNear) : node('p', 'No hidden spots are listed near this place yet.')];
    if (others.length) hiddenSection.push(node('p', 'Also nearby:', 'tr-also'), spotList(others));

    const know = [];
    if (item.entrance_fee_text) know.push(node('p', `Entrance: ${item.entrance_fee_text} (as listed ${longDate(item.fee_as_of)}).`));
    if (item.tips.length) { const ul = node('ul'); item.tips.forEach(t => ul.append(node('li', t))); know.push(ul); }
    if (item.responsible_visit) { const p = node('p', null, 'tr-respect'); p.append(node('strong', 'Visit responsibly: '), item.responsible_visit); know.push(p); }
    const verify = node('p', 'Confirm fares, schedules and entrance fees with the operator or the LGU tourism office before you travel. ', 'tr-verify-note');
    const fix = node('a', 'Send a correction');
    fix.href = 'corrections.html';
    verify.append(fix, '.');
    know.push(verify);

    const checked = node('p', `Last checked ${longDate(item.checked_on)}`, 'tr-checked');
    checked.dataset.checkedOn = item.checked_on;
    const allSources = [...item.source_ids, ...item.routes.flatMap(r => r.source_ids), item.coordinate_source_id].filter(Boolean);

    const layout = node('div', null, 'tr-detail-layout');
    const main = node('div', null, 'tr-detail-main');
    main.append(section('Where it is', where, mapHost, osm), section('How to get there', ...how));
    const side = node('div', null, 'tr-detail-side');
    side.append(section('What to eat nearby', eat), section('Hidden spots nearby', ...hiddenSection),
      section('Good to know', ...know), section('Sources', checked, sourceList(allSources)));
    layout.append(main, side);
    article.append(back, figure, head, layout);
    detailHost.replaceChildren(article);
    renderMap(mapHost, item);
    return title;
  };

  function openSpot(id, push) {
    openerId = id;
    writeState(id, push);
    const heading = renderDetail(id);
    detailHost.scrollIntoView({ block: 'start' });
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
  }
  function closeSpot() {
    if (map) { map.remove(); map = null; }
    detailHost.hidden = true;
    detailHost.replaceChildren();
    writeState(null, false);
    const link = openerId && results.querySelector(`[data-id="${CSS.escape(openerId)}"] .tr-card-link`);
    const target = link || results.querySelector('.tr-card-link');
    if (target) { target.focus({ preventScroll: true }); target.scrollIntoView({ block: 'center' }); }
    openerId = null;
  }

  const renderFood = () => {
    if (!foodHost) return;
    foodHost.replaceChildren(...data.foods.map(food => {
      const card = node('article', null, 'tr-food');
      card.id = `food-${food.id}`;
      if (food.photo) {
        const fig = node('figure', null, 'tr-food-figure');
        const cap = node('figcaption');
        cap.append(`${food.photo.author}, `, safeLink(food.photo.license, food.photo.license_url), ' · ', safeLink('source', food.photo.source_url));
        fig.append(photoElement(food.photo, true), cap);
        card.append(fig);
      } else card.append(node('div', null, 'tr-food-motif'));
      const body = node('div', null, 'tr-food-body');
      const from = node('p', 'From ', 'tr-food-place');
      from.append(lguLink(food.lgu_id, names));
      body.append(node('h3', food.name), from, node('p', food.description));
      if (food.where_to_try) body.append(node('p', `Where to try: ${food.where_to_try}`, 'tr-food-where'));
      const near = food.attraction_ids.map(a => attractions.get(a)).filter(Boolean);
      if (near.length) {
        const p = node('p', 'Near: ', 'tr-food-near');
        near.forEach((a, i) => {
          const link = node('a', a.name);
          link.href = `tourism.html?spot=${encodeURIComponent(a.id)}`;
          link.addEventListener('click', event => { event.preventDefault(); openSpot(a.id, true); });
          p.append(i ? ', ' : '', link);
        });
        body.append(p);
      }
      const cite = node('p', 'Source: ', 'tr-route-source');
      food.source_ids.forEach((id, i) => { const s = sources.get(id); if (s) cite.append(i ? ', ' : '', safeLink(s.title || s.publisher, s.url)); });
      body.append(cite);
      card.append(body);
      return card;
    }));
  };

  const refresh = () => { writeState(params().get('spot'), false); renderCards(); };
  form.addEventListener('submit', event => event.preventDefault());
  form.addEventListener('input', refresh);
  form.addEventListener('change', refresh);
  form.addEventListener('reset', () => setTimeout(refresh, 0));
  window.addEventListener('popstate', () => {
    readState();
    renderCards();
    const spot = params().get('spot');
    if (spot) renderDetail(spot); else { if (map) { map.remove(); map = null; } detailHost.hidden = true; detailHost.replaceChildren(); }
  });

  const json = path => fetch(new URL(path, document.baseURI)).then(r => { if (!r.ok) throw new Error(path); return r.json(); });
  Promise.all([json('data/tourism.json'), json('data/lgus.json').catch(() => [])]).then(([tourism, lgus]) => {
    if (tourism.schema_version !== 1 || !Array.isArray(tourism.attractions) || !Array.isArray(tourism.foods) || !Array.isArray(tourism.sources)) throw new Error('Invalid tourism data');
    data = tourism;
    names = new Map((Array.isArray(lgus) ? lgus : []).map(row => [row.id, row.name]));
    attractions = new Map(data.attractions.map(a => [a.id, a]));
    foods = new Map(data.foods.map(f => [f.id, f]));
    sources = new Map(data.sources.map(s => [s.id, s]));
    [...new Set(data.attractions.flatMap(a => a.categories))].sort().forEach(c => {
      const o = node('option', CATEGORY_LABELS[c] || c); o.value = c; category.append(o);
    });
    [...new Set(data.attractions.map(a => a.lgu_id))].sort((a, b) => (names.get(a) || a).localeCompare(names.get(b) || b)).forEach(id => {
      const o = node('option', names.get(id) || id); o.value = id; municipality.append(o);
    });
    readState();
    renderCards();
    renderFood();
    const spot = params().get('spot');
    if (spot) { openerId = spot; const heading = renderDetail(spot); heading.focus({ preventScroll: true }); detailHost.scrollIntoView({ block: 'start' }); }
    else if (location.hash) { const target = document.getElementById(location.hash.slice(1)); if (target) target.scrollIntoView(); }
  }).catch(() => {
    status.textContent = 'Tourism guide unavailable. Try again later or download the dataset.';
    results.replaceChildren();
  });
})();
