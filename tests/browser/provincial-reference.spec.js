const { test, expect } = require('@playwright/test');

test('statistics publishes all research and accessible census chart', async ({ page }) => {
  await page.goto('/statistics.html');
  await expect(page.locator('[data-status]')).toContainText('78 source-backed');
  await expect(page.getByRole('table', { name: 'Population trend: accessible chart data' })).toBeVisible();
  await expect(page.getByRole('cell', { name: '3,188,540', exact: true })).toBeVisible();
  const chart=page.getByRole('table', { name: 'Population trend: accessible chart data' });
  await expect(chart.locator('tbody tr')).toHaveCount(4);
  for (const year of ['2010','2015','2020','2024']) {
    await expect(chart.getByRole('cell', { name: year, exact: true })).toBeVisible();
  }
  const response=await page.request.get('/data/provincial-reference.json');
  expect(response.ok()).toBeTruthy();
  const bundle=await response.json();
  // Search includes original notes and indicator names, not only census records.
  const expectedMatches=[...bundle.statistics,...bundle.lgu_registry_2024]
    .filter(row=>JSON.stringify(row).toLowerCase().includes('total population'));
  await page.locator('input[name=q]').fill('Total population');
  await expect(page.locator('[data-status]')).toContainText(`${expectedMatches.length} source-backed`);
  await expect(page.locator('[data-results] .pr-record')).toHaveCount(expectedMatches.length);
  await page.locator('[data-reference]').getByRole('button', { name: 'Clear', exact: true }).click();
  await expect(page.locator('[data-status]')).toContainText('78 source-backed');
});

test('all 48 LGU comparison values reconcile across two result pages', async ({ page }) => {
  await page.goto('/statistics.html?collection=LGU+population+comparisons+%282024%29');
  await expect(page.locator('[data-status]')).toContainText('48 source-backed');
  const table=page.getByRole('table',{name:'2024 LGU population comparison: accessible chart data'});
  await expect(table.locator('tbody tr')).toHaveCount(25);
  const first=await table.locator('tbody tr td:first-of-type').allTextContents();
  await page.getByRole('button',{name:'Next',exact:true}).click();
  await expect(table.locator('tbody tr')).toHaveCount(23);
  const second=await table.locator('tbody tr td:first-of-type').allTextContents();
  expect([...first,...second].reduce((sum,text)=>sum+Number(text.replaceAll(',','')),0)).toBe(3188540);
  await expect(page.locator('[data-results]')).toContainText('48 LGUs in the full registry; population total 3,188,540 persons');
});

test('Mapandan profile URL selects only its actual dated population and hides provincial trend', async ({ page }) => {
  await page.goto('/statistics.html?lgu=lgu-0105528000');
  await expect(page.locator('[data-status]')).toContainText('1 source-backed');
  await expect(page.locator('[data-trend]')).toBeHidden();
  await expect(page.locator('[data-lgu-scope]')).toContainText('Mapandan: one 2024 population observation, not an LGU time series');
  await expect(page.getByRole('link', { name: "Open Mapandan's local statistics and profile" })).toHaveAttribute('href', 'lgu.html?id=lgu-0105528000#statistics');
  const table=page.getByRole('table',{name:'2024 LGU population comparison: accessible chart data'});
  await expect(table.locator('tbody tr')).toHaveCount(1);
  await expect(table).toContainText('38,228');
  await expect(table).toContainText('Census reference: 2024-07-01');
  await expect(table).toContainText('Source collected: 2026-10-31');
  await page.locator('input[name=q]').fill('Mapandan');
  await expect(page).toHaveURL(/lgu=lgu-0105528000/);
  await page.reload();
  await expect(page.locator('[data-status]')).toContainText('1 source-backed');
  await expect(page.locator('[data-trend]')).toBeHidden();
});

