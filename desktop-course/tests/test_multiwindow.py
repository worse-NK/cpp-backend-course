#!/usr/bin/env python3
"""Regression: a theory window must not erase another window's quiz progress."""
import json
from pathlib import Path
import sys
import tempfile
import time

from cdp import Desktop, ROOT
from test_browser import finish_question

sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
import build_site


def complete(page):
    count = 0
    while not page.js('!!document.querySelector(".verdict")'):
        if page.js('!!document.querySelector(".explanation .primary")'):
            page.click('.explanation .primary')
        else:
            finish_question(page)
        count += 1
        assert count <= 30
    assert count >= 20


def main():
    report = {'sandboxDisabled': False, 'checks': []}
    with tempfile.TemporaryDirectory(prefix='course-multiwindow-') as directory:
        temporary = Path(directory)
        site = temporary / 'site'
        build_site.write_site(site)
        desktop = Desktop(temporary / 'profile', temporary / 'electron.log', site)
        try:
            first = desktop.page
            url = 'course://app/roadmap/cpp_station0_oop_basics.html'
            key = 'cpp_station0_progress_v1'
            record = 'JSON.parse(localStorage.getItem(' + json.dumps(key) + ') || "{}")'
            first.goto(url + '#view=quiz', '!!document.querySelector(".option")')
            first.click('.option')
            first.wait('!!document.querySelector(".explanation")')
            question = first.js('document.querySelector(".counter").textContent + document.querySelector(".explanation").textContent')
            old_targets = {target['id'] for target in desktop.targets()}
            first.js('window.open(' + json.dumps(url + '#section=why-oop') + ', "_blank");true')
            for _ in range(100):
                targets = [target for target in desktop.targets() if target['type'] == 'page' and target['id'] not in old_targets]
                if targets:
                    break
                time.sleep(.08)
            assert targets
            second = desktop.connect(targets[0])
            second.wait('!!document.querySelector("article h2")')
            second.click('.section-actions .primary')
            first.wait(record + '["sec:why-oop"] === true')
            first.wait('document.querySelector(".masthead-progress")?.textContent.includes("1") || document.querySelector(".reading-progress")?.textContent.includes("1")')
            assert first.js('document.querySelector(".counter").textContent + document.querySelector(".explanation").textContent') == question
            report['checks'].append('theory mark reaches quiz window without remounting its answered question')
            complete(first)
            saved = first.js(record)
            score_key = next(name for name in saved if name.startswith('station-final:') and name.endswith(':basic'))
            assert saved['sec:why-oop'] and saved[score_key]['total'] == 25
            report['checks'].append('quiz completion retains the other window theory mark')
            second.js('location.hash="#section=struct-to-class"')
            second.wait('document.querySelector("article h2")?.textContent.includes("struct")')
            second.click('.section-actions .primary')
            second.wait(record + '["sec:struct-to-class"] === true')
            assert second.js(record)[score_key] == saved[score_key]
            report['checks'].append('stale theory window retains completed quiz score while marking another section')

            first.js('document.querySelector(".verdict").parentElement.querySelector("button.primary").click()')
            first.wait('!!document.querySelector(".option")')
            first.click('.option')
            first.wait('!!document.querySelector(".explanation")')
            question = first.js('document.querySelector(".counter").textContent + document.querySelector(".explanation").textContent')
            # Accept only this explicit reset in the disposable test page; no
            # personal data/dialogs are involved in the regression.
            second.js('window.confirm=()=>true;document.querySelector(".reset").click();true')
            first.wait('Object.keys(' + record + ').length === 0')
            assert first.js('document.querySelector(".counter").textContent + document.querySelector(".explanation").textContent') == question
            complete(first)
            after = first.js(record)
            assert after[score_key]['total'] == 25
            assert not any(name.startswith('sec:') for name in after)
            report['checks'].append('explicit reset synchronizes without resetting the unfinished quiz; later save does not resurrect old marks')
            assert second.js('document.querySelector("article .section-actions .primary").textContent') == 'Отметить раздел изученным'
            report['checks'].append('other window live UI reflects cleared marks')
            report['passed'] = True
            output = ROOT / 'release/qa'
            output.mkdir(parents=True, exist_ok=True)
            (output / 'multiwindow-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            desktop.close()


if __name__ == '__main__':
    main()
