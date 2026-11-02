/* Local SVG only: no tiles, tracking, or external runtime dependencies. */
(() => {
  'use strict';
  const host = document.querySelector('[data-lgu-map]');
  if (!host) return;
  const status = host.querySelector('[data-map-status]');
  const detail = host.querySelector('[data-map-detail]');
  const list = host.querySelector('[data-map-list]');
  const svg = host.querySelector('svg');
  const ns = 'http://www.w3.org/2000/svg';
  const profile = p => `lgu.html?id=${encodeURIComponent(p.id)}`;
  function describe(p) {
    return `${p.name}: ${p.classification}; 2024 population ${p.population_2024.toLocaleString('en-PH')}; barangays ${p.barangay_count === null ? 'unavailable' : p.barangay_count}.`;
  }
  Promise.all(['manifest.json', 'municipalities.geojson'].map(async name => {
    const response = await fetch(`data/geography/${name}`);
    if (!response.ok) throw new Error('Geography unavailable');
    return response.json();
  })).then(([manifest, collection]) => {
    status.textContent = `${manifest.municipality_count}/48 municipality geometries. ${manifest.barangay_count} published barangay records. ${manifest.barangay_note} Unresolved matches are omitted, never invented.`;
    host.querySelector('[data-map-credit]').textContent = manifest.attribution;
    const points = [];
    const polygons = geometry => geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;
    collection.features.forEach(f => polygons(f.geometry).forEach(poly => poly.forEach(ring => points.push(...ring))));
    if (!points.length) return;
    const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
    const xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys);
    const scale = Math.min(920 / ((xmax - xmin) * Math.cos(16 * Math.PI / 180)), 620 / (ymax - ymin));
    const project = p => `${20 + (p[0] - xmin) * Math.cos(16 * Math.PI / 180) * scale},${20 + (ymax - p[1]) * scale}`;
    collection.features.forEach(f => {
      const p = f.properties;
      const link = document.createElementNS(ns, 'a');
      link.setAttribute('href', profile(p));
      link.setAttribute('aria-label', describe(p) + ' Open profile');
      const path = document.createElementNS(ns, 'path');
      path.setAttribute('d', polygons(f.geometry).map(poly => poly.map(ring => `M${ring.map(project).join('L')}Z`).join('')).join(''));
      path.setAttribute('fill-rule', 'evenodd');
      const title = document.createElementNS(ns, 'title');
      title.textContent = describe(p);
      path.append(title);
      link.append(path);
      for (const event of ['focus', 'pointerenter']) link.addEventListener(event, () => {
        detail.textContent = describe(p);
        svg.querySelectorAll('[data-selected]').forEach(el => el.removeAttribute('data-selected'));
        link.setAttribute('data-selected', 'true');
      });
      svg.append(link);
      const item = document.createElement('li');
      const textLink = document.createElement('a');
      textLink.href = profile(p);
      textLink.textContent = describe(p);
      item.append(textLink);
      list.append(item);
    });
    const requested = new URLSearchParams(location.search).get('psgc');
    if (requested) {
      const match = collection.features.find(f => f.properties.psgc === requested);
      if (match) {
        detail.textContent = describe(match.properties);
        const target = Array.from(svg.querySelectorAll('a')).find(a => a.getAttribute('href') === profile(match.properties));
        if (target) target.setAttribute('data-selected', 'true');
      }
    }
  }).catch(() => {
    status.textContent = 'Geography could not be loaded. No geometry or barangay counts are inferred. Use the LGU registry for profiles.';
  });
})();
