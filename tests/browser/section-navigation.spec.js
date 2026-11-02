const { test, expect } = require('@playwright/test');

const labels = ['Overview', '2027 Projects', 'Historical Budgets', 'Offices & Districts', 'Context', 'Hearings', 'Local Finances', 'About'];

test('canonical section navigation is outside main on designated pages only', async ({ page }) => {
  for (const path of ['transparency', 'national-budget', 'historical-budget', 'budget-context', 'budget-hearings', 'finances', 'methodology', 'projects', 'procurement', 'legislation', 'map']) {
    await page.goto(`/${path}.html`);
    const nav = page.getByRole('navigation', { name: 'Transparency sections', exact: true });
    await expect(nav).toHaveCount(1);
    await expect(nav.getByRole('link')).toHaveText(labels);
    await expect(page.locator('main [data-section-nav], main .tp-nav, main nav[aria-label="Budget evidence"]')).toHaveCount(0);
  }
  for (const path of ['index', 'lgu', 'government']) {
    await page.goto(`/${path}.html`);
    await expect(page.locator('[data-section-nav]')).toHaveCount(0);
  }
});

test('national budget hash navigation exposes one correct current location', async ({ page }) => {
  await page.goto('/national-budget.html');
  const current = page.locator('[data-section-nav] [aria-current]');
  await expect(current).toHaveText('2027 Projects');
  for (const [hash, label] of [['offices', 'Offices & Districts'], ['about-data', 'About'], ['unknown-section', '2027 Projects'], ['projects', '2027 Projects']]) {
    await page.evaluate(value => { location.hash = value; }, hash);
    await expect(current).toHaveCount(1);
    await expect(current).toHaveText(label);
    await expect(current).toHaveAttribute('aria-current', 'location');
  }
  await expect(page.locator('[data-section-item="about"]')).toHaveAttribute('href', 'methodology.html#national-budget-methodology');
});

test('same-module links preserve query filters without reloading publication files', async ({ page }) => {
  let requests = 0;
  page.on('request', request => {
    if (/\/data\/national-budget\/2027\/[^/]+\.json$/.test(request.url())) requests++;
  });
  await page.goto('/national-budget.html?q=road#projects');
  await expect.poll(() => requests).toBe(5);
  await page.locator('[data-section-item="offices"]').click();
  await expect(page).toHaveURL(/\?q=road#offices$/);
  await page.locator('[data-section-item="projects"]').click();
  await expect(page).toHaveURL(/\?q=road#projects$/);
  await page.goBack();
  await expect(page).toHaveURL(/\?q=road#offices$/);
  expect(requests).toBe(5);
});

for (const width of [320, 375, 768, 1440]) {
  test(`section links remain single-line keyboard targets at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/transparency.html');
    const links = page.locator('[data-section-nav] a');
    const boxes = await links.evaluateAll(nodes => nodes.map(node => {
      const box = node.getBoundingClientRect();
      return { top: box.top, height: box.height };
    }));
    expect(new Set(boxes.map(box => Math.round(box.top))).size).toBe(1);
    expect(boxes.every(box => box.height >= 44)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await links.first().focus();
    for (let index = 1; index < labels.length; index++) {
      await page.keyboard.press('Tab');
      await expect(links.nth(index)).toBeFocused();
    }
    await expect(links.last()).toBeInViewport();
  });
}

test('sticky offset follows actual global header height through menu and resize', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto('/transparency.html');
  const checkOffsets = async () => {
    await expect.poll(() => page.evaluate(() => {
      const header = document.querySelector('.site-header').getBoundingClientRect().height;
      const nav = document.querySelector('[data-section-nav]');
      return Math.abs(parseFloat(getComputedStyle(nav).top) - header);
    })).toBeLessThan(1);
  };
  await checkOffsets();
  await page.getByRole('button', { name: 'Toggle navigation menu' }).click();
  await checkOffsets();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Toggle navigation menu' })).toBeFocused();
  await checkOffsets();
  await page.setViewportSize({ width: 1440, height: 900 });
  await checkOffsets();
  await page.evaluate(() => { document.querySelector('.site-header').style.paddingBottom = '31px'; });
  await checkOffsets();
});

test('measured target margin counts sticky offsets once', async ({ page }) => {
  await page.goto('/methodology.html#national-budget-methodology');
  await expect.poll(() => page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    const target = getComputedStyle(document.querySelector('#national-budget-methodology'));
    return Math.abs(parseFloat(target.scrollMarginTop) - parseFloat(root.getPropertyValue('--site-header-height')) - parseFloat(root.getPropertyValue('--section-nav-height')) - 16);
  })).toBeLessThan(1);
  expect(await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop) || 0)).toBe(0);
});

test('local profile navigation can reuse the global measurement helper', async ({ page }) => {
  await page.goto('/index.html');
  await page.evaluate(async () => {
    const local = document.createElement('nav');
    local.dataset.localSectionNav = '';
    local.textContent = 'Local sections';
    local.style.height = '64px';
    document.querySelector('.site-header').after(local);
    const helper = document.createElement('script');
    helper.src = 'assets/section-nav.js';
    document.body.append(helper);
    await new Promise(resolve => { helper.onload = resolve; });
  });
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--section-nav-height').trim())).toBe('64px');
  await page.locator('[data-local-section-nav]').evaluate(node => { node.style.height = '80px'; });
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--section-nav-height').trim())).toBe('80px');
});

test('no-JavaScript navigation keeps real links and a current page', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:8765/historical-budget.html');
  await expect(page.locator('[data-section-nav] a')).toHaveCount(8);
  await expect(page.locator('[data-section-nav] [aria-current="page"]')).toHaveText('Historical Budgets');
  await expect(page.locator('#hb-coverage-summary')).toBeAttached();
  expect(await page.locator('[data-section-nav]').evaluate(node => getComputedStyle(node).position)).toBe('static');
  expect(await page.locator('#hb-coverage').evaluate(node => node.closest('details').open)).toBe(false);
  await context.close();
});
