#!/usr/bin/env python3
"""Exercise real Electron progress controls with an isolated, persistent profile.

The save-data pipeline is captured at the Blob/anchor boundary so this check does
not automate or claim verification of the operating system's native Save As
dialog. File inputs, importer controls, confirmation branches, rollback and an
actual application restart are exercised. No personal browser/profile is used.
"""
import argparse
import json
from pathlib import Path
import tempfile
import time

from cdp import Desktop, ROOT


INSTRUMENT = r'''(() => {
  window.__qaDownloads = [];
  window.__qaBlobs = new Map();
  window.__qaPrompts = [];
  window.__qaConfirmAnswers = [];
  const create = URL.createObjectURL.bind(URL);
  URL.createObjectURL = function (blob) {
    const url = create(blob); window.__qaBlobs.set(url, blob); return url;
  };
  const click = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    const blob = window.__qaBlobs.get(this.href);
    if (this.download && blob) {
      const record = {name: this.download, json: null};
      window.__qaDownloads.push(record);
      blob.text().then(text => { record.json = JSON.parse(text); });
      return;
    }
    return click.apply(this, arguments);
  };
  window.confirm = function (message) {
    window.__qaPrompts.push(message);
    return window.__qaConfirmAnswers.shift() === true;
  };
  return true;
})()'''


def upload(page, path):
    document = page.call('DOM.getDocument')
    selected = page.call('DOM.querySelector', {
        'nodeId': document['root']['nodeId'], 'selector': '#progress-file'})
    page.call('DOM.setFileInputFiles', {'nodeId': selected['nodeId'], 'files': [str(path)]})


