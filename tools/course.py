#!/usr/bin/env python3
"""One entry point for the website, offline browser copy and Linux package."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import mimetypes
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import build_local

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / 'desktop-course'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def short_report(manifest, **extra):
    return {**{key: value for key, value in manifest.items() if key != 'files'}, **extra}


def port_number(value):
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError('port must be a number from 1 to 65535') from None
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError('port must be a number from 1 to 65535')
    return port


def request_name(target):
    try:
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith('/'):
            return None
        name = unquote(parsed.path, encoding='utf-8', errors='strict').removeprefix('/')
    except (ValueError, UnicodeError):
        return None
    return 'index.html' if name == '' else name if build_local.safe_name(name) else None


def content_type(name):
    for suffix, kind in {'.html': 'text/html', '.js': 'text/javascript',
                         '.css': 'text/css', '.json': 'application/json',
                         '.txt': 'text/plain', '.md': 'text/plain'}.items():
        if name.endswith(suffix):
            return kind + '; charset=utf-8'
    return mimetypes.guess_type(name)[0] or 'application/octet-stream'


def create_server(payload, port=8000):
    """Serve an immutable allowlisted snapshot, never a filesystem directory."""
    payload = dict(payload)
    if 'index.html' not in payload or any(not build_local.safe_name(name) for name in payload):
        raise ValueError('Unsafe or incomplete local server payload')

    class Handler(BaseHTTPRequestHandler):
        def handle_read(self, send_body):
            hosts = {'127.0.0.1:' + str(self.server.server_port),
                     'localhost:' + str(self.server.server_port)}
            if self.server.server_port == 80:
                hosts |= {'127.0.0.1', 'localhost'}
            if self.headers.get('Host', '').lower() not in hosts:
                self.send_error(400, 'Use the displayed localhost address')
                return
            name = request_name(self.path)
            if name not in payload:
                self.send_error(404, 'Not found')
                return
            data = payload[name]
            self.send_response(200)
            self.send_header('Content-Type', content_type(name))
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            if send_body:
                self.wfile.write(data)

        def do_GET(self):
            self.handle_read(True)

        def do_HEAD(self):
            self.handle_read(False)

        def log_message(self, format, *args):
            # Do not record query strings or unrelated content in terminal logs.
            pass

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def build_local_command(args):
    output = Path(args.output) if args.output else build_local.DEFAULT_OUTPUT
    archive = Path(args.archive) if args.archive else output.absolute().parent / build_local.ARCHIVE
    manifest = build_local.write_site(output, archive)
    return short_report(manifest, output=str(output.absolute()), archive=str(archive.absolute()))


def build_deb_command(args):
    if not sys.platform.startswith('linux') or platform.machine().lower() not in ('x86_64', 'amd64'):
        raise ValueError('The .deb target currently supports Linux x86_64/amd64 only')
    if not shutil.which('dpkg-deb'):
        raise ValueError('dpkg-deb is required for this target (on Debian/Ubuntu: sudo apt install dpkg)')
    pack = module('_course_deb_builder', DESKTOP / 'build_deb.py')
    fetch = module('_course_runtime_fetcher', DESKTOP / 'fetch_runtime.py')
    output = pack.checked_path(Path(args.output) if args.output else DESKTOP / 'release')
    version = pack.application_version()
    target = output / (pack.PACKAGE + '_' + version + '_amd64.deb')
    metadata = target.with_suffix('.deb.json')
    if target.exists() or target.is_symlink() or metadata.exists() or metadata.is_symlink():
        raise ValueError('Package already exists; keep it and choose a new --output directory')
    runtime = Path(args.runtime) if args.runtime else DESKTOP / '.toolchain' / ('electron-' + fetch.VERSION + '-linux-x64')
    if not runtime.exists() and args.no_download:
        raise ValueError('Reviewed Electron runtime is missing; omit --no-download to fetch and verify it')
    print('Checking the pinned Electron runtime; the first build downloads it over HTTPS.', flush=True)
    fetch.fetch(runtime, DESKTOP / '.toolchain')
    site = Path(args.site) if args.site else DESKTOP / 'release/site'
    build_local.desktop_adapter().write_site(site)
    return pack.build(site, runtime, output, version)


def run_checks():
    commands = [
        ([sys.executable, '-m', 'unittest', 'discover', '-s', 'tools', '-p', 'test_*.py'], ROOT),
        ([sys.executable, '-m', 'unittest', 'test_publication', 'test_repository_sync', 'test_web_security'], ROOT / 'roadmap/tools'),
        ([sys.executable, '-m', 'unittest', 'discover', '-s', 'desktop-course/tests', '-p', 'test_build.py'], ROOT),
        ([sys.executable, '-m', 'unittest', 'discover', '-s', 'desktop-course/tests', '-p', 'test_package.py'], ROOT),
    ]
    print('Focused checks only: no GUI, containers or system installation.\n'
          'The optional existing-Electron check may be skipped until its first download.', flush=True)
    for command, directory in commands:
        subprocess.run(command, cwd=directory, check=True)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest='command', required=True)
    web = commands.add_parser('web', help='build the website and web ZIP in publish/')
    web.add_argument('--output', type=Path, help='site directory (default: publish/github-pages)')
    for name, help_text in (('local', 'build an offline browser copy and ZIP'),
                            ('serve', 'build and serve the offline copy on 127.0.0.1')):
        item = commands.add_parser(name, help=help_text)
        item.add_argument('--output', type=Path, help='site directory (default: build/local)')
        item.add_argument('--archive', type=Path, help='local ZIP (default: next to the site directory)')
        if name == 'serve':
            item.add_argument('--port', type=port_number, default=8000)
    desktop = commands.add_parser('desktop', help='build the offline Electron content; no runtime needed')
    desktop.add_argument('--output', type=Path, help='default: desktop-course/release/site')
    deb = commands.add_parser('deb', help='build a Linux amd64 .deb; never install it')
    deb.add_argument('--output', type=Path, help='package directory (default: desktop-course/release)')
    deb.add_argument('--site', type=Path, help='Electron content directory (default: desktop-course/release/site)')
    deb.add_argument('--runtime', type=Path, help='reviewed Electron runtime directory')
    deb.add_argument('--no-download', action='store_true', help='fail instead of downloading a missing runtime')
    commands.add_parser('check', help='run focused build, publication and package checks')
    return result


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    try:
        if args.command == 'web':
            publication = build_local.desktop_adapter().publication
            output = args.output or publication.DEFAULT_OUTPUT
            print(json.dumps(short_report(publication.write_release(output)), ensure_ascii=False, indent=2))
        elif args.command in ('local', 'serve'):
            report = build_local_command(args)
            if args.command == 'local':
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                payload, _ = build_local.read_payload(report['output'])
                with create_server(payload, args.port) as server:
                    print('Open http://127.0.0.1:' + str(server.server_port) + '/\n'
                          'Ctrl+C stops the local server. Keep the same address/port for the same browser progress.', flush=True)
                    try:
                        server.serve_forever()
                    except KeyboardInterrupt:
                        print('\nLocal server stopped.', flush=True)
        elif args.command == 'desktop':
            output = args.output or DESKTOP / 'release/site'
            report = build_local.desktop_adapter().write_site(output)
            print(json.dumps(short_report(report, output=str(Path(output).absolute())), ensure_ascii=False, indent=2))
        elif args.command == 'deb':
            print(json.dumps(build_deb_command(args), ensure_ascii=False, indent=2))
        elif args.command == 'check':
            run_checks()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        cli.exit(1, 'Course build failed: ' + str(error) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
