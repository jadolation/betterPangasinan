const { test, expect } = require('./tile-fixture');

const dataset = async request => (await request.get('/data/tourism.json')).json();
const ALLOWED_HOSTS = new Set(['127.0.0.1:8765', 'fonts.googleapis.com', 'fonts.gstatic.com', 'tile.openstreetmap.org']);

test('guide lists every published attraction with photo, LGU and category', async ({ page, request }) => {
  const data = await dataset(request);
  await page.goto('/tourism.html');
  const root = page.locator('[data-tourism]');
  await expect(root.locator('[data-tourism-status]')).toContainText(`${data.attractions.length} places shown`);
  const cards = root.locator('.tr-card');
  await expect(cards).toHaveCount(data.attractions.length);
  for (const card of await cards.all()) {
    await expect(card.locator('img')).toHaveAttribute('alt', /\S/);
    await expect(card.locator('a[href^="lgu.html?id=lgu-"]')).toHaveCount(1);
    await expect(card.locator('.tr-chip')).not.toHaveCount(0);
  }
});

test('category, municipality, search and hidden-spot filters keep URL state', async ({ page }) => {
  await page.goto('/tourism.html');
  const root = page.locator('[data-tourism]');
  await root.locator('#tr-category').selectOption('beach');
  for (const card of await root.locator('.tr-card').all()) await expect(card).toHaveAttribute('data-categories', /beach/);
  await root.locator('#tr-municipality').selectOption('lgu-0105503000');
  await expect(page).toHaveURL(/category=beach/);
  await expect(page).toHaveURL(/municipality=lgu-0105503000/);
  await page.reload();
  await expect(root.locator('#tr-category')).toHaveValue('beach');
  await root.getByRole('button', { name: 'Clear', exact: true }).click();
  await root.getByLabel('Hidden spots only').check();
  for (const card of await root.locator('.tr-card').all()) await expect(card.locator('.tr-badge-hidden')).toBeVisible();
  await root.locator('#tr-search').fill('zzzz-no-match');
  await expect(root.locator('[data-tourism-empty]')).toBeVisible();
});

test('attraction detail shows location, commute legs, food, tips and sources', async ({ page }) => {
  await page.goto('/tourism.html?spot=hundred-islands-national-park');
  const detail = page.locator('[data-tourism-detail]');
  await expect(detail.getByRole('heading', { level: 2, name: /Hundred Islands/ })).toBeVisible();
  for (const name of ['Where it is', 'How to get there', 'What to eat nearby', 'Hidden spots nearby', 'Good to know', 'Sources'])
    await expect(detail.getByRole('heading', { name, exact: true })).toBeVisible();
  const route = detail.locator('.tr-route').first();
  await expect(route.locator('ol > li')).not.toHaveCount(0);
  await expect(route.locator('.tr-leg-mode').first()).toHaveText(/Bus|Jeepney|Tricycle|Van|Boat|Walk/);
  await expect(route).toContainText(/approx\./i);
  await expect(detail.locator('[data-checked-on]')).toContainText(/Last checked \w+ \d{1,2}, \d{4}/);
  await expect(detail.locator('.tr-verify-note')).toContainText('Confirm fares, schedules and entrance fees');
  await expect(detail.locator('a[href*="openstreetmap.org/?mlat="]')).toHaveCount(1);
  await expect(detail.locator('.leaflet-marker-icon')).toHaveCount(1);
});