test('unknown LGU URL never falls back to provincial statistics', async ({ page }) => {
  await page.goto('/statistics.html?lgu=lgu-0000000000');
  await expect(page.locator('[data-status]')).toContainText('0 source-backed');
  await expect(page.locator('[data-trend]')).toBeHidden();
  await expect(page.locator('[data-lgu-scope]')).toContainText('No registry LGU matches');
});

test('government retains research qualifications and source inventory', async ({ page }) => {
  await page.goto('/government.html');
  await page.locator('select[name=collection]').selectOption({ label: 'Source inventory' });
  await expect(page.locator('[data-status]')).toContainText('47 source-backed');
  await page.locator('select[name=collection]').selectOption({ label: 'Budget observations' });
  await expect(page.locator('[data-status]')).toContainText('15 source-backed');
  await page.locator('input[name=q]').fill('Sual');
  await expect(page.locator('[data-results]')).toContainText(/PART/i);
});

test('hospitals have directory labels and documented hotline', async ({ page }) => {
  await page.goto('/hospitals.html');
  await page.locator('select[name=collection]').selectOption({ label: 'Hospital heads: Directory-listed' });
  await expect(page.locator('[data-status]')).toContainText('12 source-backed');
  await expect(page.getByRole('link', { name: 'Call 911' })).toHaveAttribute('href', 'tel:911');
  await expect(page.locator('[data-results]')).toContainText('Not established by source');
});

test('history is searchable, source-attributed and mobile safe', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/history.html');
  await expect(page.locator('[data-status]')).toContainText('source-backed observations');
  await page.locator('input[name=q]').fill('1580');
  await expect(page.locator('[data-results]')).toContainText('1580');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test('unavailable data does not invent fallback observations', async ({ page }) => {
  await page.route('**/data/provincial-reference.json', route => route.fulfill({ status: 503, body: '' }));
  await page.goto('/hospitals.html');
  await expect(page.locator('[data-status]')).toContainText('could not be loaded');
  await expect(page.locator('a[href="tel:911"]')).toHaveCount(0);
});

test('query, collection and pagination are URL-backed with select change', async ({ page }) => {
  await page.goto('/government.html#sources');
  await expect(page.locator('select[name=collection]')).toHaveValue('Source inventory');
  await expect(page.locator('.pr-record')).toHaveCount(25);
  await expect(page.locator('[data-status]')).toContainText('47 source-backed');
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.locator('.pr-record')).toHaveCount(22);
  await expect(page).toHaveURL(/page=2/);
  await page.reload();
  await expect(page.locator('[data-status]')).toContainText('Showing 26-47');
  await page.locator('select[name=collection]').selectOption('Budget observations');
  await expect(page.locator('.pr-record')).toHaveCount(15);
  await expect(page).not.toHaveURL(/page=2/);
  await page.locator('input[name=q]').fill('Sual');
  await expect(page).toHaveURL(/q=Sual/);
  await page.reload();
  await expect(page.locator('input[name=q]')).toHaveValue('Sual');
  await expect(page.locator('[data-results]')).toContainText(/PART/i);
});

test('contact links retain source digits and raw contact string', async ({ page }) => {
  await page.goto('/hospitals.html?collection=Hospital+public+contacts&q=Pangasinan+Provincial+Hospital');
  await expect(page.locator('[data-results]')).toContainText('(075)532-2603 / (075)531-3263 / (075)531-4249');
  await expect(page.locator('[data-results] a[href="tel:0755322603"]')).toHaveCount(1);
  await expect(page.locator('[data-results] a[href="tel:0755313263"]')).toHaveCount(1);
  await expect(page.locator('[data-results] a[href="tel:0755314249"]')).toHaveCount(1);
  await expect(page.locator('[data-results] a[href^="tel:+"]')).toHaveCount(0);
  await expect(page.locator('[data-results]')).toContainText('Source collected:');
  await expect(page.locator('[data-results]')).toContainText('Not established by source');
});

