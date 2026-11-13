#!/usr/bin/env python3
"""Compare current Chrome/file rendering with Electron/course rendering.

Uses fresh mounts at each viewport and records actual platform fonts, rather
than interpreting an old screenshot or matching CSS font-family strings alone.
"""
import argparse
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request

from PIL import Image, ImageChops

from cdp import CDP, Desktop, ROOT


def metrics(page):
    page.call('DOM.enable')
    page.call('CSS.enable')
    doc = page.call('DOM.getDocument')
    result = {}
    for label, selector in (('heading', 'article h2'), ('paragraph', 'article .theory-text')):
        node = page.call('DOM.querySelector', {'nodeId': doc['root']['nodeId'], 'selector': selector})
        result[label] = {
            'platformFonts': page.call('CSS.getPlatformFontsForNode', {'nodeId': node['nodeId']})['fonts'],
            'computed': page.js('(()=>{let e=document.querySelector(' + json.dumps(selector) + '),s=getComputedStyle(e),r=e.getBoundingClientRect();return {fontFamily:s.fontFamily,fontSize:s.fontSize,fontWeight:s.fontWeight,lineHeight:s.lineHeight,letterSpacing:s.letterSpacing,width:r.width,height:r.height,x:r.x,y:r.y}})()')
        }
    result['viewport'] = page.js('({width:innerWidth,dpr:devicePixelRatio,scale:visualViewport.scale,rootFont:getComputedStyle(document.documentElement).fontSize,bodyFont:getComputedStyle(document.body).fontSize,tocOpen:document.querySelector(".sidebar details")?.open})')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=ROOT / 'release/site')
    parser.add_argument('--output', type=Path, default=ROOT / 'release/qa')
    parser.add_argument('--headful-chrome', action='store_true', help='Compare native desktop font resolution, not headless defaults')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    tag = 'headed-' if args.headful_chrome else ''
    report = {'courseVersion': json.loads((args.site / 'desktop-build.json').read_text())['version'],
              'comparison': 'current source with same local assets: Chrome157 ' + ('headful' if args.headful_chrome else 'headless') + ' file versus Electron45.2.3 headful course scheme',
              'sandboxDisabled': False, 'viewports': []}
    app = None
    chrome = None
    client = None
    with tempfile.TemporaryDirectory(prefix='desktop-current-visual-') as folder:
        temporary = Path(folder)
        try:
            app = Desktop(temporary / 'electron-profile', temporary / 'electron.log', site=args.site)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            chrome = subprocess.Popen([shutil.which('google-chrome'), *([] if args.headful_chrome else ['--headless']), '--disable-gpu', '--no-first-run',
                '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=' + str(port),
                '--remote-allow-origins=http://127.0.0.1:' + str(port),
                '--user-data-dir=' + str(temporary / 'chrome-profile'), 'about:blank'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(100):
                try:
                    targets = json.load(urllib.request.urlopen('http://127.0.0.1:%d/json' % port, timeout=1))
                    target = next(target for target in targets if target['type'] == 'page')
                    client = CDP(target, port)
                    break
                except (OSError, StopIteration):
                    time.sleep(.1)
            assert client
            for width in (1440, 390):
                comparison = {'width': width}
                for label, page, url in (
                    ('chrome', client, (args.site / 'roadmap/cpp_station0_oop_basics.html').resolve().as_uri() + '#section=why-oop'),
                    ('electron', app.page, 'course://app/roadmap/cpp_station0_oop_basics.html#section=why-oop')
                ):
                    page.viewport(width, 1000)
                    page.goto('about:blank')
                    page.goto(url, '!!document.querySelector("article h2")')
                    comparison[label] = metrics(page)
                    path = args.output / ('current-' + tag + label + '-' + str(width) + '.png')
                    page.screenshot(path)
                a = Image.open(args.output / ('current-' + tag + 'chrome-' + str(width) + '.png')).convert('RGB')
                b = Image.open(args.output / ('current-' + tag + 'electron-' + str(width) + '.png')).convert('RGB')
                diff = ImageChops.difference(a, b)
                comparison['changedPixelFractionOver8'] = sum(any(c > 8 for c in pixel) for pixel in diff.getdata()) / (a.width * a.height)
                if args.headful_chrome:
                    assert comparison['chrome'] == comparison['electron'], comparison
                    assert comparison['changedPixelFractionOver8'] < .005, comparison
                report['viewports'].append(comparison)
            report['status'] = ('passed headful comparison with identical platform font/computed metrics'
                                if args.headful_chrome else 'recorded current-platform-font comparison; pixel identity is not assumed')
            (args.output / ('current-' + tag + 'visual-verification.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            if client:
                try:
                    client.call('Browser.close')
                except Exception:
                    pass
                client.ws.close()
            if chrome:
                try:
                    chrome.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    chrome.kill()
                    chrome.wait()
            if app:
                app.close()


if __name__ == '__main__':
    main()
