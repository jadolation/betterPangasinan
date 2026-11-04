const { existsSync } = require('node:fs');
const relocatedChrome = '/Volumes/DevSSD/Google Chrome.app/Contents/MacOS/Google Chrome';
const launchOptions = {
  channel: 'chrome',
  chromiumSandbox: true,
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ||
    (process.platform === 'darwin' && existsSync(relocatedChrome) ? relocatedChrome : undefined),
};

function assertBrowserVersion(version) {
  const parts = /^([0-9]+)\.([0-9]+)\.([0-9]+)\.([0-9]+)$/.exec(version);
  // Floor for the four October 2026 CVEs; keep stable Chrome updated beyond it.
  const minimum = [156, 0, 8078, 73];
  if (parts) {
    for (let i = 0; i < minimum.length; i++) {
      const actual = Number(parts[i + 1]);
      if (actual > minimum[i]) return;
      if (actual < minimum[i]) break;
      if (i === minimum.length - 1) return;
    }
  }
  throw new Error(`Chrome ${version} is unsupported; update stable Chrome (minimum 156.0.8078.73)`);
}

module.exports = { launchOptions, assertBrowserVersion };
