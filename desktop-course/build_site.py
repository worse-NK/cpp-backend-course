#!/usr/bin/env python3
"""Package course content for Electron without changing the browser course.

All runtime dependencies are local and hash-pinned. No PWA, service worker,
network server, compiler, container or external tool is included in this site.
"""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
import sys
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(PROJECT / 'roadmap/tools'))
import build_publication as publication

REACT = {
    'https://unpkg.com/react@18.3.1/umd/react.production.min.js':
        'roadmap/vendor/desktop/react/react.production.min.js',
    'https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js':
        'roadmap/vendor/desktop/react/react-dom.production.min.js',
}
WEB_FILES = ('progress.html', 'desktop-ui.js', 'desktop.css', 'progress-core.js', 'progress-ui.js')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative(base, target):
    return posixpath.relpath(target, posixpath.dirname(base) or '.')


def vendor_files():
    lock = json.loads((HERE / 'vendor/ORIGIN.json').read_text())
    files = {}
    for name, expected in lock['files'].items():
        path = HERE / 'vendor' / name
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise ValueError(f'Vendor symlink refused: {name}')
        content = path.read_bytes()
        if digest(content) != expected:
            raise ValueError(f'Vendor hash mismatch: {name}')
        if name != 'fonts/google-fonts-original.css':
            files['roadmap/vendor/desktop/' + name] = content
    css = (HERE / 'vendor/fonts/google-fonts-original.css').read_text()
    urls = re.findall(r'url\((https://[^)]+)\)', css)
    if len(urls) != 8:
        raise ValueError('Unexpected frozen font stylesheet')
    for i, url in enumerate(urls):
        css = css.replace(url, f'font-{i}.ttf')
    files['roadmap/vendor/desktop/fonts/fonts.css'] = css.encode()
    files['roadmap/vendor/desktop/ORIGIN.json'] = (HERE / 'vendor/ORIGIN.json').read_bytes()
    return files


def localize(name, content, controls=True):
    """Keep the document and rendering order intact; only localize resources."""
    text = content.decode()
    for url, target in REACT.items():
        text = text.replace(url, relative(name, target))
    text = re.sub(r'<link\b[^>]*\brel=["\x27]preconnect["\x27][^>]*>\s*', '', text)
    text = re.sub(r'<link\b[^>]*href=["\x27]https://fonts\.googleapis\.com/[^"\x27]+["\x27][^>]*>',
                  lambda _: '<link rel="stylesheet" href="' +
                  relative(name, 'roadmap/vendor/desktop/fonts/fonts.css') + '">', text)
    if controls:
        injected = ('\n<link rel="icon" type="image/png" href="' + relative(name, 'icons/app-256.png') + '">'
                    '\n<link rel="stylesheet" href="' + relative(name, 'desktop.css') + '">'
                    '\n<script defer src="' + relative(name, 'desktop-ui.js') + '"></script>\n')
        text = text.replace('</head>', injected + '</head>', 1)
    return text.encode()


class RuntimeLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if tag in ('script', 'img', 'iframe', 'source', 'audio', 'video') and attrs.get('src'):
            self.links.append(attrs['src'])
        if tag == 'link' and attrs.get('href'):
            self.links.append(attrs['href'])


def check_local(files):
    count = 0
    for name, content in files.items():
        links = []
        if name.endswith('.html'):
            parser = RuntimeLinks()
            parser.feed(content.decode())
            links += parser.links
        if name.endswith('.css'):
            links += re.findall(r'url\(\s*["\x27]?([^\)"\x27]+)', content.decode())
        for href in links:
            url = urlsplit(href)
            if url.scheme == 'data':
                continue
            if url.scheme or url.netloc:
                raise ValueError(f'External runtime resource in {name}: {href}')
            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(url.path)))
            if target not in files:
                raise ValueError(f'Missing resource in {name}: {href}')
            count += 1
    return count


def collect():
    original, stations = publication.collect()
    original_checks = publication.check_release(original, stations)
    files = {name: localize(name, content) if name.endswith('.html') else content
             for name, content in original.items() if name != 'README.md'}
    files.update(vendor_files())
    for name in WEB_FILES:
        files[name] = (HERE / 'web' / name).read_bytes()
    for name in ('app.svg', 'app-256.png', 'app-512.png'):
        files['icons/' + name] = (HERE / 'icons' / name).read_bytes()
    files['README.txt'] = (HERE / 'README.txt').read_bytes()
    version = digest(json.dumps({name: digest(content) for name, content in sorted(files.items())},
                                sort_keys=True).encode())[:20]
    files['desktop-meta.json'] = json.dumps({'version': version, 'stationCount': len(stations),
        'applicationVersion': json.loads((HERE / 'app/package.json').read_text())['version'],
        'mode': 'electron-local-files', 'requiresBrowser': False, 'usesLocalServer': False},
        ensure_ascii=False, indent=2).encode()
    runtime_checked = check_local(files)
    manifest = {'format': 1, 'version': version, 'stationCount': len(stations), 'fileCount': len(files) + 1,
                'externalRuntimeResources': [], 'runtimeLinksChecked': runtime_checked,
                'originalBrowserLinksChecked': original_checks['local_links_checked'],
                'files': {name: {'bytes': len(content), 'sha256': digest(content)}
                          for name, content in sorted(files.items())}}
    files['desktop-build.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    return files, manifest


def write_site(output):
    output = Path(output).absolute()
    if output == PROJECT or output == PROJECT / 'roadmap' or PROJECT / 'roadmap' in output.parents:
        raise ValueError('Desktop site must not overwrite the browser course')
    if any(part.is_symlink() for part in (output, *output.parents)):
        raise ValueError('Output symlinks refused')
    files, manifest = collect()
    if output.exists():
        entries = list(output.rglob('*'))
        if any(path.is_symlink() for path in entries):
            raise ValueError('Output contains symlinks; nothing overwritten')
        actual = {path.relative_to(output).as_posix(): path for path in entries if path.is_file()}
        if actual:
            previous = json.loads((output / 'desktop-build.json').read_text())
            if set(actual) != set(previous['files']) | {'desktop-build.json'}:
                raise ValueError('Unmanaged files in output; choose a new directory')
            for name, meta in previous['files'].items():
                if digest(actual[name].read_bytes()) != meta['sha256']:
                    raise ValueError(f'Manual changes in output: {name}')
            if set(actual) - set(files):
                raise ValueError('Obsolete generated files; choose a new output directory')
    output.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'release/site')
    result = write_site(parser.parse_args().output)
    print(json.dumps({key: value for key, value in result.items() if key != 'files'}, ensure_ascii=False))
