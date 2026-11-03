const { test: base, expect } = require('@playwright/test');

const tile = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64');
const tileURL = /^https:\/\/(?:[^/]+\.)?tile\.openstreetmap\.org\//;

// Wrap context creation, not just the page fixture: explicit newContext calls
// (including no-JavaScript tests) must never send live tile requests either.
const test = base.extend({
  browser: [async ({ browser }, use) => {
    const original = browser.newContext.bind(browser);
    browser.newContext = async options => {
      const context = await original({ ...options, serviceWorkers: 'block' });
      await context.route(tileURL, route => route.fulfill({ contentType: 'image/png', body: tile }));
      return context;
    };
    try { await use(browser); } finally { browser.newContext = original; }
  }, { scope: 'worker' }],
});

module.exports = { test, expect, tileURL };
