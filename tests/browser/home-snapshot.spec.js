const { test, expect } = require('@playwright/test');

test('homepage has the exact six-section journey and no obsolete blocks', async ({ page }) => {
  await page.goto('/');
  const sections = await page.locator('main > section').evaluateAll(nodes => nodes.map(node => node.id || (node.classList.contains('hero') ? 'hero' : 'unknown')));
  expect(sections).toEqual(['hero', 'province-summary', 'community-map', 'transparency-snapshot', 'government-snapshot', 'public-knowledge']);
  await expect(page.locator('#home-search, .search-panel, main .community-band, main .feature-number')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Your province, in perspective.' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Sources before headlines.' })).toHaveCount(0);
  await expect(page.locator('#public-knowledge')).toContainText('Useful information.');
  await expect(page.locator('#public-knowledge')).toContainText('Without the runaround.');
  await expect(page.getByRole('link', { name: 'Explore all public resources' })).toHaveAttribute('href', 'projects.html');
  await expect(page.locator('#government-snapshot a[href="volunteer.html"]')).toBeVisible();
});

test('snapshot cards link to real modules and use only a lightweight summary', async ({ page, request }) => {
  const urls = [];
  page.on('request', request => urls.push(request.url()));
  const summary = await (await request.get('/data/home-snapshot.json')).json();
  await page.goto('/');
  await expect(page.locator('[data-home-metric="budget"]')).toContainText(String(summary.transparency.budget_2027_records));
  await expect(page.locator('[data-home-metric="historical"]')).toContainText(summary.transparency.historical_programs.toLocaleString('en-PH'));
  await expect(page.locator('[data-home-metric="finances"]')).toContainText('reported budget observations');
  await expect(page.locator('[data-home-services-status]')).toContainText('not yet populated');
  for (const [id, routes] of [
    ['transparency-snapshot', ['national-budget.html', 'historical-budget.html', 'budget-hearings.html', 'finances.html']],
    ['government-snapshot', ['government.html', 'hospitals.html', 'services.html', 'lgus.html']],
  ]) for (const route of routes) {
    await expect(page.locator(`#${id} a[href="${route}"]`).first()).toBeVisible();
    expect((await request.get('/' + route)).ok()).toBeTruthy();
  }
  expect(urls.some(url => /data\/national-budget\/2027\/projects.json|data\/historical-budget\/programs.json/.test(url))).toBe(false);
  expect(urls.filter(url => url.endsWith('/data/geography/municipalities.geojson'))).toHaveLength(1);
});

test('summary failure keeps useful links without zero substitutions', async ({ page }) => {
  await page.route('**/data/home-snapshot.json', route => route.fulfill({ status: 503, body: 'Unavailable' }));
  await page.goto('/');
  await expect(page.locator('[data-home-metric]:visible')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Explore Transparency', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Explore Government', exact: true })).toBeVisible();
});

test('unknown counts stay hidden while successful zero query results remain valid', async ({ page }) => {
  await page.route('**/data/home-snapshot.json', route => route.fulfill({ json: { schema_version: 1,
    transparency: { budget_2027_records: null, historical_programs: null, hearing_topics: 0, local_finance_records: 0, local_budget_observations: null },
    government: { local_governments: 48, service_records: 0 } } }));
  await page.goto('/');
  await expect(page.locator('[data-home-metric="hearings"]')).toContainText('0');
  for (const key of ['budget', 'historical', 'finances']) await expect(page.locator(`[data-home-metric="${key}"]`)).toBeHidden();
});

test('snapshot links have visible keyboard focus without raw source dumps', async ({ page }) => {
  await page.goto('/');
  const first = page.locator('#transparency-snapshot .home-feature').first();
  await first.focus(); await expect(first).toBeFocused();
  expect(await first.evaluate(node => getComputedStyle(node).outlineStyle)).not.toBe('none');
  await expect(page.locator('#transparency-snapshot pre, #government-snapshot pre, #transparency-snapshot table')).toHaveCount(0);
});

for (const width of [375, 430, 768, 1024, 1440]) {
  test(`snapshots fit ${width}px with public knowledge last`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/');
    await expect(page.locator('[data-home-metric="budget"]')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    if (width === 375 || width === 1440) for (const section of ['transparency-snapshot', 'government-snapshot', 'public-knowledge']) {
      await page.locator('#' + section).evaluate(node => window.scrollTo({ top: node.getBoundingClientRect().top + scrollY - 85, behavior: 'instant' }));
      await page.screenshot({ path: testInfo.outputPath(`${section}-${width}.png`), fullPage: false });
    }
  });
}
