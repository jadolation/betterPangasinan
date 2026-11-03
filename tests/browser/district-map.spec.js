const { test, expect } = require('./tile-fixture');

test('fourth district selects exactly five existing polygons and preserves independent selections', async ({ page, request }) => {
  const response = await request.get('/data/government-leadership.json');
  expect(response.ok()).toBeTruthy();
  const data = await response.json();
  const fourth = data.districts.find(d => d.id === 'leg:pangasinan:4th');
  expect(fourth.lgu_psgcs).toHaveLength(5);
  const other = data.districts.find(d => d.id !== fourth.id);
  await page.goto('/municipality-map.html?view=districts&district=leg:pangasinan:4th');
  await expect(page.locator('svg [data-selected]')).toHaveCount(5);
  await expect(page.getByRole('button', { name: 'Legislative Districts', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('svg a')).toHaveCount(48);
  const peer = page.locator(`svg a[data-psgc="${other.lgu_psgcs[0]}"]`);
  await peer.focus();
  await expect(page.locator('svg [data-preview]')).toHaveCount(other.lgu_psgcs.length);
  await expect(page.locator('svg [data-selected]')).toHaveCount(5);
  await peer.press('Space');
  await expect(page.locator('svg [data-selected]')).toHaveCount(other.lgu_psgcs.length);
  await page.getByRole('button', { name: 'Municipalities', exact: true }).click();
  await expect(page.locator('svg [data-selected]')).toHaveCount(0);
  await page.locator('[data-map-select]').selectOption(fourth.lgu_psgcs[0]);
  await expect(page.locator('[data-map-profile]')).toHaveAttribute('href', `lgu.html?id=lgu-${fourth.lgu_psgcs[0]}`);
  await expect(page.locator('[data-map-detail]')).toContainText(fourth.name);
  await expect(page.locator(`[data-map-detail] a[href="government.html?official=${encodeURIComponent(fourth.representative_id)}#provincial-leadership"]`)).toHaveCount(1);
  await page.getByRole('button', { name: 'Legislative Districts', exact: true }).click();
  await expect(page.locator('svg [data-selected]')).toHaveCount(other.lgu_psgcs.length);
  const target = page.locator(`svg a[data-psgc="${fourth.lgu_psgcs[0]}"]`);
  await target.focus(); await target.press('Enter');
  await expect(page.locator('svg [data-selected]')).toHaveCount(5);
  await page.locator('[data-map-search]').focus();
  await expect(page.locator('svg [data-preview]')).toHaveCount(0);
  await expect(page.locator('svg [data-selected]')).toHaveCount(5);
  await page.locator('[data-map-detail] summary').click();
  await expect(page.locator('[data-map-detail] details a')).toHaveCount(5);
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

for (const failure of ['404', 'malformed', 'invalid mapping']) {
  test(`optional leadership ${failure} does not break municipalities`, async ({ page }) => {
    await page.route('**/data/government-leadership.json', route => route.fulfill({ status: failure === '404' ? 404 : 200, contentType: 'application/json', body: failure === 'malformed' ? '{' : JSON.stringify({ schema_version: 1, officials: [], districts: [] }) }));
    await page.goto('/municipality-map.html');
    await expect(page.locator('[data-map-status]')).toContainText('48/48');
    await page.locator('[data-map-select]').selectOption('0105516000');
    await expect(page.locator('[data-map-profile]')).toHaveAttribute('href', 'lgu.html?id=lgu-0105516000');
    await page.getByRole('button', { name: 'Legislative Districts', exact: true }).click();
    await expect(page.locator('[data-map-detail]')).toContainText('District information is unavailable');
    await expect(page.locator('svg a')).toHaveCount(48);
    await page.getByRole('button', { name: 'Municipalities', exact: true }).click();
    await expect(page.locator('svg [data-selected]')).toHaveCount(1);
  });
}
