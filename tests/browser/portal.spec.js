const { test, expect } = require('@playwright/test');
const { readdirSync } = require('node:fs');
const { join } = require('node:path');

const pages = readdirSync(join(__dirname, '../../src/pages')).filter(name => name.endsWith('.html')).sort();
const widths = [320, 375, 430, 768, 1440];

for (const width of widths) {
  test(`all pages fit ${width}px, load logos, and expose main landmarks`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    for (const name of pages) {
      const response = await page.goto(`/${name}`);
      expect(response.status(), name).toBe(200);
      await page.evaluate(() => document.fonts.ready);
      await expect(page.locator('main')).toHaveCount(1);
      await expect(page.locator('main h1')).toHaveCount(1);
      const logos = page.locator('img[src$="logo.svg"]');
      expect(await logos.count(), `${name}: logo exists`).toBeGreaterThan(0);
      for (const logo of await logos.all()) {
        await expect(logo).toBeVisible();
        await expect.poll(() => logo.evaluate(img => img.complete && img.naturalWidth > 0)).toBe(true);
      }
      const dimensions = await page.evaluate(() => ({
        viewport: document.documentElement.clientWidth,
        document: document.documentElement.scrollWidth,
        body: document.body.scrollWidth,
      }));
      expect(dimensions.document, `${name}: ${JSON.stringify(dimensions)}`).toBeLessThanOrEqual(dimensions.viewport + 1);
      expect(dimensions.body, `${name}: body overflow`).toBeLessThanOrEqual(dimensions.viewport + 1);
      if (['index.html', 'lgus.html', 'finances.html'].includes(name)) {
        await page.screenshot({ path: testInfo.outputPath(`${name.replace('.html', '')}-${width}.png`), fullPage: true });
      }
    }
    expect(errors).toEqual([]);
  });
}

test('mobile navigation opens with keyboard, exposes links, and closes on Escape', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/');
  const toggle = page.locator('.nav-toggle');
  await expect(toggle).toBeVisible();
  await toggle.focus();
  await page.keyboard.press('Enter');
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('#primary-navigation a')).toHaveText(['Home', 'Transparency', 'Explore Pangasinan', 'Government', 'About']);
  await expect(page.locator('#primary-navigation a').nth(1)).toHaveAttribute('href', 'transparency.html');
  await expect(page.locator('#primary-navigation a').nth(2)).toHaveAttribute('href', 'lgus.html');
  await expect(page.locator('#primary-navigation a').nth(3)).toHaveAttribute('href', 'government.html');
  await page.keyboard.press('Tab');
  await expect(page.locator('#primary-navigation a').first()).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(toggle).toBeFocused();
  await page.keyboard.press('Space');
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
});

test('skip link moves keyboard focus to the main landmark', async ({ page }) => {
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(page.locator('.skip-link')).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('main')).toBeFocused();
});

test('homepage internal links resolve and search returns to the populated LGU directory', async ({ page, request }) => {
  await page.goto('/');
  const links = await page.locator('a[href]').evaluateAll(items => [...new Set(items.map(a => new URL(a.getAttribute('href'), location.href).href))].filter(url => url.startsWith(location.origin)));
  for (const url of links) expect((await request.get(url)).status(), url).toBe(200);
  await page.locator('#home-search').fill('NoSuchMunicipality');
  await page.locator('#home-search').press('Enter');
  await expect(page).toHaveURL(/lgus\.html\?q=NoSuchMunicipality/);
  await expect(page.locator('#lgu-query')).toHaveValue('NoSuchMunicipality');
  await expect(page.locator('#lgu-result-count')).toHaveText('0 published profiles found. Showing 0.');
  await expect(page.locator('#lgu-empty')).toBeVisible();
  await expect(page.locator('#lgu-results').locator('article')).toHaveCount(0);
  await page.locator('#lgu-query').fill('');
  await page.getByRole('button', { name: 'Search LGUs' }).click();
  await expect(page).toHaveURL(/\/lgus\.html$/);
  await expect(page.locator('#lgu-empty')).toBeHidden();
  await expect(page.locator('#lgu-results article')).toHaveCount(12);
  await expect(page.locator('#lgu-result-count')).toContainText('48 published profiles');
});

for (const name of ['finances', 'projects', 'procurement', 'legislation', 'services', 'map', 'project']) {
  test(`${name} shows an honest empty state without fabricated records`, async ({ page }) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const loaded = page.waitForResponse(response => response.url().endsWith('/data/public.json') && response.ok());
    await page.goto(`/${name}.html`);
    const root = page.locator('[data-module]');
    if (name === 'finances') await page.locator('[data-ledger-disclosure] > summary').click();
    await expect(root).toBeVisible();
    await (await loaded).finished();
    await page.waitForLoadState('networkidle');
    await expect(root.locator('[data-status]')).toContainText(/not yet|no |not found|unavailable/i);
    await expect(root.locator('[data-results] article')).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}