def values(page, keys):
    return page.js('Object.fromEntries(' + json.dumps(keys) + '.map(key=>[key,localStorage.getItem(key)]))')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=ROOT / 'release/site')
    parser.add_argument('--output', type=Path, default=ROOT / 'release/qa')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((args.site / 'desktop-build.json').read_text())
    report = {'courseVersion': metadata['version'], 'sandboxDisabled': False,
              'personalProfileChanged': False, 'checks': [], 'screenshots': [],
              'nativeSaveDialog': 'not automated; exported JSON captured from the actual UI Blob before anchor download',
              'confirmationDialogs': 'UI confirmation branches tested with explicit queued answers in disposable renderer only'}
    app = None
    with tempfile.TemporaryDirectory(prefix='course-desktop-progress-') as folder:
        temporary = Path(folder)
        profile = temporary / 'profile'
        try:
            app = Desktop(profile, temporary / 'first-run.log', site=args.site)
            page = app.page
            page.goto('course://app/progress.html',
                      'document.querySelector("#app-version")?.textContent.includes("Версия приложения")')
            assert page.js('document.querySelector("#app-status").dataset.error !== "true"')
            assert page.js('typeof require === "undefined" && typeof process === "undefined"')
            assert page.js('!document.querySelector("link[rel=manifest],#offline-install,#offline-recheck")')
            report['checks'].append('desktop metadata loads; no PWA install/cache controls; no Node globals in renderer')

            initial = {
                'cpp_station0_progress_v1': '{"sec:why-oop":true}',
                'cpp_station2_progress_v1': '{"sec:existing":true}',
                'cpp_course_text_size_v1': 'large',
                'cpp-sql-lab:v1:expression': 'SELECT 6 * 7 AS answer;',
                'qa-unrelated': 'must stay'
            }
            page.js('Object.entries(' + json.dumps(initial) + ').forEach(([key,value])=>localStorage.setItem(key,value))')
            assert page.js(INSTRUMENT)
            for width, label in ((1440, 'desktop'), (390, 'mobile')):
                page.viewport(width, 1000)
                assert page.js('document.documentElement.scrollWidth <= innerWidth + 1'), label
                assert page.js('Array.from(document.querySelectorAll("main button")).filter(e=>e.getClientRects().length).every(e=>e.getBoundingClientRect().width<=innerWidth && e.getBoundingClientRect().height<160)'), label
                page.js('document.querySelector("#progress-export").focus()')
                focus = page.js('({visible:document.querySelector("#progress-export").matches(":focus-visible"),width:getComputedStyle(document.querySelector("#progress-export")).outlineWidth})')
                assert focus['visible'] and float(focus['width'].replace('px', '')) >= 2, focus
                path = args.output / ('progress-' + label + '.png')
                page.screenshot(path)
                report['screenshots'].append(path.name)
            report['checks'].append('1440/390 px: shared dark styling, natural-size wrapping controls, visible focus, no horizontal overflow')

            page.click('#progress-export')
            page.wait('window.__qaDownloads[0]?.json')
            exported = page.js('window.__qaDownloads[0]')
            expected = {key: value for key, value in initial.items() if key != 'qa-unrelated'}
            assert exported['json']['entries'] == expected, exported
            assert exported['json']['format'] == 'cpp-backend-course-progress'
            assert exported['json']['schemaVersion'] == 1
            assert page.js('document.querySelector("#export-message").textContent.includes("Записей: 4")')
            assert values(page, list(initial)) == initial
            report['checks'].append('actual export button serializes only course keys and leaves current data unchanged')

            selected = {
                'format': 'cpp-backend-course-progress', 'schemaVersion': 1,
                'sourceOrigin': 'https://worse-nk.github.io',
                'entries': {'cpp_station0_progress_v1': '{"sec:why-oop":false}',
                            'cpp_station1_progress_v1': '{"sec:raii":true}',
                            'cpp_course_text_size_v1': 'normal'}
            }
            valid_file = temporary / 'valid-backup.json'
            valid_file.write_text(json.dumps(selected, ensure_ascii=False))
            upload(page, valid_file)
            page.wait('!document.querySelector("#progress-import").hidden')
            assert values(page, list(initial)) == initial
            page.js('window.__qaConfirmAnswers=[false]')
            page.click('#progress-import')
            assert values(page, list(initial)) == initial
            assert page.js('window.__qaDownloads.length') == 1
            assert page.js('!document.querySelector("#progress-import").hidden')
            page.js('window.__qaConfirmAnswers=[true]')
            page.click('#progress-import')
            page.wait('window.__qaDownloads[1]?.json && !!document.querySelector("#progress-confirm-import")')
            assert page.js('window.__qaDownloads[1].json.entries') == expected
            assert page.js('window.__qaDownloads[1].name.startsWith("cpp-course-before-import")')
            assert values(page, list(initial)) == initial
            page.js('window.__qaConfirmAnswers=[false]')
            page.click('#progress-confirm-import')
            assert values(page, list(initial)) == initial
            page.js('window.__qaConfirmAnswers=[true]')
            page.click('#progress-confirm-import')
            page.wait('document.querySelector("#import-message").textContent.includes("Восстановлено записей: 3")')
            for key, value in selected['entries'].items():
                assert page.js('localStorage.getItem(' + json.dumps(key) + ')') == value
            assert page.js('localStorage.getItem("qa-unrelated")') == 'must stay'
            assert page.js('localStorage.getItem("cpp_station2_progress_v1")') == initial['cpp_station2_progress_v1']
            report['checks'].append('DOM file upload, preview, both cancellation branches, backup-before-import and second explicit apply control work')
            report['checks'].append('import replaces matching course keys only; unrelated and absent backup entries retained')

            before_invalid = values(page, list(initial) + ['cpp_station1_progress_v1'])
            invalid = dict(selected)
            invalid['entries'] = {'password': 'must never be imported'}
            invalid_file = temporary / 'invalid-backup.json'
            invalid_file.write_text(json.dumps(invalid))
            upload(page, invalid_file)
            page.wait('document.querySelector("#import-message").textContent.includes("не относящиеся к курсу")')
            assert page.js('document.querySelector("#progress-import").hidden')
            assert values(page, list(before_invalid)) == before_invalid
            report['checks'].append('invalid backup with unrelated key is refused before writing')

            rollback = dict(selected)
            rollback['entries'] = {'cpp_station0_progress_v1': '{"sec:rollback-test":true}',
                                   'cpp_station1_progress_v1': '{"sec:rollback-test":true}'}
            rollback_file = temporary / 'quota-test.json'
            rollback_file.write_text(json.dumps(rollback))
            upload(page, rollback_file)
            page.wait('!document.querySelector("#progress-import").hidden')
            page.js('window.__qaConfirmAnswers=[true]')
            page.click('#progress-import')
            page.wait('!!document.querySelector("#progress-confirm-import")')
            page.js('''window.__qaStorageSet = Storage.prototype.setItem;
              window.__qaWrites=0;
              Storage.prototype.setItem=function(key,value){
                if(key.startsWith('cpp_station') && ++window.__qaWrites===2)
                  throw new DOMException('QA quota failure','QuotaExceededError');
                return window.__qaStorageSet.call(this,key,value);
              };window.__qaConfirmAnswers=[true]''')
            page.click('#progress-confirm-import')
            page.wait('document.querySelector("#import-message").textContent.includes("Прежний прогресс восстановлен")')
            page.js('Storage.prototype.setItem=window.__qaStorageSet')
            assert values(page, list(before_invalid)) == before_invalid
            report['checks'].append('injected mid-import storage failure restores earlier writes and reports rollback')
            errors = [event for event in page.events if event.get('method') == 'Runtime.exceptionThrown']
            assert not errors, errors
            app.close()
            app = None

            # The profile is reused, but the actual Electron process is new.
            app = Desktop(profile, temporary / 'second-run.log', site=args.site)
            page = app.page
            page.goto('course://app/progress.html',
                      'document.querySelector("#app-version")?.textContent.includes("Версия приложения")')
            assert values(page, list(before_invalid)) == before_invalid
            page.call('Network.emulateNetworkConditions', {'offline': True, 'latency': 0,
                'downloadThroughput': 0, 'uploadThroughput': 0})
            page.call('Page.reload')
            page.wait('document.querySelector("#app-version")?.textContent.includes("Версия приложения")')
            assert values(page, list(before_invalid)) == before_invalid
            report['checks'].append('saved progress and SQL draft survive full application close/restart and offline page reload')
            report['uncaughtJavaScriptErrors'] = []
            report['status'] = 'passed'
            (args.output / 'progress-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            if app:
                app.close()


if __name__ == '__main__':
    main()
