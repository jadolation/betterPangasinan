const { defineConfig } = require('@playwright/test');
const { existsSync } = require('node:fs');

module.exports = defineConfig({
  testDir: './tests/browser',
  outputDir: './tests/browser/artifacts',
  fullyParallel: true,
  workers: 2,
  timeout: 60000,
  reporter: [['list'], ['html', { outputFolder: 'tests/browser/report', open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:8765',
    browserName: 'chromium',
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ||
        (existsSync('/usr/bin/google-chrome') ? '/usr/bin/google-chrome' : undefined),
    },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'python3 build.py && python3 -m http.server 8765 --bind 127.0.0.1 --directory public',
    url: 'http://127.0.0.1:8765',
    reuseExistingServer: false,
    timeout: 60000,
    stderr: 'ignore',
  },
});
