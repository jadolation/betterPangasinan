const { test, expect } = require('./tile-fixture');
const { createHash } = require('node:crypto');

const localData = () => Object.fromEntries(['finances', 'projects', 'procurements', 'contracts', 'geography', 'legislation', 'documents', 'services', 'statistics'].map(name => [name, []]));
function publication(rows = [{ id: 'synthetic:one', publication_status: 'approved', snapshot_id: 'SYNTHETIC' }]) {
  const data = { projects: rows, offices: [], coverage: { complete: false }, sources: {} };
  data.manifest = {
    status: 'approved', snapshot_id: 'SYNTHETIC', retrieved_at: '2026-11-01T00:00:00Z',
    files: Object.fromEntries(Object.entries(data).map(([name, value]) => [`${name}.json`, createHash('sha256').update(JSON.stringify(value)).digest('hex')])),
  };
  return data;
}
async function mock(page, { data = publication(), local = localData(), broken = '' } = {}) {
  await page.route('**/data/public.json', route => route.fulfill({ json: local }));
  await page.route('**/data/national-budget/2027/*.json', route => {
    const name = new URL(route.request().url()).pathname.split('/').pop().replace('.json', '');
    if (broken === name) return route.fulfill({ status: 503, body: 'Unavailable' });
    return route.fulfill({ json: data[name] });
  });
}

test('landing derives budget availability and distinguishes empty local coverage', async ({ page }) => {
  await mock(page);
  await page.goto('/transparency.html');
  await expect(page.locator('#tp-budget-status')).toContainText('1 approved comparison records published.');
  await expect(page.locator('#tp-budget-status')).toContainText('Collection coverage is incomplete');
  await expect(page.locator('#tp-budget-meta')).toContainText('SYNTHETIC');
  await expect(page.locator('#tp-budget-provenance')).not.toHaveAttribute('open');
  await page.locator('#tp-budget-provenance summary').click();
  await expect(page.locator('#tp-budget-meta')).toBeVisible();
  await expect(page.locator('[data-local][data-state="empty"]')).toHaveCount(7);
  await expect(page.locator('.nav-links a[aria-current="page"]')).toHaveText('Transparency');
  for (const name of ['national-budget', 'projects', 'finances', 'procurement', 'map', 'legislation', 'services', 'statistics']) {
    await expect(page.locator(`main a[href="${name}.html"]`).first()).toBeVisible();
  }
  await expect(page.locator('.site-footer a[href="projects.html"]')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Historical national budgets 2020-2026' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Historical national budgets 2020-2026' })).toHaveAttribute('href', 'historical-budget.html');
});

