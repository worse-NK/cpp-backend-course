#!/usr/bin/env python3
"""Read only this app's X11 identity; do not inspect unrelated window content."""
import json
import re
from pathlib import Path
import subprocess
import tempfile
import time

from cdp import Desktop, ROOT


def main():
    output = ROOT / 'release/qa'
    output.mkdir(parents=True, exist_ok=True)
    app = None
    with tempfile.TemporaryDirectory(prefix='course-desktop-identity-') as folder:
        try:
            app = Desktop(Path(folder) / 'profile', output / 'desktop-identity.log', ROOT / 'release/site')
            page = app.page
            page.wait('!!document.querySelector("h1")')
            result = None
            for _ in range(40):
                # Match our known process ID, not a localized/non-ASCII title.
                tree = subprocess.check_output(['xwininfo', '-root', '-tree'], text=True)
                for window in re.findall(r'^\s*(0x[0-9a-f]+)\s', tree, re.M):
                    identity = subprocess.run(['xprop', '-id', window, '_NET_WM_PID'], capture_output=True, text=True, timeout=3)
                    match = re.search(r'=\s*(\d+)', identity.stdout)
                    if match and int(match[1]) == app.process.pid:
                        result = subprocess.run(['xprop', '-id', window, 'WM_CLASS', '_NET_WM_PID', '_NET_WM_ICON'],
                                                capture_output=True, text=True, timeout=3)
                        break
                if result is not None and result.returncode == 0:
                    break
                time.sleep(.1)
            assert result is not None and result.returncode == 0, 'No X11 window belongs to the test app process'
            wm_class = next(line for line in result.stdout.splitlines() if line.startswith('WM_CLASS'))
            assert 'cpp-backend-course-desktop' in wm_class, wm_class
            assert '_NET_WM_ICON(CARDINAL)' in result.stdout, 'window icon is missing'
            report = {'desktopFilename': 'cpp-backend-course-desktop.desktop', 'wmClass': wm_class,
                      'windowIconPropertyPresent': True, 'sandboxDisabled': False, 'passed': True}
            (output / 'desktop-identity-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps(report, ensure_ascii=False))
        finally:
            if app:
                app.close()


if __name__ == '__main__':
    main()
