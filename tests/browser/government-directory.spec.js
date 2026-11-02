const { test, expect } = require('@playwright/test');

test('government directory separates leadership, board, House and pending evidence', async ({ page }) => {
  await page.goto('/government.html');
  const root = page.locator('[data-government-directory]');
  await expect(root.locator('[data-gd-status]')).toContainText('22 officials shown');
  await expect(root.locator('.gd-card')).toHaveCount(22);
  await expect(root.getByRole('heading', { name: 'Provincial Leadership', exact: true })).toBeVisible();
  await expect(root.locator('img')).toHaveCount(0);
  const vice = root.locator('#official-vice-governor-mark-ronald-lambino');
  await expect(vice).toContainText('Mark Ronald De Guzman Lambino');
  await expect(vice.locator('a[href^="tel:"]')).toHaveCount(0);
  await expect(root.locator('a[href="tel:+63756323138"]')).toHaveCount(1);
  await expect(root).toContainText('HTTP 403');
  await root.getByText('Pending position evidence: PCL representative', { exact: true }).click();
  await expect(root).toContainText('No current person confirmed');
  await expect(page.locator('[data-reference="government"] form')).toBeVisible();
});

test('district and community search preserve URL state and link the district map', async ({ page }) => {
  await page.goto('/government.html');
  const root = page.locator('[data-government-directory]');
  await expect(root.locator('.gd-card')).toHaveCount(22);
  await root.locator('#gd-district').selectOption('leg:pangasinan:4th');
  await expect(root.locator('.gd-card')).toHaveCount(7);
  await expect(root.locator('a[href="municipality-map.html?view=districts&district=leg%3Apangasinan%3A4th"]')).toHaveCount(3);
  await page.reload();
  await expect(root.locator('#gd-district')).toHaveValue('leg:pangasinan:4th');
  await root.locator('#gd-search').fill('Dagupan');
  await expect(root.locator('.gd-card')).toHaveCount(3);
  await root.getByRole('button', { name: 'Clear', exact: true }).click();
  await expect(root.locator('.gd-card')).toHaveCount(22);
});

test('official deep link distinguishes Governor and fifth district representative', async ({ page }) => {
  await page.goto('/government.html?official=house-5#provincial-leadership');
  const root = page.locator('[data-government-directory]');
  await expect(root.locator('.gd-card')).toHaveCount(1);
  await expect(root.locator('.gd-card')).toContainText('Ramon N. Guico Jr.');
  await expect(root.locator('.gd-card')).not.toContainText('Ramon V. Guico III');
});

test('unavailable directory leaves existing reference explorer intact', async ({ page }) => {
  await page.route('**/data/government-leadership.json', route => route.fulfill({ status: 503, body: '' }));
  await page.goto('/government.html');
  await expect(page.locator('[data-gd-status]')).toContainText('Government directory unavailable');
  await expect(page.locator('[data-reference="government"] form')).toBeVisible();
});

for (const width of [375, 1440]) {
  test(`government directory fits ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/government.html');
    await expect(page.locator('[data-government-directory] .gd-card')).toHaveCount(22);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  });
}
