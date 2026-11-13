'use strict';

// Pure helpers are independently testable without starting Electron.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const ORIGIN = 'course://app';
const MIME = Object.freeze({
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.ttf': 'font/ttf',
  '.woff2': 'font/woff2', '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/plain; charset=utf-8', '.cpp': 'text/plain; charset=utf-8',
  '.hpp': 'text/plain; charset=utf-8', '.sql': 'text/plain; charset=utf-8',
  '.py': 'text/plain; charset=utf-8', '.sh': 'text/plain; charset=utf-8',
  '.yaml': 'text/plain; charset=utf-8', '.yml': 'text/plain; charset=utf-8',
  '.pcap': 'application/vnd.tcpdump.pcap', '.pcapng': 'application/octet-stream',
  '.zip': 'application/zip', '.wasm': 'application/wasm',
});

function safeName(name) {
  return typeof name === 'string' && name.length > 0 && name.length < 2048
    && !/[\\%\x00-\x1f\x7f]/.test(name) && !path.posix.isAbsolute(name)
    && name.split('/').every(part => part && part !== '.' && part !== '..');
}

function internalName(value) {
  if (typeof value !== 'string' || value.length > 16384 || /[\\\x00-\x20\x7f]/.test(value)) return null;
  // Check before URL canonicalisation can erase an encoded '..' segment.
  const rawPath = value.match(/^course:\/\/[^/?#]*(\/[^?#]*)?/i);
  if (!rawPath) return null;
  try {
    if (/%(?:2f|5c)/i.test(rawPath[1] || '')) return null;
    const raw = decodeURIComponent(rawPath[1] || '/');
    if (raw !== '/' && !safeName(raw.slice(1))) return null;
    const url = new URL(value);
    if (url.protocol !== 'course:' || url.hostname.toLowerCase() !== 'app'
      || url.port || url.username || url.password) return null;
    const name = decodeURIComponent(url.pathname).replace(/^\//, '') || 'index.html';
    return safeName(name) ? name : null;
  } catch (_) { return null; }
}

function externalURL(value) {
  if (typeof value !== 'string' || value.length > 8192 || /[\x00-\x20\x7f\\]/.test(value)) return null;
  try {
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol) || !url.hostname
      || url.username || url.password || url.hostname.endsWith('.')) return null;
    return url.href;
  } catch (_) { return null; }
}

function courseBlob(value) {
  // Blob URLs made by this renderer are used by SQL Workers and JSON backups.
  return typeof value === 'string' && /^blob:course:\/\/app\/[A-Za-z0-9-]+$/.test(value);
}

function inlineScriptHashes(html) {
  const hashes = new Set();
  const pattern = /<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi;
  let match;
  while ((match = pattern.exec(html))) {
    const attrs = match[1];
    if (/\bsrc\s*=/i.test(attrs)) continue;
    const type = attrs.match(/\btype\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/i);
    const kind = type ? (type[1] || type[2] || type[3]).toLowerCase() : '';
    if (kind && !['text/javascript', 'application/javascript', 'module'].includes(kind)) continue;
    if (!match[2].trim()) continue;
    hashes.add("'sha256-" + crypto.createHash('sha256').update(match[2]).digest('base64') + "'");
  }
  return [...hashes];
}

function cspFor(data, extension) {
  const hashes = extension === '.html' ? inlineScriptHashes(data.toString('utf8')) : [];
  return [
    "default-src 'none'", "base-uri 'none'", "object-src 'none'",
    "script-src 'self' " + hashes.join(' '), "script-src-attr 'none'",
    // Existing course/React styles use inline style attributes. This does not
    // permit executable JavaScript or remote CSS.
    "style-src 'self' 'unsafe-inline'", "img-src 'self' data: blob:",
    "font-src 'self'", "connect-src 'self'", "worker-src 'self' blob:",
    "frame-src 'self'", "frame-ancestors 'self'", "form-action 'none'",
  ].join('; ');
}

function sha256(data) { return crypto.createHash('sha256').update(data).digest('hex'); }

function noSymlinkPath(root, name) {
  if (!safeName(name)) throw new Error('Unsafe packaged path');
  let current = root;
  for (const component of name.split('/')) {
    current = path.join(current, component);
    const stat = fs.lstatSync(current);
    if (stat.isSymbolicLink()) throw new Error('Packaged symlink refused');
  }
  if (!fs.statSync(current).isFile()) throw new Error('Not a packaged file');
  return current;
}

function loadSite(directory) {
  const root = path.resolve(directory);
  // The immutable installed site may never resolve to a browser/user directory.
  let parent = root;
  while (true) {
    if (fs.lstatSync(parent).isSymbolicLink()) throw new Error('Site symlink refused');
    const next = path.dirname(parent);
    if (next === parent) break;
    parent = next;
  }
  const manifestBytes = fs.readFileSync(noSymlinkPath(root, 'desktop-build.json'));
  const manifest = JSON.parse(manifestBytes);
  if (!manifest || manifest.format !== 1 || !manifest.files || typeof manifest.files !== 'object'
    || Array.isArray(manifest.files) || !manifest.files['index.html']) throw new Error('Invalid desktop manifest');
  const names = new Set(Object.keys(manifest.files));
  for (const name of names) {
    if (!safeName(name)) throw new Error('Unsafe manifest path');
    const meta = manifest.files[name];
    if (!meta || !Number.isSafeInteger(meta.bytes) || meta.bytes < 0
      || !/^[a-f0-9]{64}$/.test(meta.sha256)) throw new Error('Invalid manifest file metadata');
    const bytes = fs.readFileSync(noSymlinkPath(root, name));
    if (bytes.length !== meta.bytes || sha256(bytes) !== meta.sha256) {
      throw new Error('Packaged file failed integrity check: ' + name);
    }
  }
  names.add('desktop-build.json');
  return {root, manifest, names, manifestBytes};
}

function readSiteFile(site, value) {
  const name = internalName(value);
  if (!name || !site.names.has(name)) return null;
  const bytes = fs.readFileSync(noSymlinkPath(site.root, name));
  // Recheck after start as well: a replaced developer file cannot become code
  // at a stable origin just because the old file once passed startup validation.
  if (name === 'desktop-build.json') {
    if (!bytes.equals(site.manifestBytes)) throw new Error('Manifest changed while running');
  } else {
    const meta = site.manifest.files[name];
    if (bytes.length !== meta.bytes || sha256(bytes) !== meta.sha256) throw new Error('Packaged file changed');
  }
  const extension = path.extname(name).toLowerCase();
  return {name, bytes, mime: MIME[extension] || 'application/octet-stream', csp: cspFor(bytes, extension)};
}

module.exports = {ORIGIN, MIME, safeName, internalName, externalURL, courseBlob,
  inlineScriptHashes, cspFor, sha256, loadSite, readSiteFile};
