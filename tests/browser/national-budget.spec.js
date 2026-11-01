const { test, expect } = require('@playwright/test');
const { readFile } = require('node:fs/promises');
const { createHash } = require('node:crypto');

// Entirely synthetic route responses, never an approved production snapshot.
function synthetic() {
  const row = (id, overrides = {}) => {
    const upstream = { nep_php: 44000000, hgab2_php: null, hgab3_php: 44000000, house_php: 44000000, api_php: null, delta_php: 0, office: 'Synthetic office', pdf_url: { nep: 'https://example.invalid/synthetic.pdf', hgab3: 'https://example.invalid/synthetic-house.pdf' }, flags: ['nep_evidence_review'], bridge_group: 'unchanged', status_label: 'Unchanged candidate', held: false, ...overrides.upstream };
    upstream.house_php = upstream[`${overrides.house_stage || 'hgab3'}_php`];
    return {
    id: `dpwh:${id}`, dataset: 'dpwh', upstream_id: id, title: `Synthetic comparison ${id}`,
    house_stage: 'hgab3', publication_status: 'approved', snapshot_id: 'SYNTHETIC-NOT-PRODUCTION',
    scope: 'geographic', lgu_associations: [{ psgc: '0150000001', name: 'Synthetic Mapandan' }],
    inclusion_reasons: ['province_query_match'], source_review_status: 'reviewed_with_warnings',
    geographic_review_status: 'reviewed', record_sha256: 'a'.repeat(64), ...overrides, upstream,
  }; };
  return {
    manifest: { status: 'approved', snapshot_id: 'SYNTHETIC-NOT-PRODUCTION', retrieved_at: '2026-11-01T00:00:00Z', notice: 'Synthetic browser test only', disclaimers: [{ title: 'Synthetic notice', body: 'Not official; incomplete synthetic coverage', url: 'https://example.invalid/notice' }] },
    projects: [row('one'), row('two', { upstream: { nep_php: 5000000, hgab3_php: 5000000, delta_php: 0, office: 'Synthetic office' }, lgu_associations: [{ psgc: '0150000001', name: 'Synthetic Mapandan' }, { psgc: '0150000002', name: 'Synthetic second LGU' }] }),
      row('three', { dataset: 'fmr', house_stage: 'hgab2', upstream: { nep_php: null, hgab2_php: 0, delta_php: null, office: 'Other office' } }),
      row('shared', { scope: 'shared', upstream: { nep_php: 1000000000, hgab3_php: 1000000000 }, lgu_associations: [] }),
      row('office', { scope: 'office', lgu_associations: [] }),
      row('uncertain', { scope: 'uncertain', title: ' \t=HYPERLINK("bad") <img src=x onerror=alert(1)>', upstream: { nep_php: null, hgab3_php: null, pdf_url: 'javascript:alert(1)' }, lgu_associations: [] })],
    offices: [{ id: 'synthetic-office', name: 'Short office name', matched_label: 'Synthetic office', tier: 'B', district_ids: ['synthetic:district:1', 'synthetic:district:2'], upstream: { co_served_districts: [{ id: 'synthetic:district:2', label: 'Synthetic co-served district' }], fy2027: { nep_php: 49000000, hgab3_php: 50000000 }, years: [{ fy: 2027, stage: 'nep', matched_label: 'Synthetic office', php: 60000000 }] } }],
    coverage: { exhaustive_geographic_coverage: false, queries: [{ complete: true }, { complete: false }], complete: false, limitations: ['Synthetic collection is incomplete.'] },
    sources: { overview: { url: 'https://example.invalid/synthetic-overview' }, meta: { synthetic: true } },
  };
}
async function mock(page, data = synthetic()) {
  data.manifest.files = Object.fromEntries(['projects', 'offices', 'coverage', 'sources'].map(name => [
    `${name}.json`, createHash('sha256').update(JSON.stringify(data[name])).digest('hex'),
  ]));
  await page.route('**/data/national-budget/2027/*.json', route => {
    const name = new URL(route.request().url()).pathname.split('/').pop().replace('.json', '');
    return route.fulfill({ body: JSON.stringify(data[name]), contentType: 'application/json' });
  });
}
async function open(page) {
  await page.goto('/national-budget.html');
  await expect(page.locator('#nb-status')).not.toContainText('Loading');
}

