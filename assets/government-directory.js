(() => {
  'use strict';
  const root = document.querySelector('[data-government-directory]');
  if (!root) return;
  const status = root.querySelector('[data-gd-status]');
  const results = root.querySelector('[data-gd-results]');
  const form = root.querySelector('form');
  const search = root.querySelector('#gd-search');
  const districtFilter = root.querySelector('#gd-district');
  const node = (tag, text, cls) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (cls) el.className = cls;
    return el;
  };
  const safeLink = (label, url) => {
    const link = node('a', label);
    try { if (new URL(url).protocol === 'https:') link.href = url; } catch (_) { /* Invalid source stays plain text. */ }
    return link;
  };
  fetch(new URL('data/government-leadership.json', document.baseURI)).then(response => {
    if (!response.ok) throw new Error('Directory unavailable');
    return response.json();
  }).then(data => {
    if (data.schema_version !== 1 || !Array.isArray(data.officials) || data.districts?.length !== 6 || !Array.isArray(data.sources) || !Array.isArray(data.pending_positions)) throw new Error('Invalid directory');
    const sources = new Map(data.sources.map(source => [source.id, source]));
    const districts = new Map(data.districts.map(district => [district.id, district]));
    data.districts.forEach(district => {
      const option = node('option', district.name);
      option.value = district.id;
      districtFilter.append(option);
    });
    let officialId = '';
    function hydrate() {
      const params = new URL(location.href).searchParams;
      officialId = params.get('official') || '';
      const official = data.officials.find(item => item.id === officialId);
      const district = params.get('district') || official?.district_id || '';
      districtFilter.value = districts.has(district) ? district : '';
      search.value = params.get('official_search') || '';
    }
    function evidence(card, official) {
      const details = node('details');
      details.append(node('summary', 'Sources and verification'));
      details.append(node('p', `${official.verification_status === 'user_reviewed' ? 'User-reviewed; not live House verification' : 'Listed on the official provincial source'} · Collected ${data.metadata.collected_at.slice(0, 10)}. Term dates not inferred.`));
      const list = node('ul', undefined, 'gd-evidence');
      official.source_ids.forEach(id => {
        const source = sources.get(id);
        if (!source) throw new Error('Missing source');
        const item = node('li');
        item.append(safeLink(source.publisher, source.url), node('span', ` · ${source.retrieved_at.slice(0, 10)}${source.http_status ? ` · HTTP ${source.http_status}` : ''}`));
        list.append(item);
      });
      Object.entries(official.field_evidence || {}).forEach(([field, value]) => {
        const item = node('li', `${field.replaceAll('_', ' ')}: ${value.note} Collected ${value.collected_at.slice(0, 10)}. `);
        value.source_ids.forEach(id => { const source = sources.get(id); if (source) item.append(safeLink(source.publisher, source.url)); });
        list.append(item);
      });
      details.append(list);
      const technical = node('details'); technical.append(node('summary', 'Original structured record'), node('pre', JSON.stringify(official, null, 2))); details.append(technical);
      card.append(details);
    }
    function card(official, heading = 'h4') {
      const card = node('article', undefined, 'gd-card');
      card.id = `official-${official.id}`;
      card.append(node('div', official.position, 'gd-role'), node(heading, official.display_name));
      if (official.full_name !== official.display_name) card.append(node('p', official.full_name));
      (official.additional_roles || []).forEach(role => card.append(node('p', `${role} (user-reviewed role)`)));
      if (official.contacts.telephone) {
        const p = node('p', 'Office telephone: ');
        const link = node('a', official.contacts.telephone);
        if (/^\+[0-9]+$/.test(official.contacts.telephone)) link.href = `tel:${official.contacts.telephone}`;
        p.append(link); card.append(p);
      }
      if (official.contacts.facebook) card.append(safeLink('Facebook linked by official profile', official.contacts.facebook));
      if (official.office_location) card.append(node('p', `Office: ${official.office_location}`));
      const district = districts.get(official.district_id);
      if (district) {
        const link = node('a', 'Explore district map');
        link.href = `municipality-map.html?view=districts&district=${encodeURIComponent(district.id)}`;
        card.append(link);
      }
      evidence(card, official);
      return card;
    }
    function render(writeUrl = false) {
      if (writeUrl) {
        const url = new URL(location.href);
        for (const [key, value] of [['official_search', search.value.trim()], ['district', districtFilter.value], ['official', officialId]]) {
          if (value) url.searchParams.set(key, value); else url.searchParams.delete(key);
        }
        history.replaceState(null, '', url);
      }
      const query = search.value.trim().toLowerCase();
      const matches = data.officials.filter(official => {
        const district = districts.get(official.district_id);
        return (!officialId || official.id === officialId) && (!districtFilter.value || official.district_id === districtFilter.value || ['governor', 'vice_governor', 'ex_officio'].includes(official.role_type)) && (!query || [official.display_name, official.full_name, official.position, ...(district?.lgu_names || [])].join(' ').toLowerCase().includes(query));
      });
      results.replaceChildren();
      [['Provincial Leadership', ['governor', 'vice_governor']], ['Sangguniang Panlalawigan', ['board_member']], ['House Representatives', ['house_representative']], ['Ex Officio Members', ['ex_officio']]].forEach(([title, roles]) => {
        const section = node('section');
        section.append(node('h3', title));
        const people = matches.filter(official => roles.includes(official.role_type));
        if (!people.length) return;
        const grid = node('div', undefined, 'gd-grid');
        if (roles.includes('board_member') || roles.includes('house_representative')) {
          grid.classList.add('gd-district-groups');
          for (const district of data.districts) {
            const members = people.filter(person => person.district_id === district.id);
            if (!members.length) continue;
            const group = node('div', undefined, 'gd-district-group'); group.append(node('h4', district.name));
            for (const person of members) group.append(card(person, 'h5'));
            grid.append(group);
          }
        } else people.forEach(official => grid.append(card(official)));
        section.append(grid);
        results.append(section);
      });
      const pending = node('details');
      pending.append(node('summary', 'Pending position evidence: PCL representative'));
      data.pending_positions.forEach(position => {
        pending.append(node('p', position.note));
        position.source_ids.forEach(id => { const source = sources.get(id); if (source) pending.append(safeLink(source.publisher, source.url), document.createTextNode(' ')); });
      });
      results.append(pending);
      status.textContent = `${matches.length} officials shown · 6 legislative districts · 48 cities and municipalities. Provincial leadership and ex officio members are province-wide.`;
    }
    form.addEventListener('submit', event => { event.preventDefault(); officialId = ''; render(true); });
    search.addEventListener('input', () => { officialId = ''; render(true); });
    districtFilter.addEventListener('change', () => { officialId = ''; render(true); });
    form.addEventListener('reset', event => { event.preventDefault(); search.value = ''; districtFilter.value = ''; officialId = ''; render(true); });
    window.addEventListener('popstate', () => { hydrate(); render(); });
    hydrate(); render();
  }).catch(() => {
    results.replaceChildren();
    status.textContent = 'Government directory unavailable. Consult the official provincial sources or try again later.';
    status.append(document.createTextNode(' '), safeLink('Official board listing', 'https://www.pangasinan.gov.ph/positions/board-member/'));
  });
})();
