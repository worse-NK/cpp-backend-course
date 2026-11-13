#!/usr/bin/env python3
"""Run the actual .deb payload by extraction; never install system-wide."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from cdp import Desktop, ROOT


def main():
    package = ROOT / 'release/cpp-backend-course-desktop_1.0.0_amd64.deb'
    metadata = json.loads(package.with_name(package.name + '.json').read_text())
    assert hashlib.sha256(package.read_bytes()).hexdigest() == metadata['sha256']
    report = {'systemInstallPerformed': False, 'sandboxDisabled': False}
    output = ROOT / 'release/qa'
    output.mkdir(parents=True, exist_ok=True)
    app = None
    with tempfile.TemporaryDirectory(prefix='course-real-electron-deb-') as folder:
        temporary = Path(folder)
        stage = temporary / 'root'
        subprocess.run(['dpkg-deb', '--extract', str(package), str(stage)], check=True)
        binary = stage / 'opt/cpp-backend-course-desktop/course-backend'
        site = stage / 'opt/cpp-backend-course-desktop/resources/app/site'
        manifest = json.loads((site / 'desktop-build.json').read_text())
        assert manifest['version'] == metadata['course_version']
        for name, record in manifest['files'].items():
            data = (site / name).read_bytes()
            assert len(data) == record['bytes'] and hashlib.sha256(data).hexdigest() == record['sha256'], name
        info = subprocess.check_output(['dpkg-deb', '--info', str(package)], text=True)
        assert 'Architecture: amd64' in info and 'Conflicts: cpp-backend-course-offline' in info
        assert 'Depends: python' not in info and 'Suggests: firefox' not in info
        archive = subprocess.check_output(['dpkg-deb', '--contents', str(package)], text=True)
        helper = next(line for line in archive.splitlines() if line.endswith('/chrome-sandbox'))
        assert helper.startswith('-rwsr-xr-x root/root'), helper
        assert (stage / 'usr/share/icons/hicolor/512x512/apps/cpp-backend-course-desktop.png').exists()
        assert (stage / 'opt/cpp-backend-course-desktop/LICENSES.chromium.html').exists()
        try:
            # No --course-site override: the app discovers its own installed
            # resources/app/site layout exactly as the packaged program does.
            app = Desktop(temporary / 'profile', output / 'packaged-electron.log', binary=binary)
            page = app.page
            page.wait('!!document.querySelector("h1")')
            page.call('Network.emulateNetworkConditions', {'offline': True, 'latency': 0,
                'downloadThroughput': 0, 'uploadThroughput': 0})
            page.goto('course://app/roadmap/cpp_station0_oop_basics.html#section=why-oop', '!!document.querySelector("article h2")')
            assert page.js('typeof require') == 'undefined'
            page.goto('course://app/roadmap/sql_trainer.html#expression', '!!window.SqlLab')
            page.js('document.querySelector("#query").value="SELECT 42"')
            page.click('#run')
            page.wait('document.querySelector("#results").textContent.includes("42")')
            report.update({'courseVersion': manifest['version'], 'packageSha256': metadata['sha256'],
                'allPackagedFileHashesVerified': True, 'rootOwnedSandboxModeInArchive': helper,
                'packagedExecutableLaunchedWithoutSiteOverride': True, 'standaloneLessonAndSqlOffline': True,
                'passed': True})
            (output / 'real-package-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            if app:
                app.close()


if __name__ == '__main__':
    main()
