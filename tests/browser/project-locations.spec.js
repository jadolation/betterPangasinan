const { test, expect } = require('@playwright/test');
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
    return { center: m.getCenter(), source, connections, crs: m.options.crs === L.CRS.EPSG4326 };
  });
  expect(state.crs).toBe(true); expect(state.center.lat).toBeGreaterThan(15); expect(state.center.lat).toBeLessThan(17);
  expect(state.source).toHaveLength(62); expect(state.source).toContainEqual([123.45, -65.25]);
  expect(state.connections).toHaveLength(31); expect(state.connections).toContainEqual([[123.45, -65.25], [123.46, -65.26]]);
  // Existing site typography uses Google Fonts; mapping itself is self-hosted.
  expect(external.filter(url => !['fonts.googleapis.com', 'fonts.gstatic.com'].includes(new URL(url).hostname))).toEqual([]);
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
  await expect(page.locator('[name=status]')).toHaveValue('suspicious');
  await expect(page.locator('[name=suspicious]')).not.toBeChecked();
  await page.locator('#pl-overview').click();
  expect(await page.evaluate(() => window.testLocationMap.getCenter().lat)).toBeGreaterThan(15);
});
test('map endpoint selection jumps list page without changing filters', async ({ page }) => {
  await setup(page); await page.goto('/map.html');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  await page.evaluate(() => window.testLocationMap.eachLayer(l => { if (l.options.className === 'pl-map-endpoint' && l.getLatLng().lat === -65.25) l.fire('click'); }));
  await expect(page.locator('#pl-page')).toHaveText('2 / 2');
  await expect(page.locator('#pl-list article[aria-current=true]')).toHaveAttribute('data-project-id', 'fmr-30');
  await expect(page.locator('[name=dataset]')).toHaveValue('fmr');
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
  await expect(page.locator('#pl-map-status')).toContainText('Local boundary reference unavailable');
  await expect(page.locator('#pl-detail')).toContainText('longitude 123.45, latitude -65.25');
  await expect(page.locator('#pl-map')).toBeHidden();
});
test('valid polar latitude is not Web Mercator clamped', async ({ page }) => {
  const data = fixture(); data.summary.projects[0].segments[0].start = [120, 90]; data.geo.features[0].geometry.coordinates = [120, 90]; data.geo.features[2].geometry.coordinates[0] = [120, 90];
  await setup(page, data); await page.goto('/map.html');
  await expect(page.locator('#project-locations')).toHaveAttribute('data-ready', 'true');
  expect(await page.evaluate(() => { const values = []; window.testLocationMap.eachLayer(l => { if (l.options.className === 'pl-map-endpoint') values.push(l.getLatLng().lat); }); return values; })).toContain(90);
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
  await expect(page.locator('#pl-status')).toContainText('32 unique projects');
  await expect(page.locator('#pl-list article')).toHaveCount(25);
  await page.locator('#pl-list article button').first().click();
  await expect(page.locator('#pl-detail')).toContainText('Source segment');
});
