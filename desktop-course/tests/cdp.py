"""Small CDP client for real Electron acceptance; no personal profile reuse."""
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
import websocket

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BINARY = ROOT / '.toolchain/electron-45.2.3-linux-x64/electron'


class CDP:
    def __init__(self, target, port):
        self.ws = websocket.create_connection(target['webSocketDebuggerUrl'],
            origin='http://127.0.0.1:' + str(port), timeout=30)
        self.serial, self.events = 0, []
        self.call('Page.enable')
        self.call('Runtime.enable')
        self.call('Network.enable')

    def call(self, method, params=None):
        self.serial += 1
        serial = self.serial
        self.ws.send(json.dumps({'id': serial, 'method': method, 'params': params or {}}))
        while True:
            value = json.loads(self.ws.recv())
            if value.get('id') == serial:
                if 'error' in value:
                    raise AssertionError(value)
                return value.get('result', {})
            self.events.append(value)

    def js(self, expression):
        result = self.call('Runtime.evaluate', {'expression': expression, 'returnByValue': True,
            'awaitPromise': True, 'userGesture': True})
        if 'exceptionDetails' in result:
            raise AssertionError(result['exceptionDetails'])
        return result['result'].get('value')

    def wait(self, expression, seconds=25):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            value = self.js(expression)
            if value:
                return value
            time.sleep(.08)
        raise AssertionError('Timeout: ' + expression + '\n' + str(self.js('({url:location.href,text:document.body?.innerText?.slice(0,450)})')))

    def goto(self, url, ready='document.readyState === "complete"'):
        self.call('Page.navigate', {'url': url})
        location_test = ('location.href === ' + json.dumps(url)) if '#' in url else (
            'location.href.split("#")[0] === ' + json.dumps(url))
        self.wait(location_test + ' && (' + ready + ')')
        self.js('document.fonts.ready.then(()=>true)')
        time.sleep(.12)

    def click(self, selector, index=0):
        assert self.js('(()=>{const e=document.querySelectorAll(' + json.dumps(selector) + ')[' + str(index) +
            '];if(!e||e.disabled)return false;e.click();return true})()'), selector

    def viewport(self, width=1440, height=1000):
        self.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height,
            'deviceScaleFactor': 1, 'mobile': width < 600})

    def screenshot(self, path):
        self.js('scrollTo(0,0)')
        time.sleep(.3)
        result = self.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(result['data']))


class Desktop:
    def __init__(self, profile, log, site=None, binary=None, app_dir=None):
        self.binary = Path(binary or DEFAULT_BINARY)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        args = [str(self.binary)]
        if self.binary.name == 'electron':
            args.append(str(app_dir or ROOT / 'app'))
        args += ['--course-test-mode', '--course-data-dir=' + str(profile),
                 '--remote-debugging-port=' + str(self.port), '--disable-gpu',
                 '--remote-allow-origins=http://127.0.0.1:' + str(self.port)]
        if site:
            args.append('--course-site=' + str(site))
        env = dict(os.environ)
        env.pop('ELECTRON_RUN_AS_NODE', None)
        env.pop('NODE_OPTIONS', None)
        # An extracted development runtime is not root-owned. Reuse the already
        # installed Chromium sandbox helper for QA only, never --no-sandbox.
        helper = Path('/opt/google/chrome/chrome-sandbox')
        if helper.exists() and helper.stat().st_uid == 0 and helper.stat().st_mode & 0o4000:
            env['CHROME_DEVEL_SANDBOX'] = str(helper)
        self.log_path = Path(log)
        self.log_stream = self.log_path.open('w')
        self.process = subprocess.Popen(args, env=env, stdout=self.log_stream, stderr=self.log_stream)
        self.clients = []
        for _ in range(160):
            try:
                targets = self.targets()
                page = next(t for t in targets if t['type'] == 'page' and t['url'].startswith('course://'))
                self.page = self.connect(page)
                break
            except (OSError, StopIteration):
                if self.process.poll() is not None:
                    self.log_stream.close()
                    raise RuntimeError('Electron exited: ' + self.log_path.read_text()[-6000:])
                time.sleep(.1)
        else:
            self.close()
            raise RuntimeError('Electron did not become ready: ' + self.log_path.read_text()[-6000:])

    def targets(self):
        return json.load(urllib.request.urlopen('http://127.0.0.1:%d/json' % self.port, timeout=1))

    def connect(self, target):
        client = CDP(target, self.port)
        self.clients.append(client)
        return client

    def close(self):
        if self.process.poll() is None:
            try:
                self.page.call('Browser.close')
            except Exception:
                self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        for client in self.clients:
            try:
                client.ws.close()
            except OSError:
                pass
        self.log_stream.close()
