const test = require('node:test');
const assert = require('node:assert/strict');
const { Readable } = require('node:stream');
const { mkdtempSync, rmSync, existsSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const { allowedURL, blockedResponse, assertPeer, normalizePeer, verifiedPeer, saveDownload, saveVerifiedDownload, outputDirectory } = require('../../scripts/psa-download.cjs');

test('only the official public HTTPS origin is allowed', () => {
  assert.equal(allowedURL('https://psa.gov.ph/classification/psgc'), true);
  for (const url of ['http://psa.gov.ph/', 'https://localhost/', 'https://127.0.0.1/', 'https://psa.gov.ph.evil/', 'https://user@psa.gov.ph/', 'https://psa.gov.ph:444/', 'file:///tmp/x']) {
    assert.equal(allowedURL(url), false, url);
  }
});

test('denials and challenges stop before further actions', () => {
  assert.equal(blockedResponse(200, {}, 'ordinary public page'), null);
  assert.equal(blockedResponse(403, {}, ''), 'http_403');
  assert.equal(blockedResponse(200, {'cf-mitigated':'challenge'}, 'User-agent: *'), 'access_challenge');
  assert.equal(blockedResponse(200, {}, '<title>Just a moment...</title>'), 'access_challenge');
  assert.equal(blockedResponse(200, {}, 'Verify you are human'), 'access_challenge');
});

test('output cannot point at source, production, external or existing directories', () => {
  for (const path of ['data/production', 'collector', '/tmp/psa-output', 'data/staging']) {
    assert.throws(() => outputDirectory(path));
  }
});

test('download bytes are retained and hashed', async () => {
  const folder = mkdtempSync(join(tmpdir(), 'psa-download-test-'));
  const bytes = Buffer.from('PK\x03\x04test-only-archive');
  const download = { createReadStream: async () => Readable.from([bytes]), cancel: async () => {} };
  try {
    const result = await saveDownload(download, join(folder, 'artifact.xlsx'), 100);
    assert.equal(result.bytes, bytes.length);
    assert.match(result.sha256, /^[a-f0-9]{64}$/);
  } finally { rmSync(folder, {recursive:true}); }
});

test('oversized or non-workbook downloads are cancelled and discarded', async () => {
  const folder = mkdtempSync(join(tmpdir(), 'psa-download-test-'));
  try {
    for (const [body, limit] of [[Buffer.from('PK\x03\x04too-large'), 5], [Buffer.from('<html>blocked</html>'), 100]]) {
      let cancelled = false;
      const path = join(folder, 'bad.xlsx');
      const download = { createReadStream: async () => Readable.from([body]), cancel: async () => {cancelled=true;} };
      await assert.rejects(saveDownload(download, path, limit));
      assert.equal(cancelled, true);
      assert.equal(existsSync(path), false);
    }
  } finally { rmSync(folder, {recursive:true}); }
});


test('actual peer must match the pinned public destination', () => {
  assertPeer({ipAddress:'104.18.26.80'}, '104.18.26.80');
  for (const peer of [null, {ipAddress:'127.0.0.1'}, {ipAddress:'169.254.169.254'}, {ipAddress:'104.18.27.80'}]) {
    assert.throws(() => assertPeer(peer, '104.18.26.80'));
  }
});


test('IPv4-mapped IPv6 is representation normalization, not a different destination', () => {
  assert.equal(normalizePeer('::ffff:104.18.26.80'), '104.18.26.80');
  assertPeer({ipAddress:'::ffff:104.18.26.80'}, '104.18.26.80');
  assert.throws(() => assertPeer({ipAddress:'::ffff:127.0.0.1'}, '104.18.26.80'));
  assert.throws(() => assertPeer({ipAddress:'104.18.27.80'}, '104.18.26.80'));
  try { assertPeer(null, '104.18.26.80', 'https://psa.gov.ph/robots.txt'); }
  catch (error) { assert.deepEqual(error.network_failure, {url:'https://psa.gov.ph/robots.txt', pinned_ip:'104.18.26.80', observed_ip:null}); }
});


test('CDP fallback proves the same exact connection, not merely a public address', () => {
  const url='https://psa.gov.ph/robots.txt';
  const cdp={url,remoteIPAddress:'104.18.26.80',protocol:'h2'};
  assert.equal(verifiedPeer(null,cdp,'104.18.26.80',url).verification,'chromium_cdp');
  assert.throws(() => verifiedPeer(null,{...cdp,remoteIPAddress:'104.18.27.80'},'104.18.26.80',url));
  assert.throws(() => verifiedPeer({ipAddress:'127.0.0.1'},cdp,'104.18.26.80',url));
  for (const evidence of [null,{...cdp,remoteIPAddress:undefined},{...cdp,fromDiskCache:true},{...cdp,url:'https://psa.gov.ph/other'}]) {
    assert.throws(() => verifiedPeer(null,evidence,'104.18.26.80',url), {code:'peer_verification_unavailable'});
  }
});


test('download success waits for exact peer proof before saving any bytes', async () => {
  const folder=mkdtempSync(join(tmpdir(),'psa-proof-test-'));
  let resolveProof;
  const proof=new Promise(resolve => {resolveProof=resolve;});
  let opened=false;
  const download={createReadStream:async () => {opened=true;return Readable.from([Buffer.from('PK\x03\x04test')]);},cancel:async()=>{}};
  try {
    const pending=saveVerifiedDownload(download,join(folder,'valid.xlsx'),proof,'104.18.26.80','https://psa.gov.ph/file.xlsx');
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(opened,false);
    assert.equal(existsSync(join(folder,'valid.xlsx')),false);
    resolveProof({ipAddress:'104.18.26.80',verification:'chromium_cdp'});
    const result=await pending;
    assert.equal(result.peer_verification,'chromium_cdp');
    assert.equal(result.remote_ip,'104.18.26.80');
    opened=false;
    await assert.rejects(saveVerifiedDownload(download,join(folder,'bad.xlsx'),Promise.resolve(null),'104.18.26.80','https://psa.gov.ph/file.xlsx'));
    assert.equal(opened,false);
    assert.equal(existsSync(join(folder,'bad.xlsx')),false);
  } finally {rmSync(folder,{recursive:true});}
});

test('saved plain-text robots header anomaly is scoped to robots only', () => {
  const text = require('node:fs').readFileSync(require('node:path').join(__dirname, '../fixtures/collector/psa-robots.txt'), 'utf8');
  const headers = {'content-type':'text/plain; charset=utf-8', 'cf-mitigated':'challenge'};
  assert.equal(blockedResponse(200, headers, text, 'https://psa.gov.ph/robots.txt'), null);
  for (const [status, body, url] of [[403,text,'https://psa.gov.ph/robots.txt'], [200,'<html>challenge</html>','https://psa.gov.ph/robots.txt'], [200,text,'https://psa.gov.ph/other']]) {
    assert.ok(blockedResponse(status, headers, body, url));
  }
});
