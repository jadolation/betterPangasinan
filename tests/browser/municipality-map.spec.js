const { test, expect } = require('@playwright/test');

test('map separates preview and selection and provides explicit profile links', async ({ page }) => {
  await page.goto('/municipality-map.html');
  await expect(page.locator('[data-map-status]')).toContainText('48/48');
  await expect(page.locator('svg a')).toHaveCount(48);
  await expect(page.locator('[data-map-list] a')).toHaveCount(48);
  await expect(page.locator('svg [data-selected]')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Municipalities', exact: true })).toHaveAttribute('aria-pressed', 'true');
  const boundary = page.locator('svg a[data-psgc="0105516000"]');
  await boundary.focus();
  await expect(page.locator('[data-map-detail]')).toContainText('Burgos');
  await expect(page.locator('svg [data-selected]')).toHaveCount(0);
  await boundary.press('Space');
  await expect(boundary).toHaveAttribute('data-selected', '');
  await expect(page.locator('[data-map-profile]')).toHaveAttribute('href', 'lgu.html?id=lgu-0105516000');
  await expect(page).toHaveURL(/municipality-map\.html$/);
  await page.locator('svg a[data-psgc="0105501000"]').focus();
  await expect(boundary).toHaveAttribute('data-selected', '');
  await page.locator('[data-map-search]').focus();
  await expect(page.locator('[data-map-detail]')).toContainText('Burgos');
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test('failed geography does not fabricate boundaries', async ({ page }) => {
  await page.route('**/data/geography/*', route => route.abort());
  await page.goto('/municipality-map.html');
  await expect(page.locator('[data-map-status]')).toContainText('could not be loaded');
  await expect(page.locator('svg a')).toHaveCount(0);
});

test('explicit query selects requested municipality', async ({ page }) => {
  await page.goto('/municipality-map.html?psgc=0105516000');
  await expect(page.locator('[data-map-detail]')).toContainText('Burgos');
  await expect(page.locator('svg [data-selected]')).toHaveCount(1);
});
