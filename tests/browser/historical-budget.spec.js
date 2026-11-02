const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

let folder;
test.beforeAll(() => {
  folder = fs.mkdtempSync(path.join(os.tmpdir(), 'historical-budget-'));
  execFileSync('python3', ['-m', 'scripts.historical_budget.publish', '--output', folder], { cwd: path.resolve(__dirname, '../..') });
});
test.afterAll(() => { if (folder) fs.rmSync(folder, { recursive: true, force: true }); });

async function snapshot(page) {
  await page.route('**/data/**', async route => {
    const relative = new URL(route.request().url()).pathname.replace(/^\//, '');
    const file = path.join(folder, relative);
    if (fs.existsSync(file) && file.startsWith(folder + path.sep)) return route.fulfill({ contentType: 'application/json', body: fs.readFileSync(file) });
    return route.continue();
  });
}

test('real reviewed GAA, year and department filters, chart table and CSV', async ({ page }) => {
  await snapshot(page);
  await page.goto('/historical-budget.html');
  await expect(page.locator('#hb-content')).toBeVisible();
  await expect(page.locator('#hb-coverage tr')).toHaveCount(38);
  await expect(page.locator('#hb-coverage')).toBeHidden();
  await expect(page.locator('#hb-coverage-summary')).toContainText('38 department/query attempts');
  await expect(page.locator('#hb-annual tr')).toHaveCount(7);
  await expect(page.getByRole('img', { name: /Annual appropriations/ })).toBeVisible();
  await page.locator('#hb-department').selectOption('05');
  await expect(page.locator('#hb-count')).toContainText('166 matching');
  await page.locator('#hb-year').selectOption('2020');
  await expect(page.locator('#hb-caption')).toContainText('FY2020');
  const downloadPromise = page.waitForEvent('download');
  await page.locator('#hb-csv').click();
  const download = await downloadPromise;
  const csv = fs.readFileSync(await download.path(), 'utf8');
  expect(csv).toContain('gaa_2020_php'); expect(csv).not.toContain('gaa_2027_php');
  await page.locator('#hb-search').fill('no-such-program-xyz');
  await expect(page.locator('#hb-count')).toContainText('0 matching');
  await expect(page.locator('#hb-annual')).toContainText('No matching families');
});

test('publication failure shows unavailable, never synthetic zero', async ({ page }) => {
  await page.route('**/data/historical-budget/*.json', route => route.fulfill({ status: 503, body: '{}' }));
  await page.goto('/historical-budget.html');
  await expect(page.locator('#hb-status')).toContainText('unavailable');
  await expect(page.locator('#hb-content')).toBeHidden();
});

test('context retains distinct scopes and DPWH 404; hearing links are timestamped', async ({ page }) => {
  await snapshot(page); await page.goto('/budget-context.html');
  await expect(page.locator('#bc-status')).toContainText('Reviewed local snapshot');
  await expect(page.locator('#bc-content')).toContainText('HTTP 404');
  await expect(page.locator('#bc-content')).toContainText('FY2027 NEP proposal PHP');
  await expect(page.locator('#bc-content')).toContainText('Current New Appropriations');
  await page.goto('/budget-hearings.html');
  await expect(page.locator('#bc-content article')).toHaveCount(3);
  const first = page.locator('#bc-content article').first();
  await expect(first.locator('details')).toHaveCount(2);
  await expect(first.locator('details a[href*="?t="]').first()).toBeHidden();
  await first.getByText(/Transcript moments and reported outcome/).click();
  await expect(first.locator('details a[href*="?t="]').first()).toBeVisible();
  const hearingData = await (await page.request.get('/data/budget-hearings.json')).json();
  for (const [index, row] of hearingData.response.data.entries()) {
    const article = page.locator('#bc-content article').nth(index);
    await expect(article).toContainText(row.topic.summary);
    await expect(article).toContainText(row.topic.outcome);
    for (const moment of row.matching_moments || []) {
      await expect(article).toContainText(moment.said);
      await expect(article.getByRole('link', { name: `Verify at ${moment.timestamp}`, includeHidden: true })).toHaveAttribute('href', moment.url);
    }
  }
  await first.getByText('Original topic record (JSON)', { exact: true }).click();
  expect(JSON.parse(await first.locator('pre').textContent())).toEqual(hearingData.response.data[0]);
  await expect(page.locator('.hb-note')).toContainText('not');
});

test('mobile filters and tables remain usable without document overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await snapshot(page); await page.goto('/historical-budget.html');
  await expect(page.locator('#hb-content')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.locator('#hb-query').selectOption('Pangasinan');
  await expect(page.locator('#hb-count')).toContainText('3,821');
});

test('unknown, zero, exact large PHP and spreadsheet-safe text stay distinct', async ({ page }) => {
  await snapshot(page);
  const programs = JSON.parse(fs.readFileSync(path.join(folder, 'data/historical-budget/programs.json')));
  const base = programs.data[0];
  programs.data = [null, 0, '9007199254740992'].map((amount, i) => ({
    ...base, key: `test:${i}`, name: i === 2 ? '=HYPERLINK("unsafe")' : `<img src=x onerror=alert(1)> ${i}`,
    years: Object.fromEntries(programs.years.map(y => [y, { amount, count: null }])),
  }));
  await page.route('**/data/historical-budget/programs.json', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(programs) }));
  await page.goto('/historical-budget.html');
  await expect(page.locator('#hb-content')).toBeVisible();
  await expect(page.locator('#hb-rows tr').nth(0)).toContainText('Unknown');
  await expect(page.locator('#hb-rows tr').nth(1).locator('td').nth(2)).toHaveText('0');
  await expect(page.locator('#hb-annual tr').first()).toContainText('9,007,199,254,740,992');
  await expect(page.locator('#hb-rows img')).toHaveCount(0);
  const pending = page.waitForEvent('download'); await page.locator('#hb-csv').click();
  const download = await pending, csv = fs.readFileSync(await download.path(), 'utf8');
  expect(csv).toContain('9007199254740992'); expect(csv).toContain("'=HYPERLINK");
  expect(csv).toContain('"","",""'); expect(csv).toContain('"0","0","0"');
});
