#!/usr/bin/env node
// Visible stable-Chrome page capture for the crawler. Reads one JSON job on stdin:
//   {origin, ip, paths: [{key, path}], out_dir, delay_ms}
// The Python caller has already checked the allowlist and robots.txt and resolved
// a public IPv4 address. Writes files into out_dir and prints a JSON report.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const net = require('node:net');
const {launchOptions, assertBrowserVersion} = require('../../scripts/browser-security.cjs');

const MAX_BYTES = 5000000;
const MAX_REQUESTS_PER_PAGE = 120;
const RUN_TIMEOUT_MS = 180000;
const sha256 = bytes => crypto.createHash('sha256').update(bytes).digest('hex');

function validateJob(job) {
  const origin = new URL(job.origin);
  if (origin.protocol !== 'https:' || origin.origin !== job.origin || origin.username || origin.password)
    throw new Error('invalid_origin');
  if (net.isIP(job.ip) !== 4) throw new Error('invalid_ip');
  for (const {key, path: p} of job.paths) {
    if (!/^[a-z0-9-]+$/.test(key) || typeof p !== 'string' || !p.startsWith('/') || p.startsWith('//'))
      throw new Error('invalid_path');
    if (new URL(p, job.origin).origin !== job.origin) throw new Error('invalid_path');
  }
  return origin;
}

function blocked(status, headers, text) {
  if (headers['cf-mitigated'] === 'challenge' || /<title>\s*Just a moment|verify you are human|checking your browser/i.test(text))
    return 'access_challenge';
  return status === 200 ? null : `http_${status}`;
}

function normalizePeer(address) {
  const match = typeof address === 'string' && /^::ffff:(\d+\.\d+\.\d+\.\d+)$/i.exec(address);
  return match ? match[1] : address;
}

async function capture(job) {
  const origin = validateJob(job);
  const report = {started_at: new Date().toISOString(), pages: [], requests: 0};
  let pageRequests = 0;
  let browser, failure;
  const timer = setTimeout(() => { failure = 'time_limit'; browser?.close().catch(() => {}); }, RUN_TIMEOUT_MS);
  const write = (name, body) => {
    if (body.length > MAX_BYTES) throw new Error('byte_limit');
    fs.writeFileSync(path.join(job.out_dir, name), body, {flag: 'wx'});
    return {file: name, sha256: sha256(body), bytes: body.length};
  };
  try {
    browser = await require('@playwright/test').chromium.launch({...launchOptions, headless: false,
      args: [`--host-resolver-rules=MAP ${origin.hostname} ${job.ip}`, '--no-proxy-server']});
    assertBrowserVersion(browser.version());
    report.browser_version = browser.version();
    const context = await browser.newContext({serviceWorkers: 'block', acceptDownloads: false});
    await context.routeWebSocket('**/*', ws => ws.close());
    await context.route('**/*', route => {
      const request = route.request();
      const sameOrigin = (() => { try { return new URL(request.url()).origin === job.origin; } catch { return false; } })();
      report.requests++;
      if (++pageRequests > MAX_REQUESTS_PER_PAGE || !sameOrigin ||
          !['document', 'script', 'stylesheet'].includes(request.resourceType())) return route.abort();
      return route.continue();
    });
    const page = await context.newPage();
    page.setDefaultTimeout(30000);
    const peers = new Map();
    const cdp = await context.newCDPSession(page);
    cdp.on('Network.responseReceived', e => peers.set(e.response.url, e.response.remoteIPAddress));
    await cdp.send('Network.enable');

    for (const [index, {key, path: p}] of job.paths.entries()) {
      if (index) await page.waitForTimeout(job.delay_ms);
      pageRequests = 0;
      const url = job.origin + p;
      const entry = {key, url, retrieved_at: new Date().toISOString()};
      report.pages.push(entry);
      try {
        const response = await page.goto(url, {waitUntil: 'load'});
        const body = await response.body();
        entry.http_status = response.status();
        entry.final_url = page.url();
        entry.content_type = response.headers()['content-type'] || null;
        const peer = normalizePeer((await response.serverAddr())?.ipAddress || peers.get(response.url()));
        entry.peer_ip = peer || null;
        if (peer !== job.ip) throw new Error('peer_mismatch');
        if (new URL(entry.final_url).origin !== job.origin) throw new Error('offsite_redirect');
        entry.raw = write(`${key}.raw.html`, body);
        const reason = blocked(response.status(), response.headers(), body.toString());
        if (reason) throw new Error(reason);
        // Cloudflare email obfuscation is decoded client-side; wait for it if present.
        await page.waitForFunction(() => !document.querySelector('a.__cf_email__'), {}, {timeout: 10000}).catch(() => {});
        entry.rendered = write(`${key}.rendered.html`, Buffer.from(await page.content()));
        const extracted = await page.evaluate(() => ({
          title: document.title,
          text: document.body.innerText,
          headings: [...document.querySelectorAll('h1')].map(h => h.innerText.trim()),
          links: [...document.querySelectorAll('a[href]')].map(a => {
            let href = null;
            try { href = new URL(a.getAttribute('href'), document.baseURI).href; } catch {}
            return {text: (a.innerText ?? a.textContent ?? '').trim(), href};
          }),
          tables: [...document.querySelectorAll('table')].map(t => [...t.querySelectorAll('tr')]
            .map(r => [...r.querySelectorAll('th,td')].map(c => c.innerText.trim()))),
          images: [...document.querySelectorAll('img[src]')].map(i => ({alt: i.alt, src: i.currentSrc || i.src})),
        }));
        entry.extracted = write(`${key}.page.json`, Buffer.from(JSON.stringify({url, final_url: entry.final_url,
          retrieved_at: entry.retrieved_at, ...extracted}, null, 2)));
        entry.status = 'captured';
      } catch (error) {
        entry.status = 'failed';
        entry.error = (failure || error.message).split('\n')[0].slice(0, 200);
        if (failure) break;
      }
    }
  } catch (error) {
    report.error = (failure || error.message).split('\n')[0].slice(0, 200);
  } finally {
    clearTimeout(timer);
    await browser?.close().catch(() => {});
    report.finished_at = new Date().toISOString();
  }
  return report;
}

module.exports = {validateJob, blocked};

if (require.main === module) {
  const job = JSON.parse(fs.readFileSync(0, 'utf8'));
  capture(job).then(report => { process.stdout.write(JSON.stringify(report)); },
    error => { process.stdout.write(JSON.stringify({error: error.message, pages: []})); process.exitCode = 1; });
}
