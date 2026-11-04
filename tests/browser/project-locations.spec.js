const { test, expect, tileURL } = require('./tile-fixture');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '../..');
const boundary = fs.readFileSync(path.join(root, 'data/geography/municipalities.geojson'), 'utf8');
const leaflet = fs.readFileSync(path.join(root, 'assets/leaflet/leaflet.js'), 'utf8');
const hashes = { projects: 'a'.repeat(64), municipalities: crypto.createHash('sha256').update(boundary).digest('hex') };
function fixture() {
  const projects = Array.from({ length: 32 }, (_, i) => ({ id: `fmr-${i}`, upstream_id: `${i}`, title: `Published road ${i}`, dataset: 'fmr', house_stage: 'hgab2', nep_php: i ? 1000000 : null, house_php: 2000000, comparison_status: 'increased', stated_province: 'Pangasinan', stated_municipalities: [{ psgc: '0105501000', name: 'Alaminos' }], stated_barangays: [], display_status: i === 30 ? 'suspicious' : i === 31 ? 'unavailable' : 'plausible', location_flags: i === 30 ? ['outside_province'] : [], source_links: { nep: 'https://example.org/original.pdf' }, segments: i === 31 ? [] : [{ index: 0, source_versions: ['nep'], start: i === 30 ? [123.45, -65.25] : [120.01 + i / 10000, 16.1], end: i === 30 ? [123.46, -65.26] : [120.02 + i / 10000, 16.11], start_raw: 'original start text', end_raw: 'original end text', distance_km: 1.5, flags: [], evidence: { explanation: 'Outside reference boundaries, not an allegation.' } }] }));
  const features = projects.flatMap(p => p.segments.flatMap(s => [
    ...['start', 'end'].map(endpoint => ({ type: 'Feature', properties: { project_id: p.id, segment_index: s.index, endpoint }, geometry: { type: 'Point', coordinates: s[endpoint] } })),
    { type: 'Feature', properties: { project_id: p.id, segment_index: s.index }, geometry: { type: 'LineString', coordinates: [s.start, s.end] } },
  ]));
  projects[0].source_links.house = null;
  return { summary: { schema_version: 1, snapshot_id: 'fixture-2027', source_hashes: hashes, policy: { no_coordinate_adjustment: true }, counts: { projects: 32 }, projects }, geo: { type: 'FeatureCollection', snapshot_id: 'fixture-2027', source_hashes: hashes, features } };
}
async function setup(page, data = fixture()) {
  await page.route('**/assets/leaflet/leaflet.js', route => route.fulfill({ contentType: 'text/javascript', body: `${leaflet}\nconst originalMap = L.map; L.map = (...args) => { const map = originalMap(...args); window.testLocationMap = map; return map; };` }));
  await page.route('**/data/project-locations/review-summary.json', route => route.fulfill({ json: data.summary }));
  await page.route('**/data/project-locations/projects.geojson', route => route.fulfill({ json: data.geo }));
  await page.route('**/data/national-budget/2027/manifest.json', route => route.fulfill({ json: { snapshot_id: 'fixture-2027', files: { 'projects.json': hashes.projects } } }));
}