test('Projects and Tools links to the budget module without crowding primary navigation', async ({ page }) => {
  await page.goto('/projects.html');
  await expect(page.locator('.nav-links a[href="national-budget.html"]')).toHaveCount(0);
  await page.getByRole('link', { name: /National budget proposals/ }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('National Budget Projects in Pangasinan');
});

test('synthetic amounts stay stage separated, null-aware and deduplicated across LGUs', async ({ page }) => {
  await mock(page); await open(page);
  await page.getByLabel('Scope lens').selectOption('geographic');
  await expect(page.locator('#nb-results article')).toHaveCount(3);
  await expect(page.locator('#nb-totals')).toContainText('NEP proposal: PHP 49,000,000 (2/2 known)');
  await expect(page.locator('#nb-totals')).toContainText('House proposal: PHP 49,000,000 (2/2 known)');
  await expect(page.locator('#nb-totals')).toContainText('Comparable-row change: PHP 0 (2/2 known)');
  await expect(page.locator('#nb-totals')).toContainText('NEP proposal: Unknown (0/1 known)');
  await expect(page.locator('#nb-totals')).toContainText('House proposal: PHP 0 (1/1 known)');
  await expect(page.locator('#nb-totals')).not.toContainText('98,000,000');
  await page.locator('select[name="lgu"]').selectOption('0150000002');
  await expect(page.locator('#nb-results article')).toHaveCount(1);
  await expect(page.locator('#nb-totals')).toContainText('5,000,000');
  await page.getByRole('button', { name: 'Reset filters' }).click();
  await page.getByLabel('Scope lens').selectOption('shared');
  await expect(page.locator('#nb-results')).toContainText('no Pangasinan share is inferred');
  await expect(page.locator('#nb-count')).toContainText('Not a geographic allocation total');
});

test('default and reset show all published scopes without a geographic total', async ({ page }) => {
  await mock(page); await open(page);
  await expect(page.getByLabel('Scope lens')).toHaveValue('all');
  await expect(page.locator('#nb-results article')).toHaveCount(6);
  await expect(page.locator('#nb-count')).toContainText('Not a geographic allocation total');
  const thirdReading = page.locator('#nb-totals section').filter({ hasText: 'House third reading' });
  await expect(thirdReading).toContainText('NEP proposal: PHP 1,093,000,000 (4/5 known)');
  await expect(thirdReading).toContainText('House proposal: PHP 1,093,000,000 (4/5 known)');
  await expect(thirdReading).toContainText('not attributable provincial funding');
  await page.getByLabel('Scope lens').selectOption('geographic');
  await page.getByRole('button', { name: 'Reset filters' }).click();
  await expect(page.getByLabel('Scope lens')).toHaveValue('all');
  await expect(page.locator('#nb-results article')).toHaveCount(6);
  await expect(page.locator('#nb-pagination')).toBeHidden();
});

test('pagination limits cards but totals and CSV cover all 60 selected records', async ({ page }) => {
  const data = synthetic();
  data.projects = Array.from({ length: 60 }, (_, index) => ({
    ...data.projects[0], id: `dpwh:page-${index}`, upstream_id: `page-${index}`,
    title: `Synthetic paginated ${String(index + 1).padStart(2, '0')}`,
  }));
  await mock(page, data); await open(page);
  await expect(page.locator('#nb-results article')).toHaveCount(25);
  await expect(page.locator('#nb-page-status')).toHaveText('Showing 1-25 of 60');
  await expect(page.getByRole('button', { name: 'Previous page' })).toBeDisabled();
  await expect(page.locator('#nb-totals')).toContainText('NEP proposal: PHP 2,640,000,000 (60/60 known)');
  await expect(page.locator('#nb-totals')).toContainText('House proposal: PHP 2,640,000,000 (60/60 known)');
  const next = page.getByRole('button', { name: 'Next page' });
  await next.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#nb-page-status')).toHaveText('Showing 26-50 of 60');
  await expect(page.locator('#nb-results article').first()).toContainText('Synthetic paginated 26');
  await page.keyboard.press('Enter');
  await expect(page.locator('#nb-results article')).toHaveCount(10);
  await expect(page.locator('#nb-page-status')).toHaveText('Showing 51-60 of 60');
  await expect(next).toBeDisabled();
  const downloading = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download filtered CSV' }).click();
  const csv = await readFile(await (await downloading).path(), 'utf8');
  expect(csv.split('\r\n')).toHaveLength(61);
  expect(csv).toContain('Synthetic paginated 01');
  expect(csv).toContain('Synthetic paginated 60');
  await expect(page.locator('#nb-totals')).toContainText('House proposal: PHP 2,640,000,000 (60/60 known)');
  await page.getByRole('button', { name: 'Previous page' }).focus();
  await page.keyboard.press('Space');
  await expect(page.locator('#nb-page-status')).toHaveText('Showing 26-50 of 60');
  await page.getByLabel('Search records').fill('paginated');
  await expect(page.locator('#nb-page-status')).toHaveText('Showing 1-25 of 60');
  await next.click();
  await page.getByRole('button', { name: 'Reset filters' }).click();
  await expect(page.locator('#nb-page-status')).toHaveText('Showing 1-25 of 60');
  await page.getByLabel('Search records').fill('paginated 60');
  await expect(page.locator('#nb-results article')).toHaveCount(1);
  await expect(page.locator('#nb-pagination')).toBeHidden();
});

test('real 732-record production snapshot opens populated without a geographic filter', async ({ page }) => {
  const response = await page.request.get('/data/national-budget/2027/manifest.json');
  expect(response.ok()).toBeTruthy();
  const publication = await response.json();
  test.skip(publication.status !== 'approved', 'No approved production snapshot present');
  const projects = await (await page.request.get('/data/national-budget/2027/projects.json')).json();
  test.skip(projects.length !== 732, 'Different approved production snapshot');
  expect(publication.status).toBe('approved');
  expect(projects).toHaveLength(732);
  await open(page);
  await expect(page.getByLabel('Scope lens')).toHaveValue('all');
  await expect(page.locator('#nb-status')).toContainText('Approved snapshot loaded');
  await expect(page.locator('#nb-results article')).toHaveCount(25);
  await expect(page.locator('#nb-page-status')).toHaveText('Showing 1-25 of 732');
  await expect(page.locator('#nb-count')).toContainText('732 budget comparison records. Not a geographic allocation total.');
  await expect(page.getByText('Search matches can include similarly named places outside Pangasinan. Publication approval does not verify project location.', { exact: true })).toBeVisible();
});

test('synthetic filters, source evidence, no matches and safe filtered CSV', async ({ page }) => {
  await mock(page); await open(page);
  await page.locator('select[name="dataset"]').selectOption('fmr');
  await expect(page.locator('#nb-results article')).toHaveCount(1);
  await page.locator('select[name="office"]').selectOption('Synthetic office');
  await expect(page.locator('#nb-results')).toContainText('No filter matches');
  await page.getByRole('button', { name: 'Reset filters' }).click();
  await page.getByLabel('House stage').selectOption('hgab3');
  await page.getByLabel('Source review status').selectOption('reviewed_with_warnings');
  await page.locator('select[name="sort"]').selectOption('amount');
  await page.locator('#nb-results summary').first().click();
  await expect(page.locator('#nb-results a').first()).toHaveAttribute('href', 'https://example.invalid/synthetic.pdf');
  await expect(page.locator('#nb-results')).toContainText('nep_evidence_review');
  await page.getByLabel('Scope lens').selectOption('uncertain');
  await page.getByLabel('Search records').fill('HYPERLINK');
  await expect(page.locator('#nb-results article')).toHaveCount(1);
  await expect(page.locator('#nb-results img')).toHaveCount(0);
  await expect(page.locator('#nb-results a')).toHaveCount(0);
  const downloading = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download filtered CSV' }).click();
  const csv = await readFile(await (await downloading).path(), 'utf8');
  expect(csv).toContain('SYNTHETIC-NOT-PRODUCTION');
  expect(csv).toContain('"\' \t=HYPERLINK(""bad"")');
  expect(csv).not.toContain('Synthetic comparison one');
});

test('held and scope-review rows retain versions but never enter comparable change', async ({ page }) => {
  const data = synthetic();
  data.projects[0].upstream.held = true;
  data.projects[0].upstream.hgab3_php += 100;
  data.projects[0].upstream.house_php += 100;
  data.projects[0].upstream.delta_php = 100;
  data.projects[1].upstream.bridge_group = 'scope_review';
  data.projects[1].upstream.status_label = 'Scope needs checking';
  await mock(page, data); await open(page);
  await page.getByLabel('Scope lens').selectOption('geographic');
  const thirdReading = page.locator('#nb-totals section').filter({ hasText: 'House third reading' });
  await expect(thirdReading).toContainText('House proposal: PHP 49,000,100 (2/2 known)');
  await expect(thirdReading).toContainText('Comparable-row change: Unknown (0/2 known)');
  await expect(page.locator('#nb-results article').first()).toContainText('Excluded from comparable-row change totals');
  await page.locator('select[name="comparison"]').selectOption('scope_review / Scope needs checking');
  await expect(page.locator('#nb-results article')).toHaveCount(1);
  await expect(page.locator('#nb-results')).toContainText('Synthetic comparison two');
  await page.locator('select[name="status"]').selectOption('reviewed_with_warnings');
  await page.locator('select[name="geographic"]').selectOption('reviewed');
  await expect(page.locator('#nb-results article')).toHaveCount(1);
});

test('reviewed registry LGUs and supported programs without published matches remain selectable', async ({ page }) => {
  const data = synthetic();
  data.sources.lgu_registry = [{ psgc: '0150000003', name: 'Synthetic unmatched LGU' }];
  await mock(page, data); await open(page);
  await page.getByRole('combobox', { name: 'LGU', exact: true }).selectOption('0150000003');
  await expect(page.locator('#nb-results')).toContainText('No reviewed project matches are available for this LGU yet');
  await page.getByRole('button', { name: 'Reset filters' }).click();
  await page.getByRole('combobox', { name: 'Program', exact: true }).selectOption('nia');
  await expect(page.locator('#nb-results')).toContainText('No filter matches');
  await expect(page.locator('#nb-totals')).toBeEmpty();
});

test('main cards show citizen warnings, comparison, original PDFs and readable notices', async ({ page }) => {
  await mock(page); await open(page);
  await page.getByLabel('Scope lens').selectOption('geographic');
  const card = page.locator('#nb-results article').first();
  await expect(card.getByRole('link', { name: 'Original NEP PDF', exact: true })).toBeVisible();
  await expect(card.getByRole('link', { name: 'Original House PDF (hgab3)', exact: true })).toBeVisible();
  await expect(card.getByText(/NEP evidence needs review:/)).toBeVisible();
  await expect(card.getByText(/Comparison status: unchanged/)).toBeVisible();
  await expect(card.getByText(/Source-supplied change: PHP 0/)).toBeVisible();
  await expect(page.locator('#nb-meta h3')).toHaveText('Synthetic notice');
  await expect(page.locator('#nb-meta')).toContainText('Not official; incomplete synthetic coverage');
  await expect(page.locator('#nb-meta a')).toHaveAttribute('href', 'https://example.invalid/notice');
  await expect(page.locator('#nb-meta')).not.toContainText('"body"');
  await expect(page.locator('#nb-coverage-summary')).toContainText('Incomplete collection coverage');
  await expect(page.locator('#nb-coverage-summary')).toContainText('Synthetic collection is incomplete');
  await expect(page.locator('#nb-coverage-summary')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('National Budget Projects in Pangasinan');
  await page.getByText('Coverage and source metadata', { exact: true }).click();
  await expect(page.getByRole('link', { name: 'Download sources JSON' })).toHaveAttribute('href', 'data/national-budget/2027/sources.json');
  await expect(page.getByRole('link', { name: 'Download coverage JSON' })).toHaveAttribute('href', 'data/national-budget/2027/coverage.json');
});

test('office lens uses published labels and named-project FY2027 context without headline subtraction', async ({ page }) => {
  await mock(page); await open(page);
  await expect(page.locator('#nb-offices')).toBeHidden();
  await page.getByLabel('Scope lens').selectOption('office');
  await expect(page.locator('#nb-offices')).toBeVisible();
  await expect(page.locator('#nb-offices h3')).toHaveText('Synthetic office');
  await expect(page.locator('#nb-offices')).toContainText('Tier B');
  await expect(page.locator('#nb-offices')).toContainText('synthetic:district:1; synthetic:district:2');
  await expect(page.locator('#nb-offices')).toContainText('Synthetic co-served district');
  await expect(page.locator('#nb-offices')).toContainText('Whole-office NEP (context only): PHP 60,000,000');
  await expect(page.locator('#nb-offices')).toContainText('FY2027 named-project NEP: PHP 49,000,000; House third reading (hgab3): PHP 50,000,000');
  await expect(page.locator('#nb-offices')).toContainText('Do not subtract district headlines');
  await expect(page.locator('#nb-totals')).not.toContainText('60,000,000');
});

test('a geographically reviewed record also appears once in its collected office lens', async ({ page }) => {
  const data = synthetic();
  data.projects[0].inclusion_reasons.push({ category: 'office', params: { office: 'Synthetic office' } });
  await mock(page, data); await open(page);
  await page.getByLabel('Scope lens').selectOption('office');
  await expect(page.locator('#nb-results article')).toHaveCount(2);
  await expect(page.locator('#nb-results')).toContainText('Synthetic comparison one');
  await expect(page.locator('#nb-totals')).toContainText('NEP proposal: PHP 88,000,000 (2/2 known)');
  await expect(page.locator('#nb-offices')).toContainText('not recomputed from the filtered project cards');
});

test('unavailable manifest never loads comparison records', async ({ page }) => {
  let requested = false;
  await page.route('**/data/national-budget/2027/*.json', route => {
    if (!route.request().url().endsWith('manifest.json')) requested = true;
    return route.fulfill({ json: { status: 'unavailable', notice: 'Awaiting human approval', disclaimers: [] } });
  });
  await open(page);
  await expect(page.locator('#nb-status')).toContainText('No approved national budget snapshot');
  await expect(page.locator('#nb-content')).toBeHidden();
  expect(requested).toBe(false);
});

for (const width of [375, 1440]) {
  test(`built publication state and screenshot at ${width}px`, async ({ page }, testInfo) => {
    const response = await page.request.get('/data/national-budget/2027/manifest.json');
    expect(response.ok()).toBeTruthy();
    const publication = await response.json();
    await page.setViewportSize({ width, height: 900 });
    await open(page);
    if (publication.status === 'unavailable') {
      await expect(page.locator('#nb-status')).toContainText('No approved national budget snapshot');
      await expect(page.locator('#nb-content')).toBeHidden();
    } else {
      expect(publication.status).toBe('approved');
      await expect(page.locator('#nb-status')).toContainText('Approved snapshot');
      const projects = await (await page.request.get('/data/national-budget/2027/projects.json')).json();
      await expect(page.getByLabel('Scope lens')).toHaveValue('all');
      await expect(page.locator('#nb-results article')).toHaveCount(Math.min(25, projects.length));
      await expect(page.locator('#nb-count')).toContainText('Not a geographic allocation total');
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: testInfo.outputPath(`production-national-budget-${width}.png`), fullPage: false });
  });
}

for (const bad of ['unsafe', 'stage', 'dataset', 'pairing', 'unapproved', 'snapshot', 'metadata-snapshot', 'missing-money', 'negative-money', 'house-mismatch', 'duplicate', 'broken-json']) {
  test(`invalid synthetic ${bad} fails closed`, async ({ page }) => {
    const data = synthetic();
    if (bad === 'unsafe') data.projects[0].upstream.nep_php = Number.MAX_SAFE_INTEGER + 1;
    if (bad === 'stage') data.projects[0].house_stage = 'unknown';
    if (bad === 'dataset') data.projects[0].dataset = 'unknown';
    if (bad === 'pairing') data.projects[0].dataset = 'fmr';
    if (bad === 'unapproved') data.projects[0].publication_status = 'pending';
    if (bad === 'snapshot') data.projects[0].snapshot_id = 'OTHER-SNAPSHOT';
    if (bad === 'metadata-snapshot') data.coverage.snapshot_id = 'OTHER-SNAPSHOT';
    if (bad === 'missing-money') delete data.projects[0].upstream.api_php;
    if (bad === 'negative-money') data.projects[0].upstream.nep_php = -1;
    if (bad === 'house-mismatch') data.projects[0].upstream.house_php = 1;
    if (bad === 'duplicate') data.projects.push(data.projects[0]);
    if (bad === 'broken-json') await page.route('**/data/national-budget/2027/*.json', route => route.fulfill({ body: '{broken', contentType: 'application/json' }));
    else await mock(page, data);
    await open(page);
    await expect(page.locator('#nb-status')).toContainText('unavailable or invalid');
    await expect(page.locator('#nb-content')).toBeHidden();
  });
}

test('overflowing aggregate is not rounded into a false total', async ({ page }) => {
  const data = synthetic();
  data.projects[0].upstream.nep_php = Number.MAX_SAFE_INTEGER;
  await mock(page, data); await open(page);
  await expect(page.locator('#nb-totals')).toContainText('sum outside safe integer range');
});

test('mixed publication assets fail closed on checksum mismatch', async ({ page }) => {
  const data = synthetic();
  await mock(page, data);
  await page.route('**/data/national-budget/2027/projects.json', route => route.fulfill({ json: [] }));
  await open(page);
  await expect(page.locator('#nb-status')).toContainText('unavailable or invalid');
  await expect(page.locator('#nb-content')).toBeHidden();
});

test('empty approved snapshot is distinct from unavailable publication', async ({ page }) => {
  const data = synthetic();
  data.projects = [];
  await mock(page, data); await open(page);
  await expect(page.locator('#nb-status')).toContainText('Approved snapshot contains no published comparison records');
  await expect(page.locator('#nb-content')).toBeVisible();
  await expect(page.locator('#nb-export')).toBeDisabled();
  await expect(page.locator('#nb-totals')).toBeEmpty();
});

test('relative page, asset and data URLs work below a project subpath', async ({ page }) => {
  const requests = [];
  await page.route('**/preview/**', async route => {
    requests.push(new URL(route.request().url()).pathname);
    const response = await route.fetch({ url: route.request().url().replace('/preview/', '/') });
    await route.fulfill({ response });
  });
  await mock(page);
  await page.goto('/preview/national-budget.html');
  await expect(page.locator('#nb-results article')).toHaveCount(6);
  expect(requests).toContain('/preview/assets/national-budget.js');
  expect(requests).toContain('/preview/assets/national-budget.css');
  await expect(page.locator('.brand')).toHaveAttribute('href', 'index.html');
  await page.locator('#nb-results summary').first().click();
  await expect(page.locator('#nb-results a').first()).toHaveAttribute('href', 'https://example.invalid/synthetic.pdf');
});

for (const width of [320, 375, 430, 768, 1440]) {
  test(`synthetic responsive layout ${width}px and keyboard filtering`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await mock(page); await open(page);
    await expect(page.getByLabel('Search records')).toBeVisible();
    await page.getByLabel('Search records').focus();
    await page.keyboard.type('two');
    await expect(page.locator('#nb-results article')).toHaveCount(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    if (width === 375 || width === 1440) {
      await page.getByLabel('Search records').blur();
      await page.evaluate(() => window.scrollTo(0, 0));
      await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
      await page.screenshot({ path: testInfo.outputPath(`synthetic-national-budget-${width}.png`), fullPage: true, animations: 'disabled' });
    }
  });
}

test('static no-JavaScript content is honest', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:8765/national-budget.html');
  await expect(page.getByText('JavaScript is disabled', { exact: true })).toBeVisible();
  await expect(page.locator('#nb-status')).toContainText('No approved national budget snapshot');
  await context.close();
});
