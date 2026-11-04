#!/usr/bin/env node
// Ordinary browser download only; challenges remain terminal access failures.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { launchOptions, assertBrowserVersion } = require('./browser-security.cjs');

const ROOT = path.resolve(__dirname, '..');
const LANDING = 'https://psa.gov.ph/classification/psgc';
const WORKBOOK = 'https://psa.gov.ph/system/files/scd/PSGC-3Q-2026-Publication-Datafile.xlsx';
const MAX_BYTES = 25000000;
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');

function allowedURL(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.hostname === 'psa.gov.ph' &&
      !url.username && !url.password && (!url.port || url.port === '443');
  } catch { return false; }
}

function blockedResponse(status, headers, text, url) {
  // A saved robots response carried a challenge header despite containing plain rules.
  const plainRobots = url === 'https://psa.gov.ph/robots.txt' && status === 200 &&
    /^text\/plain(?:;|$)/i.test(headers['content-type'] || '') &&
    !/[<>]/.test(text) && /^User-agent:\s*\S+/im.test(text) &&
    text.split(/\r?\n/).every(line => !line.trim() || /^\s*(#|[A-Za-z-]+\s*:)/.test(line));
  if ((headers['cf-mitigated'] === 'challenge' && !plainRobots) || /<title>\s*Just a moment|verify you are human|checking your browser/i.test(text)) return 'access_challenge';
  return status === 200 ? null : `http_${status}`;
}

function normalizePeer(address) {
  const match = typeof address === 'string' && /^::ffff:(\d+\.\d+\.\d+\.\d+)$/i.exec(address);
  return match && require('node:net').isIP(match[1]) === 4 ? match[1] : address;
}

function assertPeer(peer, pinned, url) {
  if (!peer || normalizePeer(peer.ipAddress) !== pinned) {
    const error = new Error(`Response connection differs from pinned public IP (expected ${pinned}, observed ${peer?.ipAddress || 'unavailable'})`);
    error.network_failure = {url, pinned_ip:pinned, observed_ip:peer?.ipAddress || null};
    throw error;
  }
}

function verifiedPeer(primary, cdp, pinned, url) {
  const fallback = cdp && cdp.url === url && !cdp.fromDiskCache && !cdp.fromServiceWorker && cdp.remoteIPAddress
    ? {ipAddress:cdp.remoteIPAddress, verification:'chromium_cdp'} : null;
  const peer = primary ? {...primary, verification:'playwright_server_addr'} : fallback;
  try { assertPeer(peer, pinned, url); }
  catch (error) {
    if (!peer) error.code='peer_verification_unavailable';
    if (cdp) error.network_failure.cdp = {remote_ip:cdp.remoteIPAddress || null,
      remote_port:cdp.remotePort ?? null, protocol:cdp.protocol || null,
      from_disk_cache:Boolean(cdp.fromDiskCache), from_service_worker:Boolean(cdp.fromServiceWorker)};
    throw error;
  }
  return peer;
}

function outputDirectory(value) {
  const output = path.resolve(ROOT, value);
  const staging = path.join(ROOT, 'data', 'staging');
  if (!output.startsWith(staging + path.sep) || fs.existsSync(output)) throw new Error('Output must be a fresh data/staging subdirectory');
  let parent = path.dirname(output);
  while (!fs.existsSync(parent)) parent = path.dirname(parent);
  if (fs.realpathSync(parent) !== parent) throw new Error('Output symlink parent refused');
  return output;
}

async function saveDownload(download, filename, limit = MAX_BYTES) {
  const chunks = [];
  let length = 0;
  try {
    const stream = await download.createReadStream();
    if (!stream) throw new Error('Download stream unavailable');
    for await (const chunk of stream) {
      length += chunk.length;
      if (length > limit) throw new Error('Workbook exceeds byte limit');
      chunks.push(chunk);
    }
    const body = Buffer.concat(chunks);
    if (!body.subarray(0, 4).equals(Buffer.from([0x50,0x4b,0x03,0x04]))) throw new Error('Downloaded response is not an XLSX archive');
    fs.writeFileSync(filename, body, {flag:'wx'});
    return {artifact:path.basename(filename), bytes:body.length, sha256:hash(body)};
  } catch (error) {
    await download.cancel().catch(() => {});
    throw error;
  }
}

async function saveVerifiedDownload(download, filename, proof, pinned, url) {
  try {
    const peer = await proof;
    assertPeer(peer, pinned, url);
    return {...await saveDownload(download, filename), remote_ip:peer.ipAddress,
      peer_verification:peer.verification};
  } catch (error) {
    await download.cancel().catch(() => {});
    throw error;
  }
}

function python(code, input) {
  const executable = process.env.PYTHON || (fs.existsSync(path.join(ROOT, '.venv/bin/python')) ? path.join(ROOT, '.venv/bin/python') : 'python3');
  return JSON.parse(execFileSync(executable, ['-c', code], {cwd:ROOT, input:JSON.stringify(input), encoding:'utf8', timeout:10000}));
}

async function run(target, authorized, headed = false) {
  if (!authorized) throw new Error('Explicit --authorize-live-practice is required');
  const output = outputDirectory(target);
  fs.mkdirSync(output, {recursive:true});
  const report = {started_at:new Date().toISOString(), source_url:LANDING, workbook_url:WORKBOOK,
    review_status:'pending', redistribution_review:'pending', is_mock:false, auto_publish:false,
    status:'started', headed, artifacts:[], requests:0};
  let browser;
  let timer;
  let violation;
  const deadline = Date.now() + 90000;
  timer = setTimeout(() => {
    violation = 'Browser run exceeded 90 seconds';
    if (browser) browser.close().catch(() => {});
  }, 90000);
  try {
    const addresses = python('from collector.practice import public_addresses; import json; print(json.dumps(public_addresses("psa.gov.ph")))');
    const ip = addresses.find(address => !address.includes(':'));
    if (!ip) throw new Error('No public IPv4 destination available for browser pinning');
    report.pinned_ip = ip;
    const { chromium } = require('@playwright/test');
    browser = await chromium.launch({...launchOptions, headless:!headed, timeout:Math.max(1, Math.min(30000, deadline-Date.now())),
      args:[`--host-resolver-rules=MAP psa.gov.ph ${ip}`, '--no-proxy-server']});
    report.browser_version = browser.version();
    assertBrowserVersion(report.browser_version);
    const context = await browser.newContext({acceptDownloads:true, serviceWorkers:'block'});
    context.setDefaultTimeout(30000);
    await context.routeWebSocket('**/*', socket => socket.close());
    await context.route('**/*', async route => {
      report.requests += 1;
      if (report.requests > 40 || !allowedURL(route.request().url())) return route.abort();
      return route.continue();
    });
    const page = await context.newPage();
    const network = await context.newCDPSession(page);
    const cdpResponses = new Map();
    network.on('Network.responseReceived', event => cdpResponses.set(event.response.url, event.response));
    await network.send('Network.enable');
    async function peerFor(response) {
      const primary = await response.serverAddr();
      if (!primary && !cdpResponses.has(response.url())) await new Promise(resolve => setTimeout(resolve, 100));
      return verifiedPeer(primary, cdpResponses.get(response.url()), ip, response.url());
    }
    const responses = new Map();
    context.on('response', response => {
      responses.set(response.url(), response);
      if (['https://psa.gov.ph/robots.txt', LANDING].includes(response.url())) return;
      (async () => {
        if (!allowedURL(response.url())) throw new Error('Response origin is not approved');
        const peer = await peerFor(response);
        if (Number(response.headers()['content-length'] || 0) > MAX_BYTES) throw new Error('Response exceeds byte limit');
        if (response.url() === WORKBOOK) {
          const denied = blockedResponse(response.status(), response.headers(), '');
          if (denied) {
            report.status = denied;
            const body = await response.body();
            if (body.length > MAX_BYTES) throw new Error('Denied response exceeds byte limit');
            fs.writeFileSync(path.join(output, 'workbook-denied.raw'), body, {flag:'wx'});
            report.artifacts.push({url:WORKBOOK, status:response.status(), remote_ip:peer.ipAddress,
              retrieved_at:new Date().toISOString(), artifact:'workbook-denied.raw', bytes:body.length, sha256:hash(body)});
            violation = denied;
            await context.close();
          }
        }
      })().catch(error => {violation=error.message; if (error.code) report.status=error.code; if (error.network_failure) report.network_failure=error.network_failure; context.close().catch(() => {});});
    });
    async function capture(url, name) {
      const response = await page.goto(url, {waitUntil:'domcontentloaded', timeout:30000});
      if (!response) throw new Error('No main-document response');
      let peer;
      let peerError;
      try { peer = await peerFor(response); } catch (error) { peerError=error; }
      if (Number(response.headers()['content-length'] || 0) > MAX_BYTES) throw new Error('Document exceeds byte limit');
      const bytes = await response.body();
      if (bytes.length > MAX_BYTES) throw new Error('Document exceeds byte limit');
      const headers = response.headers();
      const evidence = {url:response.url(), retrieved_at:new Date().toISOString(), status:response.status(),
        remote_ip:peer?.ipAddress || null, peer_verification:peer?.verification || 'unverified', content_type:headers['content-type'], cf_mitigated:headers['cf-mitigated'],
        artifact:name, bytes:bytes.length, sha256:hash(bytes)};
      fs.writeFileSync(path.join(output, name), bytes, {flag:'wx'});
      report.artifacts.push(evidence);
      if (peerError) throw peerError;
      if (violation) throw new Error(violation);
      const denied = blockedResponse(response.status(), headers, bytes.toString('utf8'), response.url());
      if (denied) {report.status=denied; return null;}
      return {text:bytes.toString('utf8'), headers};
    }
    const robots = await capture('https://psa.gov.ph/robots.txt', 'robots.raw');
    if (!robots) return report;
    if (!(robots.headers['content-type'] || '').includes('text/plain')) {report.status='robots_content_unrecognized'; return report;}
    const agent = await page.evaluate(() => navigator.userAgent);
    const policy = python('import sys,json; from urllib.robotparser import RobotFileParser; v=json.load(sys.stdin); r=RobotFileParser(); r.parse(v["text"].splitlines()); print(json.dumps({"allowed":all(r.can_fetch(v["agent"],u) for u in v["urls"]),"delay":r.crawl_delay(v["agent"]) or 2}))', {text:robots.text, agent, urls:[LANDING,WORKBOOK]});
    if (!policy.allowed) {report.status='robots_denied'; return report;}
    if (policy.delay > 30) {report.status='robots_delay_deferred'; return report;}
    await new Promise(resolve => setTimeout(resolve, Math.max(2, policy.delay)*1000));
    if (!await capture(LANDING, 'landing.raw')) return report;
    const link = page.locator(`a[href="${WORKBOOK}"], a[href="${new URL(WORKBOOK).pathname}"]`).first();
    if (await link.count() !== 1) {report.status='documented_workbook_link_missing'; return report;}
    await new Promise(resolve => setTimeout(resolve, Math.max(2, policy.delay)*1000));
    const waiting = page.waitForEvent('download', {timeout:30000});
    waiting.catch(() => {});
    await link.click({timeout:30000});
    const download = await waiting;
    if (download.url() !== WORKBOOK) {await download.cancel(); throw new Error('Workbook redirected to an unapproved URL');}
    const response = responses.get(WORKBOOK);
    const proof = response ? peerFor(response) : Promise.resolve().then(() =>
      verifiedPeer(null, cdpResponses.get(WORKBOOK), ip, WORKBOOK));
    report.artifacts.push({...await saveVerifiedDownload(download, path.join(output,'publication.xlsx'), proof, ip, WORKBOOK),
      url:WORKBOOK, retrieved_at:new Date().toISOString()});
    if (violation || report.status !== 'started') throw new Error(violation || report.status);
    report.status='downloaded_for_layout_review';
    return report;
  } catch (error) {
    if (report.status === 'started') report.status=error.code || 'blocked_or_failed';
    report.error=violation || error.message;
    if (error.network_failure) report.network_failure=error.network_failure;
    return report;
  } finally {
    clearTimeout(timer);
    if (browser) await browser.close().catch(() => {});
    report.finished_at=new Date().toISOString();
    fs.writeFileSync(path.join(output,'manifest.json'), JSON.stringify(report,null,2)+'\n', {flag:'wx'});
  }
}

module.exports = {allowedURL, blockedResponse, normalizePeer, assertPeer, verifiedPeer, outputDirectory, saveDownload, saveVerifiedDownload, run};
if (require.main === module) {
  const args=process.argv.slice(2);
  const index=args.indexOf('--target');
  if (index < 0 || !args[index+1]) {console.error('--target is required'); process.exitCode=1;}
  else run(args[index+1], args.includes('--authorize-live-practice'), args.includes('--headed')).then(report => {
    console.log(JSON.stringify(report)); process.exitCode=report.status==='downloaded_for_layout_review' ? 0 : 1;
  }).catch(error => {console.error(error.message); process.exitCode=1;});
}