for (const width of [320, 375, 430, 768, 1024, 1440]) {
  test(`real transparency landing fits ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 950 });
    await page.goto('/transparency.html');
    await expect(page.locator('#tp-budget-status')).not.toHaveAttribute('data-state', 'loading');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    if (width === 375 || width === 1440) await page.screenshot({ path: testInfo.outputPath(`transparency-${width}.png`), fullPage: true });
  });
}

test('landing counts approved non-mock local records only, even in test mode', async ({ page }) => {
  const local = localData();
  local.projects = [
    { id: 'approved', is_mock: false, publication_status: 'approved' },
    { id: 'mock', is_mock: true, publication_status: 'approved' },
    { id: 'pending', is_mock: false, publication_status: 'pending' },
    { id: 'missing-mock-status', publication_status: 'approved' },
  ];
  local.procurements = [{ id: 'p', is_mock: false, publication_status: 'approved' }];
  local.contracts = [{ id: 'c', is_mock: false, publication_status: 'approved' }];
  await mock(page, { local });
  await page.goto('/transparency.html');
  await expect(page.locator('[data-local="projects"]')).toHaveText('1 approved local record published.');
  await expect(page.locator('[data-local="procurements,contracts"]')).toHaveText('2 approved local records published.');
});

for (const scenario of ['approved-empty', 'unavailable', 'checksum', 'missing-checksum', 'missing-asset', 'snapshot', 'duplicate', 'unapproved', 'malformed-metadata']) {
  test(`landing handles ${scenario} without publishing an assumed count`, async ({ page }) => {
    let data = publication();
    if (scenario === 'approved-empty') data = publication([]);
    if (scenario === 'unavailable') data.manifest.status = 'unavailable';
    if (scenario === 'checksum') data.manifest.files['projects.json'] = '0'.repeat(64);
    if (scenario === 'missing-checksum') delete data.manifest.files['sources.json'];
    if (scenario === 'snapshot') data = publication([{ ...data.projects[0], snapshot_id: 'OTHER' }]);
    if (scenario === 'duplicate') data = publication([data.projects[0], data.projects[0]]);
    if (scenario === 'unapproved') data = publication([{ ...data.projects[0], publication_status: 'pending' }]);
    if (scenario === 'malformed-metadata') {
      data.sources = [];
      data.manifest.files['sources.json'] = createHash('sha256').update('[]').digest('hex');
    }
    await mock(page, { data, broken: scenario === 'missing-asset' ? 'offices' : '' });
    await page.goto('/transparency.html');
    const state = ['approved-empty', 'unavailable'].includes(scenario) ? 'empty' : 'unavailable';
    await expect(page.locator('#tp-budget-status')).toHaveAttribute('data-state', state);
    await expect(page.locator('#tp-budget-status')).not.toContainText('1 approved');
    await expect(page.locator('[data-local="projects"]')).toHaveAttribute('data-state', 'empty');
  });
}

test('local failures are independent and malformed collections are not reported as empty', async ({ page }) => {
  const local = localData();
  local.projects = null;
  await mock(page, { local });
  await page.goto('/transparency.html');
  await expect(page.locator('[data-local="projects"]')).toHaveAttribute('data-state', 'unavailable');
  await expect(page.locator('[data-local="finances"]')).toHaveAttribute('data-state', 'empty');
  await expect(page.locator('#tp-budget-status')).toHaveAttribute('data-state', 'available');
  await page.route('**/data/public.json', route => route.fulfill({ status: 500, body: 'Unavailable' }));
  await page.reload();
  await expect(page.locator('[data-local][data-state="unavailable"]')).toHaveCount(7);
  await expect(page.locator('#tp-budget-status')).toHaveAttribute('data-state', 'available');
});

test('loading does not assume a budget count before the manifest arrives', async ({ page }) => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await mock(page);
  await page.route('**/data/national-budget/2027/manifest.json', async route => {
    await gate;
    await route.fulfill({ json: publication().manifest });
  });
  try {
    await page.goto('/transparency.html', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#tp-budget-status')).toHaveAttribute('data-state', 'loading');
    await expect(page.locator('#tp-budget-status')).toContainText('No record count is assumed');
    await expect(page.locator('#tp-budget-meta')).toBeHidden();
  } finally { release(); }
  await expect(page.locator('#tp-budget-status')).toHaveAttribute('data-state', 'available');
});

test('landing works under a deployment prefix with relative module and data URLs', async ({ page }) => {
  await mock(page);
  await page.route('**/preview/**', async route => {
    if (new URL(route.request().url()).pathname.includes('/data/')) return route.fallback();
    const response = await route.fetch({ url: route.request().url().replace('/preview/', '/') });
    await route.fulfill({ response });
  });
  await page.goto('/preview/transparency.html');
  await expect(page.locator('#tp-budget-status')).toHaveAttribute('data-state', 'available');
  await expect(page.locator('main a[href="projects.html"]').first()).toHaveJSProperty('href', 'http://127.0.0.1:8765/preview/projects.html');
});

test('no-JavaScript landing keeps module links and explains unchecked availability', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:8765/transparency.html');
  await expect(page.getByText(/Availability checks require JavaScript\. No counts are assumed/)).toBeVisible();
  await expect(page.locator('main a[href="national-budget.html"]').first()).toBeVisible();
  await context.close();
});

for (const [url, label, current] of [
  ['/transparency.html', 'Transparency', 'page'],
  ['/projects.html', 'Transparency', 'location'],
  ['/national-budget.html', 'Transparency', 'location'],
  ['/lgu.html', 'Explore Pangasinan', 'location'],
]) {
  test(`primary navigation identifies ${url}`, async ({ page }) => {
    await mock(page);
    await page.goto(url);
    await expect(page.locator('.nav-links a[aria-current]')).toHaveText(label);
    await expect(page.locator('.nav-links a[aria-current]')).toHaveAttribute('aria-current', current);
  });
}
