const { test, expect } = require('./tile-fixture');
const dagupan = 'lgu-0105518000';
const mapandan = 'lgu-0105528000';

async function open(page, id, hash = '') {
  await page.goto(`/lgu.html?id=${id}${hash}`);
  await expect(page.locator('#profile-content')).toBeVisible();
  await expect(page.locator('#profile-optional-status')).not.toContainText('Loading');
}

test('Dagupan has its own population and barangays without a provincial trend', async ({ page }) => {
  await open(page, dagupan);
  await expect(page.locator('#profile-name')).toHaveText('City of Dagupan');
  await expect(page.locator('#profile-kpis')).toContainText('174,777');
  await expect(page.locator('#profile-kpis')).toContainText('31');
  await expect(page.locator('#profile-statistics')).toContainText('174,777');
  await expect(page.locator('#profile-statistics')).not.toContainText('3,188,540');
  await expect(page.locator('#profile-barangay-list li')).toHaveCount(8);
  await page.getByRole('button', { name: 'Show more barangays' }).click();
  await page.getByRole('button', { name: 'Show more barangays' }).click();
  await expect(page.locator('#profile-barangay-list li')).toHaveCount(31);
  await expect(page.locator('#profile-finances')).toContainText('No local finance records are available');
});

test('Mapandan shows local population and discovery without invented allocations', async ({ page }) => {
  await open(page, mapandan);
  await expect(page.locator('#profile-name')).toHaveText('Mapandan');
  await expect(page.locator('#profile-statistics')).toContainText('38,228');
  await expect(page.locator('#profile-projects')).toContainText('2 FY2027 title matches');
  await expect(page.locator('#profile-projects')).toContainText('not confirmed local projects or local funding');
  await expect(page.locator('#profile-finances')).not.toContainText('49,000,000');
  await expect(page.locator('#profile-barangay-status')).toContainText('15 in this collected registry');
  const source = await (await page.request.get(`/data/lgu-profiles/${mapandan}.json`)).json();
  await page.getByLabel('Search barangays').fill(source.barangays[0].name);
  await expect(page.locator('#profile-barangay-list')).toContainText(source.barangays[0].name);
});

test('LGU representatives come from the shared six-district dataset', async ({ page }) => {
  await open(page, dagupan, '#government');
  await expect(page.locator('#profile-government')).toContainText('Pangasinan 4th Legislative District');
  await expect(page.locator('#profile-government')).toContainText('Ma. Georgina P. de Venecia');
  await expect(page.locator('#profile-government')).toContainText('Jerry Agerico B. Rosario');
  await expect(page.locator('#profile-government')).toContainText('Marinor B. De Guzman');
  await expect(page.locator('#profile-government a[href^="municipality-map.html?view=districts"]')).toHaveAttribute('href', 'municipality-map.html?view=districts&district=leg%3Apangasinan%3A4th');
  await expect(page.locator('#profile-government')).toContainText('does not show who requested or controlled a project');
  await open(page, mapandan, '#government');
  await expect(page.locator('#profile-government')).toContainText('Pangasinan 3rd Legislative District');
  await expect(page.locator('#profile-government')).toContainText('Maria Rachel J. Arenas');
  await expect(page.locator('#profile-government')).not.toContainText('Ma. Georgina P. de Venecia');
});

test('local finance keeps decimal pesos and partial legal qualifications', async ({ page, request }) => {
  const lgus = await (await request.get('/data/lgus.json')).json();
  await open(page, lgus.find(row => row.name === 'Sual').id, '#finances');
  await expect(page.locator('#profile-finances')).toContainText('PHP 505,000,000');
  await expect(page.locator('#profile-finances')).toContainText('operative in PART');
  await expect(page.locator('#profile-finances')).not.toContainText('8,379,222,529');
  await open(page, lgus.find(row => row.name === 'Bayambang').id, '#finances');
  await expect(page.locator('#profile-finances')).toContainText('PHP 711,381,782.69');
});

test('optional dataset failure leaves the registry and local statistic functional', async ({ page }) => {
  await page.route('**/data/lgu-profiles/*.json', route => route.fulfill({ status: 503, body: 'Unavailable' }));
  await open(page, dagupan, '#statistics');
  await expect(page.locator('#profile-statistics')).toContainText('174,777');
  await expect(page.locator('#profile-optional-status')).toContainText('Additional collections are unavailable');
  await expect(page.locator('#profile-barangay-status')).toContainText('No count is inferred');
});

test('mismatched optional profile never shows another municipality data', async ({ page, request }) => {
  const other = await (await request.get(`/data/lgu-profiles/${dagupan}.json`)).json();
  await page.route(`**/data/lgu-profiles/${mapandan}.json`, route => route.fulfill({ json: other }));
  await open(page, mapandan);
  await expect(page.locator('#profile-statistics')).toContainText('38,228');
  await expect(page.locator('#profile-statistics')).not.toContainText('174,777');
  await expect(page.locator('#profile-barangay-list li')).toHaveCount(0);
});

test('malformed hash does not make a valid profile unavailable', async ({ page }) => {
  await open(page, dagupan, '#bad[');
  await expect(page.locator('#profile-name')).toHaveText('City of Dagupan');
});

test('profile anchors preserve identity and stay below sticky navigation', async ({ page }) => {
  await open(page, mapandan, '#statistics');
  for (const section of ['finances', 'projects', 'sources', 'statistics']) {
    await page.getByRole('navigation', { name: 'LGU profile sections' }).getByRole('link', { name: section === 'projects' ? 'Projects' : section[0].toUpperCase() + section.slice(1), exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`id=${mapandan}#${section}$`));
    await expect(page.locator(`[data-local-section-nav] a[href="#${section}"]`)).toHaveAttribute('aria-current', 'location');
    const rect = await page.locator(`#${section}`).boundingBox();
    const nav = await page.locator('[data-local-section-nav]').boundingBox();
    expect(rect.y).toBeGreaterThanOrEqual(nav.y + nav.height - 2);
  }
  await page.goBack();
  await expect(page).toHaveURL(/#sources$/);
  await expect(page.locator('#profile-name')).toHaveText('Mapandan');
});

test('unknown identity never falls back to another LGU', async ({ page }) => {
  await page.goto('/lgu.html?id=unknown-lgu');
  await expect(page.locator('#profile-status')).toContainText('not available');
  await expect(page.locator('#profile-content')).toBeHidden();
});

test('legacy finance bookmark points prominently to the same profile section', async ({ page }) => {
  await page.goto(`/finances.html?lgu=${dagupan}`);
  await expect(page.locator('#lgu-profile-shortcut a')).toHaveAttribute('href', `lgu.html?id=${dagupan}#finances`);
});

for (const width of [320, 375, 430, 768, 1024, 1440]) {
  test(`unified profile remains usable at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 950 });
    for (const id of [dagupan, mapandan]) {
      await open(page, id);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
      await page.getByLabel('Search barangays').fill('a');
      if (width === 375 || width === 1440) await page.screenshot({ path: testInfo.outputPath(`${id}-${width}.png`), fullPage: false });
    }
  });
}
