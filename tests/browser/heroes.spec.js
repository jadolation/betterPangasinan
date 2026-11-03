const { test, expect } = require('./tile-fixture');
const { readdirSync, readFileSync } = require('node:fs');
const path = require('node:path');

const pages = path.join(__dirname, '../../src/pages');
const routes = readdirSync(pages).filter(name => name.endsWith('.html') && /class="(?:hero"|page-hero\b)|\bwave-hero\b/.test(readFileSync(path.join(pages, name), 'utf8')));

for (const width of [375, 1440]) {
  test(`all blue heroes share the wave without overflow at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    expect(routes).toEqual(expect.arrayContaining(['transparency.html', 'national-budget.html', 'historical-budget.html', 'budget-context.html', 'budget-hearings.html']));
    for (const route of routes) {
      await page.goto('/' + route);
      const hero = page.locator('.hero, .page-hero, .wave-hero').first();
      await expect(hero).toBeVisible();
      const appearance = await hero.evaluate(node => {
        const box = node.getBoundingClientRect();
        const heading = node.querySelector('h1');
        const wave = getComputedStyle(node, '::after');
        return { background: getComputedStyle(node).backgroundColor, heading: getComputedStyle(heading).color,
          x: box.x, width: box.width, client: document.documentElement.clientWidth,
          overflow: document.documentElement.scrollWidth > innerWidth,
          contentBottom: heading.getBoundingClientRect().bottom, bottom: box.bottom,
          wave: wave.backgroundImage, waveHeight: wave.height };
      });
      expect(appearance.background, route).toBe('rgb(1, 64, 127)');
      expect(appearance.heading, route).toBe('rgb(255, 255, 255)');
      expect(Math.abs(appearance.x), route).toBeLessThanOrEqual(1);
      expect(Math.abs(appearance.width - appearance.client), route).toBeLessThanOrEqual(1);
      expect(appearance.overflow, route).toBe(false);
      expect(appearance.contentBottom, route).toBeLessThan(appearance.bottom - 50);
      if (route === 'index.html') await expect(hero.locator('.hero-divider svg')).toBeVisible();
      else {
        expect(appearance.wave, route).toContain('hero-wave.svg');
        expect(appearance.waveHeight, route).toBe('70px');
        await expect(hero.locator('.hero-divider')).toBeHidden();
      }
      if (['index.html', 'lgus.html', 'national-budget.html', 'transparency.html', 'historical-budget.html', 'budget-context.html', 'budget-hearings.html'].includes(route)) {
        await page.screenshot({ path: testInfo.outputPath(`hero-${route}-${width}.png`), fullPage: false });
      }
    }
    expect(errors).toEqual([]);
  });
}

test('wave decoration and Transparency headings work without JavaScript', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto('/national-budget.html');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  expect(await page.locator('.wave-hero').evaluate(node => getComputedStyle(node, '::after').backgroundImage)).toContain('hero-wave.svg');
  expect((await page.request.get('/assets/hero-wave.svg')).status()).toBe(200);
  await context.close();
});