test('photos are self-hosted and credited with a license', async ({ page }) => {
  await page.goto('/tourism.html?spot=hundred-islands-national-park');
  const figure = page.locator('[data-tourism-detail] figure').first();
  await expect(figure.locator('img')).toHaveAttribute('src', /^assets\/tourism\//);
  await expect(figure.locator('figcaption')).toContainText(/CC BY|CC0|Public domain/);
  await expect(figure.locator('figcaption a[href^="https://"]')).not.toHaveCount(0);
});

test('local food links to its municipality and related attractions', async ({ page }) => {
  await page.goto('/tourism.html#local-food');
  const food = page.locator('[data-tourism-food] .tr-food');
  await expect(food).not.toHaveCount(0);
  await expect(food.first().locator('a[href^="lgu.html?id=lgu-"]')).toHaveCount(1);
});

test('unknown spot shows not-found state and keeps the list usable', async ({ page }) => {
  await page.goto('/tourism.html?spot=does-not-exist');
  await expect(page.locator('[data-tourism-detail]')).toContainText('We could not find that place');
  await expect(page.locator('.tr-card').first()).toBeVisible();
});

test('unavailable dataset degrades gracefully', async ({ page }) => {
  await page.route('**/data/tourism.json', route => route.fulfill({ status: 503, body: '' }));
  await page.goto('/tourism.html');
  await expect(page.locator('[data-tourism-status]')).toContainText('Tourism guide unavailable');
});

test('keyboard: open a card and return focus to it', async ({ page }) => {
  await page.goto('/tourism.html');
  const first = page.locator('.tr-card a.tr-card-link').first();
  await first.focus(); await page.keyboard.press('Enter');
  await expect(page.locator('[data-tourism-detail] h2')).toBeFocused();
  await page.locator('[data-tourism-back]').click();
  await expect(first).toBeFocused();
});

test('no third-party image or script hosts are contacted', async ({ page }) => {
  const hosts = new Set();
  page.on('request', r => hosts.add(new URL(r.url()).host.replace(/^[abc]\./, '')));
  await page.goto('/tourism.html?spot=hundred-islands-national-park');
  await expect(page.locator('.leaflet-marker-icon')).toHaveCount(1);
  for (const host of hosts) expect(ALLOWED_HOSTS.has(host), host).toBeTruthy();
});

test('tourism palette text meets WCAG AA contrast', async ({ page }) => {
  await page.goto('/tourism.html');
  await expect(page.locator('.tr-card').first()).toBeVisible();
  const failures = await page.evaluate(() => {
    const lum = c => { const [r, g, b] = c.match(/\d+/g).slice(0, 3).map(v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }); return .2126 * r + .7152 * g + .0722 * b; };
    const bg = el => { for (; el; el = el.parentElement) { const c = getComputedStyle(el).backgroundColor; if (!/rgba\(.*, 0\)|transparent/.test(c)) return c; } return 'rgb(255,255,255)'; };
    return [...document.querySelectorAll('.tr-chip, .tr-badge-hidden, .tr-card h3, .tr-hero .lede')].filter(el => {
      const [a, b] = [lum(getComputedStyle(el).color), lum(bg(el))].sort((x, y) => y - x);
      return (a + .05) / (b + .05) < 4.5;
    }).map(el => el.className);
  });
  expect(failures).toEqual([]);
});

test('Tourism is reachable from Explore Pangasinan, footer and LGU profile', async ({ page }) => {
  await page.goto('/lgus.html');
  await expect(page.locator('nav.explore-links a[href="tourism.html"]')).toBeVisible();
  await expect(page.locator('.site-footer a[href="tourism.html"]')).toHaveCount(1);
  await page.goto('/lgu.html?id=lgu-0105503000');
  await expect(page.locator('a[href="tourism.html?municipality=lgu-0105503000"]')).toBeVisible();
});

test('no-JS visitors get the dataset link', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto('/tourism.html');
  await expect(page.getByRole('link', { name: 'read the full tourism dataset with its sources' })).toHaveAttribute('href', 'data/tourism.json');
  await expect(page.getByRole('heading', { level: 1, name: 'Discover Pangasinan' })).toBeVisible();
  await context.close();
});

for (const width of [375, 1440]) {
  test(`tourism fits ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/tourism.html?spot=hundred-islands-national-park');
    await expect(page.locator('.tr-card').first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  });
}
