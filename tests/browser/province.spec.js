const { test, expect } = require('@playwright/test');

test('homepage derives provincial KPIs and preserves the original hero', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#province-summary [data-province-status]')).toContainText('48 reviewed city and municipal profiles');
  await expect(page.locator('.province-kpi')).toHaveCount(6);
  await expect(page.locator('.province-kpis')).toContainText('3,188,540');
  await expect(page.locator('.province-kpis')).toContainText('1,364');
  await expect(page.locator('.province-kpis')).toContainText('0105500000');
  await expect(page.locator('[data-province-sources]')).toContainText('2024-07-01');
  await expect(page.locator('.hero-divider svg')).toBeVisible();
});

test('directory displays the 48 imported records and classification filters', async ({ page, request }) => {
  const records = await (await request.get('/data/lgus.json')).json();
  expect(records).toHaveLength(48);
  expect(records.reduce((sum, row) => sum + row.population, 0)).toBe(3188540);
  await page.goto('/lgus.html');
  await expect(page.locator('#lgu-results article')).toHaveCount(48);
  await expect(page.locator('#lgu-results')).toContainText('2024-07-01');
  await expect(page.locator('#lgu-results')).toContainText('2025-07-31');
  await page.locator('#lgu-type').selectOption('city');
  await expect(page.locator('#lgu-results article')).toHaveCount(4);
  await page.locator('#lgu-type').selectOption('municipality');
  await expect(page.locator('#lgu-results article')).toHaveCount(44);
  await page.locator('#lgu-query').fill('Mapandan');
  await expect(page.locator('#lgu-results article')).toHaveCount(1);
  const record = records.find(row => row.name === 'Mapandan');
  await expect(page.locator('#lgu-results')).toContainText(record.psgc);
  await expect(page.locator('#lgu-results')).toContainText(record.population.toLocaleString('en-PH'));
});

test('LGU profile joins population barangays and source links using PSGC', async ({ page, request }) => {
  const records = await (await request.get('/data/lgus.json')).json();
  const record = records.find(row => row.name === 'Mapandan');
  const barangays = await (await request.get('/data/geography/barangays.json')).json();
  const expected = barangays.filter(row => row.parent_psgc === record.psgc);
  await page.goto(`/lgu.html?id=${encodeURIComponent(record.id)}`);
  await expect(page.locator('#profile-name')).toHaveText(record.name);
  await expect(page.locator('#profile-content')).toContainText(record.population.toLocaleString('en-PH'));
  await expect(page.locator('.profile-barangays ul li')).toHaveCount(expected.length);
  await expect(page.locator('.profile-barangays')).toContainText('unofficial mirror');
  await page.getByLabel('Search barangays').fill(expected[0].name);
  await expect(page.locator('.profile-barangays ul')).toContainText(expected[0].name);
  await expect(page.locator(`a[href="municipality-map.html?psgc=${record.psgc}"]`)).toBeVisible();
  await expect(page.getByRole('link', { name: 'Search national proposal titles (not a verified allocation)' })).toHaveAttribute('href', /national-budget\.html\?q=Mapandan#projects/);
});

test('all production identifiers have profile routes without a synthetic fallback', async ({ page, request }) => {
  const records = await (await request.get('/data/lgus.json')).json();
  expect(new Set(records.map(row => row.psgc)).size).toBe(48);
  await page.goto(`/lgu.html?id=${encodeURIComponent(records[0].id)}`);
  await expect(page.locator('#profile-name')).toHaveText(records[0].name);
  await page.goto('/lgu.html?id=unknown-lgu');
  await expect(page.locator('#profile-status')).toBeVisible();
  await expect(page.locator('#profile-content')).toBeHidden();
});

test('province data failure remains unavailable rather than replacing values with zero', async ({ page }) => {
  await page.route('**/data/province-profile.json', route => route.fulfill({ status: 503, body: 'Unavailable' }));
  await page.goto('/');
  await expect(page.locator('[data-province-status]')).toContainText('could not be loaded');
  await expect(page.locator('.province-kpi')).toHaveCount(0);
});

for (const width of [320, 375, 430, 768, 1024, 1440]) {
  test(`populated homepage and registry fit ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 950 });
    for (const route of ['index.html', 'lgus.html']) {
      await page.goto('/' + route);
      if (route === 'index.html') await expect(page.locator('.province-kpi')).toHaveCount(6);
      else await expect(page.locator('#lgu-results article')).toHaveCount(48);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
      if (width === 375 || width === 1440) await page.screenshot({ path: testInfo.outputPath(`${route}-${width}.png`), fullPage: false });
    }
  });
}