for (const [mode,count] of [['budgets',15],['legislation',15],['projects',4]]) {
  test(`embedded ${mode} mode publishes only its dedicated observations`, async ({ page }) => {
    await page.route('**/reference-embed.html', route => route.fulfill({ contentType:'text/html', body:`<!doctype html><html><body><section data-reference="${mode}"><form><label>Search<input name="q" type="search"></label><select name="collection"><option value="">All collections</option></select><button type="submit">Search</button></form><p data-status role="status"></p><div data-results></div></section><script src="assets/provincial-reference.js" defer></script></body></html>` }));
    await page.goto('/reference-embed.html');
    await expect(page.locator('[data-status]')).toContainText(`${count} source-backed`);
    await expect(page.locator('.pr-record')).toHaveCount(count);
    await expect(page.locator('select[name=collection] option')).toHaveCount(2);
    await expect(page.locator('[data-results]')).not.toContainText('Directory-listed offices');
  });
}

test('statistics put values, units and periods first and retain all 30 original records in disclosures', async ({ page }) => {
  await page.goto('/statistics.html?collection=Statistics');
  await expect(page.locator('[data-status]')).toContainText('30 source-backed');
  const first = page.locator('.pr-statistic').first();
  await expect(first.locator('.pr-stat-value')).toHaveText('3,188,540persons');
  await expect(first.locator('.pr-period')).toHaveText('2024 / Pangasinan');
  await expect(first.locator('dl')).toHaveCount(0);
  await expect(first.locator('details')).not.toHaveAttribute('open', '');
  await first.getByText('Source, dates and original record', { exact: true }).click();
  await expect(first.locator('pre')).toContainText('"value": 3188540');
  await expect(first.locator('pre')).toContainText('"reference_period": "2024"');
  await expect(page.locator('.pr-statistic')).toHaveCount(25);
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.locator('.pr-statistic')).toHaveCount(5);
});

test('budget evidence filters retain proposal and partial-operative qualifications without a financial calculator', async ({ page }) => {
  await page.goto('/government.html?collection=Budget+observations');
  await expect(page.getByRole('table', { name: 'Budget evidence: amounts are not actual spending' })).toBeVisible();
  await expect(page.locator('.pr-budget-row')).toHaveCount(15);
  await page.getByLabel('Budget year', { exact: true }).selectOption('2027');
  await expect(page.locator('.pr-budget-row')).toHaveCount(1);
  await expect(page.locator('.pr-budget-row')).toContainText('PROPOSED annual');
  await expect(page.locator('.pr-budget-row')).toContainText('not an approved appropriation');
  await expect(page).toHaveURL(/year=2027/);
  await page.reload();
  await expect(page.getByLabel('Budget year', { exact: true })).toHaveValue('2027');
  await page.locator('[data-reference]').getByRole('button', { name: 'Clear', exact: true }).click();
  await page.locator('select[name=collection]').selectOption('Budget observations');
  await page.getByLabel('Budget type', { exact: true }).selectOption('annual');
  await page.locator('input[name=q]').fill('Sual');
  await expect(page.locator('.pr-budget-row')).toHaveCount(1);
  await expect(page.locator('.pr-budget-row')).toContainText('operative in PART');
  await page.locator('.pr-budget-row summary').click();
  await expect(page.locator('.pr-budget-row pre')).toContainText('"provincial_resolution_number": "305-2026"');
});

test('hospital records prioritize directory-listed identity and keep raw evidence closed', async ({ page }) => {
  await page.goto('/hospitals.html?collection=Hospital+heads%3A+Directory-listed');
  const first = page.locator('article.pr-record').first();
  await expect(first.getByRole('heading', { name: 'Pangasinan Provincial Hospital' })).toBeVisible();
  await expect(first).toContainText('Directory-listed; currentness not established');
  await expect(first).toContainText('Directory-listed head: Dr. Cipriano C. Fernandez');
  await expect(first.locator('pre')).toBeHidden();
  await first.locator('summary').click();
  await expect(first.locator('pre')).toContainText('"as_of_date": null');
});
