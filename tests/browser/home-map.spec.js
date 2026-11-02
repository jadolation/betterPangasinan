const { test, expect } = require('@playwright/test');

test('home map follows summary and searchable selector selects without navigating', async ({ page }) => {
  await page.goto('/');
  const host = page.locator('#community-map');
  await expect(page.locator('#province-summary + #community-map')).toHaveCount(1);
  await expect(host.locator('[data-map-status]')).toContainText('48/48');
  await expect(host.locator('[data-selected]')).toHaveCount(0);
  await host.locator('[data-map-search]').fill('Burgos');
  await expect(host.locator('select option')).toHaveCount(2);
  await host.locator('[data-map-select]').selectOption('0105516000');
  await expect(host.locator('[data-map-detail]')).toContainText('Burgos');
  await expect(host.locator('[data-map-profile]')).toHaveAttribute('href', 'lgu.html?id=lgu-0105516000');
  for (const width of [320, 375, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  }
});

test('dynamic profile instances share sources and preserve callback records', async ({ page }) => {
  const requests = [];
  page.on('request', request => { if (request.url().endsWith('/municipalities.geojson')) requests.push(request.url()); });
  await page.goto('/');
  await expect(page.locator('#community-map [data-map-status]')).toContainText('48/48');
  const result = await page.evaluate(async () => {
    const container = document.createElement('div'); document.body.append(container);
    const selections = [], previews = [];
    const instance = window.createMunicipalityMap({ container, mode: 'profile', selectedPsgc: '0105516000', onSelect: record => selections.push(record), onPreview: record => previews.push(record) });
    await instance.ready;
    const initial = container.querySelector('[data-selected]').dataset.psgc;
    container.querySelector('[data-psgc="0105501000"]').dispatchEvent(new Event('pointerenter'));
    const unchanged = selections.length === 0 && container.querySelector('[data-selected]').dataset.psgc === initial;
    instance.select('0105501000');
    const record = selections[0];
    const outcome = { initial, unchanged, preview: previews[0].psgc, id: record.id, population: record.population, date: record.population_reference_date, geoHash: record.geography.source_sha256, censusHash: record.source_sha256, count: container.querySelectorAll('svg a').length };
    instance.destroy(); outcome.destroyed = container.children.length === 0; return outcome;
  });
  expect(result).toMatchObject({ initial: '0105516000', unchanged: true, preview: '0105501000', id: 'lgu-0105501000', date: '2024-07-01', count: 48, destroyed: true });
  expect(result.population).toBeGreaterThan(0);
  expect(result.geoHash).not.toBe(result.censusHash);
  expect(requests).toHaveLength(1);
});
