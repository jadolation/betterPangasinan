const test = require('node:test');
const assert = require('node:assert/strict');
const {validateJob, blocked} = require('../../web-crawler/crawler/browser.cjs');

const job = paths => ({origin: 'https://www.pangasinan.gov.ph', ip: '104.21.2.25', paths});

test('worker accepts only same-origin fixed paths', () => {
  assert.doesNotThrow(() => validateJob(job([{key: 'lgu-agno', path: '/city-municipalities/agno/'}])));
  for (const path of ['//evil.test/', 'https://evil.test/', 'relative', '/\\evil'])
    assert.throws(() => validateJob(job([{key: 'x', path}])), /invalid_path/, path);
  assert.throws(() => validateJob(job([{key: '../x', path: '/'}])), /invalid_path/);
  assert.throws(() => validateJob({...job([]), origin: 'http://www.pangasinan.gov.ph'}), /invalid_origin/);
  assert.throws(() => validateJob({...job([]), ip: '::1'}), /invalid_ip/);
});

test('challenge pages are failures, not captures', () => {
  assert.equal(blocked(200, {'cf-mitigated': 'challenge'}, ''), 'access_challenge');
  assert.equal(blocked(200, {}, '<title>Just a moment...</title>'), 'access_challenge');
  assert.equal(blocked(403, {}, ''), 'http_403');
  assert.equal(blocked(200, {}, '<html>ok</html>'), null);
});
