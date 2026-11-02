const { test, expect } = require('@playwright/test');

test('municipality map exposes sourced keyboard links and text alternative', async ({ page }) => {
  await page.goto('/municipality-map.html');
  await expect(page.locator('[data-map-status]')).toContainText('48/48');
  await expect(page.locator('svg a')).toHaveCount(48);
  await expect(page.locator('[data-map-list] a')).toHaveCount(48);
  const boundary = page.locator('svg a').first();
  await boundary.focus();
  await expect(page.locator('[data-map-detail]')).toContainText('population');
  await expect(page.locator('[data-map-detail]')).toContainText('barangays 39');
  await expect(boundary).toHaveAttribute('href', /^lgu\.html\?id=lgu-\d{10}$/);
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test('failed geography does not fabricate boundaries', async ({ page }) => {
  await page.route('**/data/geography/*', route => route.abort());
  await page.goto('/municipality-map.html');
  await expect(page.locator('[data-map-status]')).toContainText('could not be loaded');
  await expect(page.locator('svg a')).toHaveCount(0);
});

test('profile query selects the requested municipality', async ({ page }) => {
  await page.goto('/municipality-map.html?psgc=0105516000');
  await expect(page.locator('[data-map-detail]')).toContainText('Burgos');
  await expect(page.locator('svg [data-selected]')).toHaveCount(1);
});
