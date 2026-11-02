const { test, expect } = require('@playwright/test');
const { readFileSync, readdirSync } = require('node:fs');
const { join } = require('node:path');

function fixtures() {
  const directory = join(__dirname, '../../data/fixtures');
  return Object.fromEntries(readdirSync(directory).filter(name => name.endsWith('.json')).map(name => [
    name.replace('.json', ''), JSON.parse(readFileSync(join(directory, name), 'utf8')),
  ]));
}

async function intercept(page, { mode = 'test', data = fixtures() } = {}) {
  await page.route('**/data/public.json', route => route.fulfill({ json: data }));
  await page.route('**/*.html*', async route => {
    if (route.request().resourceType() !== 'document') return route.continue();
    const response = await route.fetch();
    const body = (await response.text()).replace(/(<meta name="data-mode" content=")[^"]+/, `$1${mode}`);
    await route.fulfill({ response, body });
  });
}

async function openData(page, url) {
  const fetched = page.waitForResponse(response => response.url().endsWith('/data/public.json') && response.ok());
  await page.goto(url);
  await (await fetched).finished();
  // Include dictionary fetches and rendering continuations before negative assertions.
  await page.waitForLoadState('networkidle');
}

test('synthetic directory renders four profiles and filters query and classification', async ({ page }) => {
  await intercept(page);
  await openData(page, '/lgus.html');
  await expect(page.locator('#lgu-result-count')).toHaveText('4 published profiles found. Showing 4.');
  await expect(page.locator('#lgu-results article')).toHaveCount(4);
  for (const record of fixtures().lgus) await expect(page.locator('#lgu-results')).toContainText(record.name);
  await page.locator('#lgu-query').fill('mapandan');
  await expect(page.locator('#lgu-results article')).toHaveCount(1);
  await expect(page.locator('#lgu-results')).toContainText('Mapandan');
  await page.locator('#lgu-type').selectOption('city');
  await expect(page.locator('#lgu-results article')).toHaveCount(0);
  await expect(page.locator('#lgu-empty')).toContainText('No matching profiles');
  await page.locator('#lgu-query').fill('');
  await expect(page.locator('#lgu-results article')).toHaveCount(1);
  await expect(page.locator('#lgu-results')).toContainText('Dagupan');
  await page.locator('#lgu-type').selectOption('municipality');
  await expect(page.locator('#lgu-results article')).toHaveCount(2);
  await page.getByRole('button', { name: 'Search LGUs' }).click();
  await expect(page).toHaveURL(/type=municipality/);
});

test('every synthetic LGU identifier renders its own profile and source', async ({ page }) => {
  await intercept(page);
  for (const record of fixtures().lgus) {
    await openData(page, `/lgu.html?id=${record.id}`);
    await expect(page.locator('#profile-name')).toHaveText(record.name);
    await expect(page.locator('#profile-content')).toBeVisible();
    await expect(page.locator('#profile-content')).toContainText('not yet collected');
    await page.locator('#profile-sources > details').first().locator('summary').first().click();
    await expect(page.locator('#profile-sources a[href="https://example.invalid/synthetic"]')).toBeVisible();
    await expect(page.locator('#profile-content a[href="#finances"]')).toBeVisible();
    const local = fixtures().finances.filter(row => row.lgu_id === record.id);
    if (local.length) for (const row of local) await expect(page.locator('#profile-finances')).toContainText(row.amount.toLocaleString('en-PH'));
    else await expect(page.locator('#profile-finances')).toContainText('No local finance records are available');
  }
});

test('synthetic finance selects 2026 appropriation and totals exactly 300.75', async ({ page }) => {
  await intercept(page);
  await openData(page, '/finances.html');
  await expect(page.locator('[data-module] tbody tr')).toHaveCount(2);
  await expect(page.locator('[data-module] [data-results]')).toContainText('No combined total');
  await page.locator('[data-module] select[name="year"]').selectOption('2026');
  await page.locator('[data-module] select[name="amount_type"]').selectOption('appropriation');
  await expect(page.locator('[data-module] [data-results]')).toContainText('Total for this selection: 300.75 PHP (PHP).');
  await expect(page.locator('[data-module] tbody tr')).toHaveCount(2);
  await expect(page.locator('meter')).toHaveCount(2);
  await openData(page, '/finances.html?lgu=mock-lgu-a');
  await expect(page.locator('[data-module] tbody tr')).toHaveCount(1);
  await expect(page.locator('[data-module] tbody')).toContainText('100.25');
});

test('project registry links to detail, procurement and contract records', async ({ page }) => {
  await intercept(page);
  await openData(page, '/projects.html');
  await page.locator('[data-module] [data-results] h3 a').click();
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveURL(/project\.html\?id=mock-project/);
  await expect(page.locator('[data-results]')).toContainText('Synthetic project');
  await expect(page.locator('[data-results]')).toContainText('Fictional Supplier Test Contract');
  await page.locator('[data-results] a[href*="procurement.html?id="]').click();
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveURL(/procurement\.html\?id=mock-procurement/);
  await expect(page.locator('[data-results] article')).toHaveCount(1);
  await expect(page.locator('[data-results]')).toContainText('Synthetic procurement');
  await expect(page.locator('[data-results]')).toContainText('Fictional Supplier Test Contract');
  await expect(page.locator('[data-results] a[href$="/project.html?id=mock-project"]')).toBeVisible();
});

