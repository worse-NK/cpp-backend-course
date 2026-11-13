"""Add static CSP without changing code, rendering order or browser storage.

W3C CSP3 (working draft), sections 3.3 and 8.4: early meta delivery and external
script hashes. W3C SRI 2016, section 3.3.2: file:// resources may be ineligible,
so only the existing HTTPS React resources receive SRI, not local course files.
"""
import base64
import hashlib
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote, urlsplit

VENDOR = Path(__file__).resolve().parents[2] / 'desktop-course/vendor'
REACT = {
    'https://unpkg.com/react@18.3.1/umd/react.production.min.js': 'react/react.production.min.js',
    'https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js': 'react/react-dom.production.min.js',
}
FONTS = ('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&'
         'family=JetBrains+Mono:wght@400;500;700&display=swap')
JAVASCRIPT = {'', 'module', 'text/javascript', 'application/javascript',
              'text/ecmascript', 'application/ecmascript'}


def _hash(data, algorithm='sha256'):
    return algorithm + '-' + base64.b64encode(hashlib.new(algorithm, data).digest()).decode()


def _react_integrities():
    lock_path = VENDOR / 'ORIGIN.json'
    if any(part.is_symlink() for part in (lock_path, *lock_path.parents)):
        raise ValueError('React vendor lock symlink refused')
    lock = json.loads(lock_path.read_text())
    pins = {}
    for url, name in REACT.items():
        path = VENDOR / name
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise ValueError('React vendor symlink refused')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != lock.get('files', {}).get(name):
            raise ValueError('React vendor hash differs from the reviewed lock: ' + name)
        pins[url] = _hash(data, 'sha384')
    return pins


class _Document(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.lines = [0] + [match.end() for match in re.finditer('\n', source)]
        self.tags, self.scripts = [], []
        self.open_script = None
        self.feed(source)
        self.close()
        if self.open_script is not None:
            raise ValueError('Unclosed script in course HTML')

    def _source_offset(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, pairs):
        if len({name for name, _ in pairs}) != len(pairs):
            raise ValueError('Duplicate HTML attributes are refused')
        attrs, raw = dict(pairs), self.get_starttag_text()
        start = self._source_offset()
        self.tags.append((tag, attrs, start, start + len(raw), raw))
        if tag == 'script':
            self.open_script = (attrs, start + len(raw))

    def handle_endtag(self, tag):
        if tag == 'script' and self.open_script is not None:
            attrs, start = self.open_script
            self.scripts.append((attrs, self.source[start:self._source_offset()]))
            self.open_script = None


def _script_tag(attrs, values):
    attrs = {name: value for name, value in attrs.items() if name not in values}
    attrs.update(values)
    return '<script' + ''.join(' ' + name + ('' if value is None else
        '="' + escape(value, quote=True) + '"') for name, value in attrs.items()) + '>'


def _local_target(name, value, files):
    url = urlsplit(value)
    if url.scheme or url.netloc or url.path.startswith('/') or '\\' in value:
        raise ValueError('Unexpected course resource URL: ' + value)
    target = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(url.path)))
    if target == '..' or target.startswith('../'):
        raise ValueError('Course resource escaped the site')
    if files is not None and target not in files:
        raise ValueError('Missing protected course resource: ' + target)


