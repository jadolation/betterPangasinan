const test = require('node:test');
const assert = require('node:assert/strict');
const { launchOptions, assertBrowserVersion } = require('../../scripts/browser-security.cjs');

test('external browsing and tests select stable Chrome with the sandbox enabled', () => {
  assert.equal(launchOptions.channel, 'chrome');
  assert.equal(launchOptions.chromiumSandbox, true);
  assert.deepEqual(require('../../playwright.config.js').use.launchOptions, launchOptions);
});

test('CVE floor rejects old and unrecognized browsers', () => {
  for (const version of ['156.0.8078.4', '156.0.8078.72', '155.9.9999.999', '', 'unknown']) {
    assert.throws(() => assertBrowserVersion(version), /update stable Chrome/);
  }
  for (const version of ['156.0.8078.73', '156.0.8078.80', '156.0.8079.0', '157.0.0.0']) {
    assert.doesNotThrow(() => assertBrowserVersion(version));
  }
});
