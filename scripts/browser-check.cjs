const { chromium } = require('@playwright/test');
const { launchOptions, assertBrowserVersion } = require('./browser-security.cjs');

module.exports = async function checkBrowser() {
  const browser = await chromium.launch(launchOptions);
  try {
    assertBrowserVersion(browser.version());
    console.log(`Sandboxed stable Chrome ${browser.version()}`);
  } finally {
    await browser.close();
  }
};