def secure_html(content, *, name='index.html', files=None, mode='web'):
    """Protect a final HTML payload; repeat after localizing or injecting controls."""
    if mode not in ('web', 'local', 'desktop'):
        raise ValueError('Unknown course security mode')
    source = content.decode('utf-8')
    parsed = _Document(source)
    # Keep any independent policy: multiple CSPs are intersected, never weakened.
    owned = [(start - (start > 0 and source[start - 1] == '\n'), end, '')
             for tag, attrs, start, end, _ in parsed.tags
             if tag == 'meta' and attrs.get('data-course-security') == '1'
             and attrs.get('http-equiv', '').lower() == 'content-security-policy']
    for start, end, value in reversed(owned):
        source = source[:start] + value + source[end:]
    parsed = _Document(source)
    heads = [item for item in parsed.tags if item[0] == 'head']
    if len(heads) != 1:
        raise ValueError('Protected course HTML requires one explicit head')
    insertion = heads[0][3]
    hashes, remote, changes = set(), {}, []
    first_resource = len(source)
    for attrs, code in parsed.scripts:
        kind = attrs.get('type', '').split(';', 1)[0].strip().lower()
        if not attrs.get('src') and kind in JAVASCRIPT and code.strip():
            # HTML input normalizes line endings before the browser hashes text.
            hashes.add(_hash(code.replace('\r\n', '\n').replace('\r', '\n').encode()))
    for tag, attrs, start, end, raw in parsed.tags:
        if any(attr.startswith('on') for attr in attrs):
            raise ValueError('Inline event attributes are refused in course HTML')
        if tag in ('base', 'object', 'embed'):
            raise ValueError('Unsupported active element in course HTML: ' + tag)
        if tag in ('script', 'style'):
            first_resource = min(first_resource, start)
        rel = attrs.get('rel', '').lower().split()
        if tag == 'link' and 'preconnect' in rel:
            # connect-src is none; this optional optimization cannot be used.
            changes.append((start, end, ''))
            continue
        value = None
        if tag in ('script', 'iframe', 'img', 'source', 'audio', 'video'):
            value = attrs.get('src')
        elif tag == 'link' and any(kind in rel for kind in ('stylesheet', 'icon', 'preload', 'modulepreload')):
            value = attrs.get('href')
        if value is None:
            continue
        first_resource = min(first_resource, start)
        if tag == 'script' and value in REACT and mode == 'web':
            if not remote:
                remote = _react_integrities()
            changes.append((start, end, _script_tag(attrs, {
                'integrity': remote[value], 'crossorigin': 'anonymous'})))
            hashes.add(remote[value])
        elif tag == 'link' and 'stylesheet' in rel and value == FONTS and mode == 'web':
            pass
        elif tag in ('img', 'source') and urlsplit(value).scheme in ('data', 'blob'):
            pass
        else:
            _local_target(name, value, files)
    if first_resource < insertion:
        raise ValueError('Active course content precedes the document head')
    # Keep the encoding declaration in the first 1024 bytes, before the policy.
    for tag, attrs, start, end, _ in parsed.tags:
        if tag == 'meta' and attrs.get('charset') and insertion <= start < first_resource:
            insertion = end
            break
    policy = '; '.join([
        "default-src 'none'", "base-uri 'none'", "object-src 'none'",
        "script-src 'self'" + ''.join(" '" + value + "'" for value in sorted(hashes)),
        "script-src-attr 'none'", "style-src 'self' 'unsafe-inline'" +
            (' https://fonts.googleapis.com' if mode == 'web' else ''),
        "font-src 'self'" + (' https://fonts.gstatic.com' if mode == 'web' else ''),
        "img-src 'self' data: blob:",
        # The packaged settings page reads its local build metadata, not an API.
        "connect-src 'self'" if mode == 'desktop' and name == 'progress.html' else "connect-src 'none'",
        "worker-src 'self' blob:", "frame-src 'self'", "form-action 'none'",
    ])
    changes.append((insertion, insertion, '\n<meta http-equiv="Content-Security-Policy" '
        'data-course-security="1" content="' + escape(policy, quote=True) + '">'))
    for start, end, value in sorted(changes, reverse=True):
        source = source[:start] + value + source[end:]
    return source.encode('utf-8')


def secure_files(files, mode='web'):
    """Return protected HTML with all other payloads unchanged."""
    return {name: secure_html(content, name=name, files=files, mode=mode)
            if name.endswith('.html') else content for name, content in files.items()}


def validate_files(files, mode='web'):
    """Reject missing/stale generated policy or SRI without approving changed code."""
    expected = secure_files(files, mode=mode)
    for name, content in files.items():
        if expected[name] != content:
            raise ValueError('Missing or stale course CSP/SRI: ' + name)
    return sum(name.endswith('.html') for name in files)
