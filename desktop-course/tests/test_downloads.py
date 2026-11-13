#!/usr/bin/env python3
"""Exercise actual Electron will-download without a personal Downloads folder."""
import json
from pathlib import Path
import tempfile
import time

from cdp import Desktop, ROOT


def main():
    report = {'nativeSaveDialogManuallyChecked': False, 'downloadDataFlowChecked': False}
    app = None
    output = ROOT / 'release/qa'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='course-electron-download-') as folder:
        temporary = Path(folder)
        downloads = temporary / 'downloads'
        downloads.mkdir()
        try:
            app = Desktop(temporary / 'profile', output / 'electron-downloads.log', ROOT / 'release/site')
            page = app.page
            page.call('Browser.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': str(downloads), 'eventsEnabled': True})
            page.goto('course://app/progress.html', '!!window.CourseProgress')
            page.js('localStorage.setItem("cpp_station0_progress_v1",JSON.stringify({"sec:why-oop":true}))')
            page.click('#progress-export')
            for _ in range(150):
                files = list(downloads.glob('*.json'))
                if files:
                    break
                time.sleep(.1)
            assert files, 'Actual Electron backup download did not complete'
            snapshot = json.loads(files[0].read_text())
            assert snapshot['entries']['cpp_station0_progress_v1'] == '{"sec:why-oop":true}'
            report['jsonBackupDownload'] = True
            page.goto('course://app/roadmap/object_lifetime_demo.html', '!!document.querySelector("#openSource")')
            page.click('#openSource')
            page.click('#downloadSource')
            for _ in range(150):
                examples = list(downloads.glob('*.cpp'))
                if examples:
                    break
                time.sleep(.1)
            assert examples, 'Actual C++ source download did not complete'
            assert '#include' in examples[0].read_text() and 'int main' in examples[0].read_text()
            report['cppExampleDownload'] = True
            report['downloadDataFlowChecked'] = True
            report['courseVersion'] = json.loads((ROOT / 'release/site/desktop-build.json').read_text())['version']
            report['passed'] = True
            (output / 'download-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps(report, ensure_ascii=False))
        finally:
            if app:
                app.close()


if __name__ == '__main__':
    main()
