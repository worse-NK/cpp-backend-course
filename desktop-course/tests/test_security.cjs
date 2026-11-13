'use strict';
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const s = require('../app/security.cjs');
let checks = 0;
function equal(a, b) {checks++; assert.deepEqual(a, b);}
function rejects(fn) {checks++; assert.throws(fn);}

equal(s.internalName('course://app/'), 'index.html');
equal(s.internalName('course://app/roadmap/a.html?v=123#section=x'), 'roadmap/a.html');
for (const value of ['https://app/a', 'file:///etc/passwd', 'course://evil/a',
  'course://app:123/a', 'course://user@app/a', 'course://app/../a', 'course://app/%2e%2e/a',
  'course://app/%252e%252e/a', 'course://app/a%2fb', 'course://app/a\\b', 'course://app/a%00b',
  'course://app/a/./b', 'course://app/%zz', 'javascript:alert(1)']) equal(s.internalName(value), null);
for (const value of ['javascript:alert(1)', 'file:///tmp/a', 'data:text/html,x',
  'https://a.test\\x', 'https://user:password@a.test/', 'mailto:test@example.com',
  'https://a.test/\nfoo', 'https://a.test./']) equal(s.externalURL(value), null);
equal(s.externalURL('https://www.electronjs.org/docs/latest/'), 'https://www.electronjs.org/docs/latest/');
equal(s.externalURL('http://127.0.0.1:8080/'), 'http://127.0.0.1:8080/');
equal(s.courseBlob('blob:course://app/abc-def-0123'), true);
equal(s.courseBlob('blob:https://evil.test/abc'), false);
equal(s.courseBlob('blob:course://evil/abc'), false);

const sample = '<script>const x=1;</script><script type="application/json">{"x":1}</script>'
  + '<script src="assets/a.js"></script><script type="module">const y=2;</script>';
equal(s.inlineScriptHashes(sample), ["'sha256-" + crypto.createHash('sha256').update('const x=1;').digest('base64') + "'",
  "'sha256-" + crypto.createHash('sha256').update('const y=2;').digest('base64') + "'"]);
const policy = s.cspFor(Buffer.from(sample), '.html');
equal(policy.includes("'unsafe-eval'"), false);
equal(policy.includes("script-src-attr 'none'"), true);
equal(policy.includes("worker-src 'self' blob:"), true);
equal(policy.includes("frame-ancestors 'self'"), true);

const root = fs.mkdtempSync(path.join(os.tmpdir(), 'course-security-'));
try {
  const html = Buffer.from('<html><script>console.log(1)</script></html>');
  const manifest = {format: 1, version: 'test', files: {'index.html': {bytes: html.length, sha256: s.sha256(html)}}};
  fs.writeFileSync(path.join(root, 'index.html'), html);
  fs.writeFileSync(path.join(root, 'desktop-build.json'), JSON.stringify(manifest));
  const site = s.loadSite(root);
  equal(s.readSiteFile(site, 'course://app/').bytes.equals(html), true);
  equal(s.readSiteFile(site, 'course://app/unknown.html'), null);
  equal(s.readSiteFile(site, 'course://app/desktop-build.json').mime, 'application/json; charset=utf-8');
  fs.writeFileSync(path.join(root, 'index.html'), 'edited');
  rejects(() => s.readSiteFile(site, 'course://app/'));
  rejects(() => s.loadSite(root));
  fs.unlinkSync(path.join(root, 'index.html'));
  fs.symlinkSync('/etc/passwd', path.join(root, 'index.html'));
  rejects(() => s.loadSite(root));
  fs.unlinkSync(path.join(root, 'index.html'));
  fs.writeFileSync(path.join(root, 'index.html'), html);
  manifest.files['../outside'] = {bytes: 0, sha256: '0'.repeat(64)};
  fs.writeFileSync(path.join(root, 'desktop-build.json'), JSON.stringify(manifest));
  rejects(() => s.loadSite(root));
} finally {fs.rmSync(root, {recursive: true, force: true});}
console.log(JSON.stringify({passed: true, checks}));