test('requested Koronadal record cannot reappear through inclusion or its old deep link', async ({ page }) => {
  const data = fixture(), excludedId = 'fmr:house_only:ib:p722:r4';
  const project = structuredClone(data.summary.projects[0]);
  project.id = excludedId; project.title = 'Concreting of Purok Makiangayon, Brgy. New Pangasinan, Koronadal City, South Cotabato';
  project.display_status = 'name_match_elsewhere';
  data.summary.projects.push(project);
  data.geo.features.push(...data.geo.features.filter(feature => feature.properties.project_id === 'fmr-0').map(feature => ({ ...structuredClone(feature), properties: { ...feature.properties, project_id: excludedId } })));
  await setup(page, data);
  await page.goto(`/map.html?include_elsewhere=1&project=${encodeURIComponent(excludedId)}`);
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  await expect(page.locator('#pl-detail')).toContainText('excluded from Project Locations');
  await expect(page.locator('#pl-status')).toContainText('1 source result excluded from this map');
  const plotted = await page.evaluate(() => Object.values(window.testLocationMap._layers).filter(layer => layer.options?.className === 'pl-map-endpoint').map(layer => layer.getElement()?.dataset.projectId));
  expect(plotted).not.toContain(excludedId);
  await page.locator('[name=query]').fill('Makiangayon');
  await expect(page.locator('#pl-list article')).toHaveCount(0);
  await expect(page.locator('[name=include_elsewhere]')).toBeChecked();
});
test('local Leaflet renders every supplied endpoint and line, defaults to province, paginates unique projects', async ({ page }) => {
  await setup(page);
  const external = []; page.on('request', r => { if (!new URL(r.url()).hostname.match(/^(localhost|127\.0\.0\.1)$/)) external.push(r.url()); });
  await page.goto('/map.html');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  await expect(page.locator('#pl-status')).toContainText('32 unique projects');
  await expect(page.locator('#pl-list article')).toHaveCount(25);
  const state = await page.evaluate(() => {
    const m = window.testLocationMap, source = [], connections = [];
    m.eachLayer(l => { if (l.options.className === 'pl-map-endpoint') source.push([l.getLatLng().lng, l.getLatLng().lat]); if (l.options.dashArray === '6 6') connections.push(l.getLatLngs().map(p => [p.lng, p.lat])); });
    const tiles = []; m.eachLayer(l => { if (l instanceof L.TileLayer) tiles.push({ url: l._url, attribution: l.options.attribution }); });
    return { center: m.getCenter(), source, connections, crs: m.options.crs === L.CRS.EPSG3857, min: m.options.minZoom, max: m.options.maxZoom, tiles };
  });
   expect(state.crs).toBe(true); expect(state.center.lat).toBeGreaterThan(15); expect(state.center.lat).toBeLessThan(17);
   expect(state.min).toBe(2); expect(state.max).toBe(19);
   expect(state.tiles).toHaveLength(1);
   expect(state.tiles[0].url).toBe('https://tile.openstreetmap.org/{z}/{x}/{y}.png');
   expect(state.tiles[0].attribution).toContain('OpenStreetMap');
  expect(state.source).toHaveLength(62); expect(state.source).toContainEqual([123.45, -65.25]);
  expect(state.connections).toHaveLength(31); expect(state.connections).toContainEqual([[123.45, -65.25], [123.46, -65.26]]);
  // OSM requests are fulfilled by the shared fixture, never by the network.
  expect(external.filter(url => !tileURL.test(url) && !['fonts.googleapis.com', 'fonts.gstatic.com'].includes(new URL(url).hostname))).toEqual([]);
  await page.locator('#pl-next').click();
  await expect(page.locator('#pl-list article')).toHaveCount(7);
  await expect(page.locator('#pl-list')).toContainText('Location unavailable');
});
test('source outlier selection preserves coordinates, filters, evidence and deep link', async ({ page }) => {
  await setup(page); await page.goto('/map.html');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  await page.locator('#pl-suspicious').click();
  await expect(page.locator('#pl-list article')).toHaveCount(1);
  await page.getByRole('button', { name: 'Published road 30', exact: true }).click();
  await expect(page).toHaveURL(/project=fmr-30/);
  await expect(page.locator('#pl-detail')).toContainText('longitude 123.45, latitude -65.25');
  await expect(page.locator('#pl-detail')).toContainText('original start text');
  await expect(page.locator('#pl-detail')).toContainText('not findings of fraud');
  expect(await page.evaluate(() => window.testLocationMap.getCenter().lat)).toBeLessThan(-60);
  await expect(page.locator('[name=dataset]')).toHaveValue('');
  await expect(page.locator('#pl-layer-warnings')).toBeChecked();
  await page.locator('#pl-overview').click();
  expect(await page.evaluate(() => window.testLocationMap.getCenter().lat)).toBeGreaterThan(15);
});
test('map endpoint selection jumps list page without changing filters', async ({ page }) => {
  await setup(page); await page.goto('/map.html');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  await page.evaluate(() => window.testLocationMap.eachLayer(l => { if (l.options.className === 'pl-map-endpoint' && l.getLatLng().lat === -65.25) l.fire('click'); }));
  await expect(page.locator('#pl-page')).toHaveText('2 / 2');
  await expect(page.locator('#pl-list article[aria-current=true]')).toHaveAttribute('data-project-id', 'fmr-30');
  await expect(page.locator('[name=dataset]')).toHaveValue('');
});