test('legislation searches both legislation and document collections', async ({ page }) => {
  await intercept(page);
  await openData(page, '/legislation.html');
  await expect(page.locator('[data-module] [data-results] article')).toHaveCount(2);
  await page.locator('[data-module] [name="q"]').fill('legislation index');
  await expect(page.locator('[data-module] [data-results] article')).toHaveCount(1);
  await expect(page.locator('[data-module] [data-results]')).toContainText('Synthetic legislation');
  await page.locator('[data-module] [name="q"]').fill('not an audit finding');
  await expect(page.locator('[data-module] [data-results] article')).toHaveCount(1);
  await expect(page.locator('[data-module] [data-results]')).toContainText('Synthetic document');
  await page.locator('[data-module] [name="q"]').fill('nonexistent-record');
  await expect(page.locator('[data-module] [data-status]')).toContainText('No published records match');
  await expect(page.locator('[data-module] [data-results] article')).toHaveCount(0);
});

test('malformed identifiers remain inert and show missing-record states', async ({ page }) => {
  await intercept(page);
  const bad = encodeURIComponent('<script>window.badId=true</script>');
  await openData(page, `/lgu.html?id=${bad}`);
  await expect(page.locator('#profile-content')).toBeHidden();
  await expect(page.locator('#profile-status')).toBeVisible();
  await openData(page, `/project.html?id=${bad}`);
  await expect(page.locator('[data-status]')).toContainText('Project not found');
  await expect(page.locator('[data-results] article')).toHaveCount(0);
  await openData(page, `/procurement.html?id=${bad}`);
  await expect(page.locator('[data-status]')).toContainText('No published records match');
  await expect(page.locator('[data-results] article')).toHaveCount(0);
  expect(await page.evaluate(() => window.badId)).toBeUndefined();
});

test('production mode rejects every private synthetic collection and profile', async ({ page }) => {
  await intercept(page, { mode: 'production' });
  await openData(page, '/lgus.html');
  await expect(page.locator('#lgu-result-count')).toHaveText('0 published profiles found. Showing 0.');
  await expect(page.locator('#lgu-results article')).toHaveCount(0);
  await openData(page, '/lgu.html?id=mock-lgu-a');
  await expect(page.locator('#profile-content')).toBeHidden();
  for (const name of ['finances', 'projects', 'procurement', 'legislation', 'services', 'map', 'project']) {
    await openData(page, `/${name}.html?id=mock-project`);
    await expect(page.locator('[data-module] [data-results] article, [data-module] [data-results] tbody tr, [data-module] meter')).toHaveCount(0);
    await expect(page.locator('[data-module] [data-results]')).not.toContainText('Synthetic');
  }
});

test('mobile navigation remains visible without JavaScript', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 320, height: 812 } });
  const page = await context.newPage();
  try {
    await page.goto('/index.html');
    for (const link of await page.locator('#primary-navigation a').all()) await expect(link).toBeVisible();
    await expect(page.locator('.nav-toggle')).toBeHidden();
    await page.locator('#primary-navigation a[href="lgus.html"]').click();
    await expect(page).toHaveURL(/lgus\.html$/);
  } finally {
    await context.close();
  }
});

test('mobile navigation remains usable when its script fails to load', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 812 });
  await page.route('**/assets/script.js', route => route.abort('failed'));
  const failed = page.waitForEvent('requestfailed', request => request.url().endsWith('/assets/script.js'));
  await page.goto('/index.html');
  await failed;
  for (const link of await page.locator('#primary-navigation a').all()) await expect(link).toBeVisible();
  await expect(page.locator('.nav-toggle')).toBeHidden();
  await page.locator('#primary-navigation a[href="lgus.html"]').click();
  await expect(page).toHaveURL(/lgus\.html$/);
});

test('map CDN failure retains sourced text records', async ({ page }) => {
  const data = fixtures();
  // Browser-only fault injection exercises the library failure branch; never publishes geometry.
  data.geography[0] = { ...data.geography[0], verification_status: 'verified', license: 'CC0-1.0' };
  await intercept(page, { data });
  const failedLibrary = page.waitForEvent('requestfailed', request => request.url().includes('leaflet.js'));
  await page.route('https://unpkg.com/**', route => route.abort('failed'));
  await openData(page, '/map.html');
  await failedLibrary;
  await expect(page.locator('[data-status]')).toHaveText('The map could not load. Use the equivalent sourced text records below.');
  await expect(page.locator('[data-results]')).toContainText(data.geography[0].name);
  await expect(page.locator('[data-results] a[href="https://example.invalid/synthetic"]')).toBeVisible();
  await expect(page.locator('#project-map')).toBeHidden();
});