test('changing filters does not leave a hidden selection with an invisible map target', async ({ page }) => {
  await setup(page); await page.goto('/map.html?project=fmr-30');
  await expect(page.locator('#pl-detail')).toContainText('Published road 30');
  await page.locator('[name=status]').selectOption('plausible');
  await expect(page.locator('#pl-detail')).toContainText('outside these filters');
  await expect(page).not.toHaveURL(/project=/);
  await expect(page.locator('#pl-list article[aria-current=true]')).toHaveCount(0);
});
test('invalid partner does not remove valid endpoint or invent a connection', async ({ page }) => {
  const data = fixture(), p = data.summary.projects[0]; p.segments[0].end = [120, 95];
  data.geo.features = data.geo.features.filter(f => f.properties.project_id !== p.id || f.properties.endpoint === 'start');
  await setup(page, data); await page.goto('/map.html?project=fmr-0');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  await expect(page.locator('#pl-detail')).toContainText('End: No valid coordinate');
  await expect(page.locator('#pl-detail')).toContainText('Unknown (not zero)');
  await expect(page.locator('#pl-detail').getByRole('button', { name: 'View End', exact: true })).toBeDisabled();
});
test('hash mismatch and altered coordinate evidence fail closed', async ({ page }) => {
  const data = fixture(); data.geo.features[0].geometry.coordinates = [120, 15];
  await setup(page, data); await page.goto('/map.html');
  await expect(page.locator('#pl-status')).toContainText('Coordinate content differs');
  await expect(page.locator('#pl-map')).toBeHidden();
  await expect(page.locator('#pl-list article')).toHaveCount(0);
});
test('library failure preserves text evidence and mobile keyboard selection', async ({ page }) => {
  await setup(page); await page.route('**/assets/leaflet/leaflet.js', route => route.abort());
  await page.setViewportSize({ width: 375, height: 812 }); await page.goto('/map.html');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  await expect(page.locator('#pl-map-status')).toContainText('Map library unavailable');
  const button = page.getByRole('button', { name: 'Published road 0', exact: true }); await button.focus(); await button.press('Enter');
  await expect(page.locator('#pl-detail')).toContainText('longitude 120.01');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
test('missing source has explicit nonfabricated failure', async ({ page }) => {
  await setup(page); await page.route('**/data/project-locations/review-summary.json', route => route.abort());
  await page.goto('/map.html'); await expect(page.locator('#pl-status')).toContainText('could not be loaded or verified');
  await expect(page.locator('#pl-map')).toBeHidden();
});
test('published DPWH deep link selects its program instead of silently hiding the project', async ({ page }) => {
  const data = fixture(), p = structuredClone(data.summary.projects[0]); p.id = 'dpwh-example'; p.dataset = 'dpwh'; p.title = 'Published DPWH project'; p.house_stage = 'hgab3';
  data.summary.projects.push(p);
  data.geo.features.push(...structuredClone(data.geo.features.filter(f => f.properties.project_id === 'fmr-0')).map(f => { f.properties.project_id = p.id; return f; }));
  await setup(page, data); await page.goto('/map.html?project=dpwh-example');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  await expect(page.locator('[name=dataset]')).toHaveValue('dpwh');
  await expect(page.locator('#pl-list article')).toHaveCount(1);
  await expect(page.locator('#pl-detail')).toContainText('Published DPWH project');
});
test('source hash mismatch rejects evidence before creating map layers', async ({ page }) => {
  const data = fixture(); data.summary.source_hashes = { ...hashes, projects: 'b'.repeat(64) };
  await setup(page, data); await page.goto('/map.html');
  await expect(page.locator('#pl-status')).toContainText('do not match');
  await expect(page.locator('#pl-map')).toBeHidden();
});
test('boundary reference failure keeps source coordinate text usable', async ({ page }) => {
  await setup(page); await page.route('**/data/geography/municipalities.geojson', route => route.abort());
  await page.goto('/map.html?project=fmr-30');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  await expect(page.locator('#pl-map-status')).toContainText('Administrative boundaries unavailable');
  await expect(page.locator('#pl-detail')).toContainText('longitude 123.45, latitude -65.25');
  await expect(page.locator('#pl-map')).toBeVisible();
  expect(await page.evaluate(() => !!window.testLocationMap)).toBe(true);
});
test('valid polar latitude is not silently Web Mercator clamped', async ({ page }) => {
  const data = fixture(); data.summary.projects[0].segments[0].start = [120, 90]; data.geo.features[0].geometry.coordinates = [120, 90]; data.geo.features[2].geometry.coordinates[0] = [120, 90];
  await setup(page, data); await page.goto('/map.html');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  const layers = () => page.evaluate(() => { const points = [], lines = []; window.testLocationMap.eachLayer(l => { if (l.options.className === 'pl-map-endpoint') points.push(l.getLatLng().lat); if (l.options.dashArray === '6 6') lines.push(l.getLatLngs().map(p => p.lat)); }); return { points, lines }; });
  const initial = await layers();
  expect(initial.points).not.toContain(90); expect(initial.points).not.toContain(85.0511287798);
  expect(initial.lines.flat()).not.toContain(90);
  await page.getByRole('button', { name: 'Published road 0', exact: true }).click();
  await expect(page.locator('#pl-detail')).toContainText('longitude 120, latitude 90');
  await expect(page.locator('#project-locations')).toContainText(/Mercator|projection/i);
  const inspect = page.locator('#pl-global-inspect');
  if (await inspect.count()) {
    await inspect.click();
    expect(await page.evaluate(() => window.testLocationMap.options.crs === L.CRS.EPSG4326)).toBe(true);
    expect((await layers()).points).toContain(90);
    expect(await page.evaluate(() => { let n = 0; window.testLocationMap.eachLayer(l => { if (l instanceof L.TileLayer) n++; }); return n; })).toBe(0);
  }
});
test('no JavaScript retains downloads and explains no inferred locations', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage(); await page.goto('/map.html');
  await expect(page.getByText(/No locations are inferred from project names\./)).toBeVisible();
  for (const name of ['location summary', 'coordinate file', 'project registry']) await expect(page.getByRole('link', { name, exact: true })).toBeVisible();
  await context.close();
});
test('published snapshot FMR smoke', async ({ page }) => {
  await page.goto('/map.html');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  await page.locator('[name=dataset]').selectOption('fmr');
  await expect(page.locator('#pl-status')).toContainText('31 unique projects');
  await page.locator('[name=include_elsewhere]').check();
  await expect(page.locator('#pl-status')).toContainText('31 unique projects');
  await expect(page.locator('#pl-list article')).toHaveCount(25);
  await page.locator('#pl-list article button').first().click();
  await page.locator('#pl-detail').getByText('Original coordinates and segments (1)', { exact: true }).click();
  await expect(page.locator('#pl-detail')).toContainText('Published segment');
});

test('V2 basemap and layer controls do not duplicate source features', async ({ page }) => {
  await setup(page); await page.goto('/map.html');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  await expect(page.locator('#pl-basemap')).toHaveValue('osm');
  for (const layer of ['boundaries', 'fmr', 'dpwh', 'other', 'warnings']) await expect(page.locator(`#pl-layer-${layer}`)).toBeChecked();
  const endpoints = () => page.evaluate(() => { const points = []; window.testLocationMap.eachLayer(l => { if (l.options.className === 'pl-map-endpoint') points.push([l.getLatLng().lng, l.getLatLng().lat]); }); return points; });
  const before = await endpoints(); expect(before).toHaveLength(62);
  await page.locator('#pl-basemap').selectOption('none');
  expect(await page.evaluate(() => { let n = 0; window.testLocationMap.eachLayer(l => { if (l instanceof L.TileLayer) n++; }); return n; })).toBe(0);
  expect(await endpoints()).toEqual(before);
  await page.getByText('Visible layers', { exact: true }).click();
  await page.locator('#pl-layer-fmr').uncheck(); expect(await endpoints()).toHaveLength(0);
  for (let i = 0; i < 2; i++) { await page.locator('#pl-layer-fmr').check(); expect(await endpoints()).toEqual(before); await page.locator('#pl-layer-fmr').uncheck(); }
  await page.locator('#pl-layer-fmr').check();
  await page.locator('#pl-layer-warnings').uncheck();
  expect((await endpoints()).length).toBeLessThan(before.length);
  await page.locator('#pl-layer-warnings').check(); expect(await endpoints()).toEqual(before);
});

test('V2 suspicious shortcut clears restrictive filters without moving viewport', async ({ page }) => {
  const data = fixture();
  data.summary.projects[1].display_status = 'needs_review'; data.summary.projects[1].location_flags = ['municipality_mismatch'];
  data.summary.projects[2].display_status = 'name_match_elsewhere'; data.summary.projects[2].location_flags = ['outside_province', 'name_match_elsewhere'];
  data.summary.projects[3].display_status = 'needs_review'; data.summary.projects[3].location_flags = [];
  await setup(page, data); await page.goto('/map.html');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  await page.locator('[name=comparison]').selectOption('increased');
  await page.locator('[name=municipality]').selectOption('0105501000');
  await page.locator('[name=query]').fill('no matching title');
  await page.getByText('Visible layers', { exact: true }).click();
  await page.locator('#pl-layer-warnings').uncheck();
  const before = await page.evaluate(() => ({ center: window.testLocationMap.getCenter(), zoom: window.testLocationMap.getZoom() }));
  await page.locator('#pl-suspicious').click();
  for (const name of ['dataset', 'comparison', 'municipality', 'query']) await expect(page.locator(`[name=${name}]`)).toHaveValue('');
  await expect(page.locator('#pl-layer-warnings')).toBeChecked();
  await expect(page.locator('#pl-list article')).toHaveCount(2);
  await expect(page.locator('#pl-list')).toContainText('Published road 1');
  await expect(page.locator('#pl-list')).toContainText('Published road 30');
  expect(await page.evaluate(() => ({ center: window.testLocationMap.getCenter(), zoom: window.testLocationMap.getZoom() }))).toEqual(before);
});

test('V2 detail navigation uses original endpoints and reset clears selection', async ({ page }) => {
  await setup(page); await page.goto('/map.html?project=fmr-30');
  await expect(page.locator('#pl-detail h2')).toHaveText('Published road 30');
  const detail = page.locator('#pl-detail');
  for (const label of ['View Start', 'View End', 'View Both', 'Go to published location']) await expect(detail.getByRole('button', { name: label, exact: true })).toBeEnabled();
  await detail.getByRole('button', { name: 'View End', exact: true }).click();
  const center = await page.evaluate(() => window.testLocationMap.getCenter());
  expect(center.lat).toBeCloseTo(-65.26, 2); expect(center.lng).toBeCloseTo(123.46, 2);
  await detail.getByRole('button', { name: 'View Start', exact: true }).click();
  expect((await page.evaluate(() => window.testLocationMap.getCenter())).lat).toBeCloseTo(-65.25, 2);
  for (const accordion of await detail.locator('details').all()) await expect(accordion).not.toHaveAttribute('open', '');
  await page.locator('#pl-reset').click();
  await expect(page).not.toHaveURL(/project=/);
  await expect(page.locator('#pl-list article[aria-current=true]')).toHaveCount(0);
  expect((await page.evaluate(() => window.testLocationMap.getCenter())).lat).toBeGreaterThan(15);
});

test('V2 tile and boundary failures leave exact source markers usable', async ({ page }) => {
  await setup(page);
  await page.route(tileURL, route => route.abort());
  await page.route('**/data/geography/municipalities.geojson', route => route.abort());
  await page.goto('/map.html');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  await expect(page.locator('#pl-map')).toBeVisible();
  const state = await page.evaluate(() => { const points = []; window.testLocationMap.eachLayer(l => { if (l.options.className === 'pl-map-endpoint') points.push([l.getLatLng().lng, l.getLatLng().lat]); }); return { points, center: window.testLocationMap.getCenter() }; });
  expect(state.points).toHaveLength(62); expect(state.points).toContainEqual([123.45, -65.25]);
  expect(state.center.lat).toBeGreaterThan(15); expect(state.center.lat).toBeLessThan(17);
  await page.getByRole('button', { name: 'Published road 0', exact: true }).click();
  await expect(page.locator('#pl-detail')).toContainText('longitude 120.01, latitude 16.1');
});

test('V2 single published API point does not invent a line or warning', async ({ page }) => {
  const data = fixture(), p = data.summary.projects[0];
  p.display_status = 'needs_review'; p.location_flags = [];
  p.segments[0].end = null; p.segments[0].end_raw = null; p.segments[0].flags = [];
  data.geo.features = data.geo.features.filter(f => f.properties.project_id !== p.id || f.properties.endpoint === 'start');
  await setup(page, data); await page.goto('/map.html?project=fmr-0');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  const state = await page.evaluate(() => { const points = [], lines = []; window.testLocationMap.eachLayer(l => { if (l.options.className === 'pl-map-endpoint') points.push([l.getLatLng().lng, l.getLatLng().lat]); if (l.options.dashArray === '6 6') lines.push(l.getLatLngs().map(p => [p.lng, p.lat])); }); return { points, lines }; });
  expect(state.points).toHaveLength(61); expect(state.lines).toHaveLength(30);
  expect(state.points).toContainEqual([120.01, 16.1]);
  await expect(page.locator('#pl-detail').getByRole('button', { name: 'View End', exact: true })).toBeDisabled();
  await page.locator('#pl-suspicious').click();
  await expect(page.locator('#pl-list article')).toHaveCount(1);
  await expect(page.locator('#pl-list')).not.toContainText('Published road 0');
});

test('V2 multi-segment navigation identifies its segment', async ({ page }) => {
  const data = fixture(), p = data.summary.projects[0], segment = structuredClone(p.segments[0]);
  segment.index = 1; segment.start = [121.01, 17.1]; segment.end = [121.02, 17.11]; p.segments.push(segment);
  data.geo.features.push(...structuredClone(data.geo.features.filter(f => f.properties.project_id === p.id)).map(f => { f.properties.segment_index = 1; f.geometry.coordinates = f.geometry.type === 'Point' ? segment[f.properties.endpoint] : [segment.start, segment.end]; return f; }));
  await setup(page, data); await page.goto('/map.html?project=fmr-0');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  await page.locator('#pl-detail').getByText('Original coordinates and segments (2)', { exact: true }).click();
  const buttons = page.locator('#pl-detail').getByRole('button', { name: /View Start.*segment|segment.*View Start/i });
  await expect(buttons).toHaveCount(2);
  await buttons.nth(1).click();
  const center = await page.evaluate(() => window.testLocationMap.getCenter());
  expect(center.lat).toBeCloseTo(17.1, 2); expect(center.lng).toBeCloseTo(121.01, 2);
});

test('default All Programs excludes only explicit namesakes and inclusion preserves original endpoints', async ({ page }) => {
  const data = fixture(), namesake = data.summary.projects[2], bridge = data.summary.projects[30];
  namesake.title = 'New Pangasinan, Koronadal, South Cotabato';
  namesake.display_status = 'name_match_elsewhere'; namesake.location_flags = ['outside_province', 'name_match_elsewhere'];
  bridge.dataset = 'dpwh'; bridge.title = 'Published distant bridge';
  await setup(page, data); await page.goto('/map.html');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  await expect(page.locator('[name=dataset]')).toHaveValue('');
  await expect(page.locator('[name=include_elsewhere]')).not.toBeChecked();
  await expect(page.locator('#pl-status')).toContainText('31 unique projects');
  await expect(page.locator('#pl-status')).toContainText('1 outside-province namesake results excluded');
  const endpoints = () => page.evaluate(() => { const points = []; window.testLocationMap.eachLayer(l => { if (l.options.className === 'pl-map-endpoint') points.push([l.getLatLng().lng, l.getLatLng().lat]); }); return points; });
  const focused = await endpoints();
  expect(focused).toHaveLength(60);
  expect(focused).toContainEqual(bridge.segments[0].start);
  expect(focused).not.toContainEqual(namesake.segments[0].start);
  await page.locator('[name=query]').fill(namesake.title);
  await expect(page.locator('#pl-list article')).toHaveCount(0);
  await page.locator('[name=include_elsewhere]').check();
  await expect(page.locator('#pl-list article')).toHaveCount(1);
  expect(await endpoints()).toEqual([namesake.segments[0].start, namesake.segments[0].end]);
  await page.getByRole('button', { name: namesake.title, exact: true }).click();
  await expect(page.locator('#pl-detail')).toContainText(`longitude ${namesake.segments[0].start[0]}, latitude ${namesake.segments[0].start[1]}`);
  await page.locator('#pl-reset').click();
  await expect(page.locator('[name=dataset]')).toHaveValue('');
  await expect(page.locator('[name=query]')).toHaveValue('');
  await expect(page.locator('[name=include_elsewhere]')).not.toBeChecked();
  await expect(page.locator('#pl-status')).toContainText('31 unique projects');
  expect(await endpoints()).toEqual(focused);
});

test('namesake deep links and explicit status enable inclusion and history restores filters and data', async ({ page }) => {
  const data = fixture();
  data.summary.projects[2].display_status = 'name_match_elsewhere';
  data.summary.projects[2].location_flags = ['name_match_elsewhere'];
  await setup(page, data); await page.goto('/map.html?project=fmr-2');
  await expect(page.locator('#pl-detail h2')).toHaveText('Published road 2');
  await expect(page.locator('[name=include_elsewhere]')).toBeChecked();
  await page.locator('#pl-reset').click();
  await page.locator('[name=status]').selectOption('name_match_elsewhere');
  await expect(page.locator('[name=include_elsewhere]')).toBeChecked();
  await expect(page.locator('#pl-list article')).toHaveCount(1);
  await expect(page).toHaveURL(/include_elsewhere=1/);
  const namesakeURL = page.url();
  // Filters replace the current entry; supply a second entry to exercise popstate.
  await page.evaluate(() => history.pushState(null, '', location.href));
  await page.locator('#pl-reset').click();
  await expect(page.locator('#pl-status')).toContainText('31 unique projects');
  await page.goBack();
  await expect(page).toHaveURL(namesakeURL);
  await expect(page.locator('[name=status]')).toHaveValue('name_match_elsewhere');
  await expect(page.locator('[name=include_elsewhere]')).toBeChecked();
  await expect(page.locator('#pl-list article')).toHaveCount(1);
  await page.goForward();
  await expect(page.locator('[name=status]')).toHaveValue('');
  await expect(page.locator('[name=dataset]')).toHaveValue('');
  await expect(page.locator('[name=include_elsewhere]')).not.toBeChecked();
  await expect(page.locator('#pl-status')).toContainText('31 unique projects');
});

test('URL filters hydrate and survive Back and Forward without losing all-program scope', async ({ page }) => {
  await setup(page);
  await page.goto('/map.html?query=Published+road+30&dataset=all&status=suspicious&municipality=0105501000&comparison=increased&suspicious=1&include_elsewhere=1');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  for (const [name, value] of Object.entries({ query: 'Published road 30', dataset: '', status: 'suspicious', municipality: '0105501000', comparison: 'increased' })) await expect(page.locator(`[name=${name}]`)).toHaveValue(value);
  for (const name of ['suspicious', 'include_elsewhere']) await expect(page.locator(`[name=${name}]`)).toBeChecked();
  await expect(page.locator('#pl-list article')).toHaveCount(1);
  await page.evaluate(() => history.pushState(null, '', location.href));
  await page.locator('#pl-reset').click();
  await page.goBack();
  await expect(page.locator('[name=query]')).toHaveValue('Published road 30');
  await expect(page.locator('[name=include_elsewhere]')).toBeChecked();
  await expect(page.locator('#pl-list article')).toHaveCount(1);
  await page.goForward();
  await expect(page.locator('[name=query]')).toHaveValue('');
  await expect(page.locator('[name=include_elsewhere]')).not.toBeChecked();
  await expect(page.locator('#pl-status')).toContainText('32 unique projects');
});

test('real default all-program search finds 6548 by exact title and both IDs', async ({ page }) => {
  const published = JSON.parse(fs.readFileSync(path.join(root, 'data/national-budget/2027/projects.json'), 'utf8'));
  const source = published.find(p => p.id === 'dpwh:house-reading:6548');
  await page.goto('/map.html');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  await expect(page.locator('[name=dataset]')).toHaveValue('');
  await expect(page.locator('[name=include_elsewhere]')).not.toBeChecked();
  for (const query of [source.title, source.id, '6548']) {
    await page.locator('[name=query]').fill(query);
    await expect(page.locator('#pl-list article')).toHaveCount(1);
    await expect(page.locator('#pl-list article')).toHaveAttribute('data-project-id', source.id);
  }
  const summary = await (await page.request.get('/data/project-locations/review-summary.json')).json();
  const namesake = summary.projects.find(p => p.dataset === 'fmr' && p.display_status === 'name_match_elsewhere');
  expect(namesake.title).toContain('Koronadal');
  await page.locator('[name=query]').fill(namesake.title);
  await expect(page.locator('#pl-list article')).toHaveCount(0);
  await page.locator('[name=include_elsewhere]').check();
  await expect(page.locator('#pl-list article')).toHaveCount(0);
  expect(namesake.id).toBe('fmr:house_only:ib:p722:r4');
  expect(namesake.segments[0].start).toEqual([124.908989, 6.486838]);
  expect(namesake.segments[0].end).toEqual([124.916314, 6.481725]);
});

test('real 6548 retains its single API point and compares the reviewed title coordinates as unverified', async ({ page }) => {
  const published = JSON.parse(fs.readFileSync(path.join(root, 'data/national-budget/2027/projects.json'), 'utf8'));
  expect(published).toHaveLength(732);
  const source = published.find(p => p.id === 'dpwh:house-reading:6548');
  expect(source).toBeTruthy();
  const original = [source.upstream.lon, source.upstream.lat];
  expect(original).toEqual([119.92525, 6.38299]);
  const detailSource = source.detail_evidence[0].envelope.data;
  expect([detailSource.lon, detailSource.lat]).toEqual(original);
  expect(source.title).toContain('16.38329, 119.92648');
  expect(source.upstream.nep_php).toBeNull();
  expect(source.upstream.house_php).toBe(350000000);
  await page.route('**/assets/leaflet/leaflet.js', route => route.fulfill({ contentType: 'text/javascript', body: `${leaflet}\nconst originalMap = L.map; L.map = (...args) => { const map = originalMap(...args); window.testLocationMap = map; return map; };` }));
  await page.goto(`/map.html?project=${encodeURIComponent(source.id)}`);
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  const summary = await (await page.request.get('/data/project-locations/review-summary.json')).json();
  const derived = summary.projects.find(p => p.id === source.id);
  expect(derived.segments).toHaveLength(1);
  expect(derived.segments[0].start).toEqual(original);
  const second = [119.92648, 16.38329];
  expect(derived.segments[0].end).toEqual(second);
  expect(derived.segments[0].geometry_kind).toBe('title_coordinate_comparison');
  expect(derived.segments[0].start_role).toBe('titleCoordinateFirst');
  expect(derived.segments[0].end_role).toBe('titleCoordinateSecond');
  expect(derived.segments[0].endpoint_roles_verified).toBe(false);
  expect(derived.segments[0].flags).toContain('endpoint_distance_over_200km_review');
  expect(derived.nep_php).toBeNull(); expect(derived.house_php).toBe(350000000);
  const geo = await (await page.request.get('/data/project-locations/projects.geojson')).json();
  const features = geo.features.filter(f => f.properties.project_id === source.id);
  expect(features).toHaveLength(3);
  expect(features.filter(f => f.geometry.type === 'Point').map(f => f.geometry.coordinates)).toEqual([original, second]);
  expect(features.every(f => f.properties.geometry_kind === 'title_coordinate_comparison')).toBe(true);
  expect(features.find(f => f.geometry.type === 'LineString').geometry.coordinates).toEqual([original, second]);
  expect(geo.features.filter(f => f.geometry.type === 'Point')).toHaveLength(207);
  expect(geo.features.filter(f => f.geometry.type === 'LineString')).toHaveLength(33);
  expect(summary.projects.filter(p => p.segments.some(s => s.start || s.end))).toHaveLength(174);
  await expect(page.locator('[name=dataset]')).toHaveValue('dpwh');
  await expect(page.locator('#pl-detail h2')).toHaveText(source.title);
  await expect(page.locator('#pl-detail')).toContainText('longitude 119.92525, latitude 6.38299');
  await expect(page.locator('#pl-detail')).toContainText('Second point (source title - unverified)');
  await expect(page.locator('#pl-detail')).toContainText('not a confirmed bridge alignment');
  const mapped = await page.evaluate(title => {
    const points = [], lines = [];
    window.testLocationMap.eachLayer(layer => {
      const tooltip = layer.getTooltip?.()?.getContent()?.textContent || '';
      if (!tooltip.includes(title)) return;
      if (layer.options.className === 'pl-map-endpoint') points.push([layer.getLatLng().lng, layer.getLatLng().lat]);
      else if (layer.options.dashArray === '6 6') lines.push({ dash: layer.options.dashArray, tooltip });
    });
    return { points, lines };
  }, source.title);
  expect(mapped.points).toEqual([original, second]);
  expect(mapped.lines).toHaveLength(1);
  expect(mapped.lines[0].dash).toBe('6 6');
  expect(mapped.lines[0].tooltip).toContain('unverified source-title coordinate comparison, not a bridge alignment');
  for (const label of ['View First Point', 'View Second Point', 'View Both']) await expect(page.locator('#pl-detail').getByRole('button', { name: label, exact: true })).toBeEnabled();
  await page.locator('#pl-detail').getByRole('button', { name: 'View Second Point', exact: true }).click();
  expect((await page.evaluate(() => window.testLocationMap.getCenter())).lat).toBeCloseTo(second[1], 3);
  await page.locator('#pl-detail').getByRole('button', { name: 'View First Point', exact: true }).click();
  const center = await page.evaluate(() => window.testLocationMap.getCenter());
  expect(center.lat).toBeCloseTo(original[1], 3); expect(center.lng).toBeCloseTo(original[0], 3);
});
