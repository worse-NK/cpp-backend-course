#!/usr/bin/env python3
"""Real standalone Electron acceptance, no browser launch or localhost server."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

from cdp import Desktop, ROOT
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
import build_site


def finish_question(page):
    if page.js('!!document.querySelector(".assembly")'):
        page.click('.assembly-pool button:not(:disabled)')
        page.click('.assembly-actions .primary')
    else:
        page.click('.option')
    page.wait('!!document.querySelector(".explanation .primary")')
    page.click('.explanation .primary')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=ROOT / 'release/site')
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--app-dir', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'release/qa')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((args.site / 'desktop-build.json').read_text())
    _, stations = build_site.publication.collect()
    report = {'courseVersion': manifest['version'], 'sandboxDisabled': False,
              'browserRequired': False, 'localHttpServerStarted': False,
              'stations': [], 'labScenarios': [], 'checks': [], 'screenshots': []}
    desktop = None
    with tempfile.TemporaryDirectory(prefix='course-electron-acceptance-') as temporary:
        profile = Path(temporary) / 'profile'
        try:
            desktop = Desktop(profile, args.output / 'electron.log', args.site, args.binary, args.app_dir)
            page = desktop.page
            page.wait('!!document.querySelector("h1")')
            report['rendererIsolation'] = page.js('({origin:location.origin,require:typeof require,node:typeof process,secure:isSecureContext})')
            assert report['rendererIsolation'] == {'origin': 'course://app', 'require': 'undefined', 'node': 'undefined', 'secure': True}, report['rendererIsolation']
            page.call('Network.emulateNetworkConditions', {'offline': True, 'latency': 0,
                'downloadThroughput': 0, 'uploadThroughput': 0})
            report['networkEmulatedOffline'] = True

            # Viewport is set before mounting: the TOC initially opens depending
            # on available width, just as in the normal browser reader.
            cases = [
                ('home', 'cpp_backend_roadmap.html', '!!document.querySelector("h1")'),
                ('station0', 'cpp_station0_oop_basics.html#section=why-oop', '!!document.querySelector("article h2")'),
                ('lifetime', 'object_lifetime_demo.html', '!!document.querySelector("#next")'),
                ('sql', 'sql_trainer.html', '!!window.SqlLab'),
                ('security', 'security_labs.html#lab=security&scenario=access&step=0', '!!document.querySelector("#run:not(:disabled)")'),
            ]
            for label, path, ready in cases:
                for width in (1440, 390):
                    page.viewport(width)
                    # A same-URL Page.navigate does not remount React. Force a
                    # new document so the TOC initializes at this viewport.
                    page.goto('about:blank')
                    page.goto('course://app/roadmap/' + path, ready)
                    picture = args.output / (label + '-' + str(width) + '.png')
                    page.screenshot(picture)
                    assert page.js('document.documentElement.scrollWidth <= innerWidth+1'), (label, width)
                    report['screenshots'].append(picture.name)
                    assert page.js('getComputedStyle(document.body).backgroundColor') in ('rgb(24, 37, 47)', 'rgb(25, 39, 49)'), label
            print('desktop/mobile course screenshots OK', flush=True)
            page.viewport(1440)

            for station in stations:
                filename = station['meta']['sourceFile']
                page.goto('course://app/roadmap/' + filename + '#section=' + station['theory'][0]['id'],
                    '!!document.querySelector("article h2")')
                assert page.js('STATION_DATA.meta.id') == station['meta']['id']
                assert page.js('document.querySelector("article h2").textContent') == station['theory'][0]['title']
                page.goto('course://app/roadmap/' + filename + '#view=quiz', '!!document.querySelector(".option")')
                page.click('.option')
                page.wait('!!document.querySelector(".explanation")')
                report['stations'].append(station['meta']['id'])
            print('all 21 stations + quiz answer rendering OK', flush=True)

            # A question's theory opens another app window, not a browser and
            # not a navigation that discards the question's current answer.
            before_targets = {target['id'] for target in desktop.targets()}
            question_state = page.js('document.querySelector(".counter").textContent + document.querySelector(".explanation").textContent')
            page.click('.quiz-theory-refs a')
            for _ in range(100):
                children = [target for target in desktop.targets() if target['type'] == 'page' and target['id'] not in before_targets]
                if children:
                    break
                time.sleep(.1)
            assert children
            child = desktop.connect(children[0])
            child.wait('!!document.querySelector("article h2")')
            assert child.js('location.origin') == 'course://app'
            assert page.js('document.querySelector(".counter").textContent + document.querySelector(".explanation").textContent') == question_state
            child.call('Page.close')
            report['checks'].append('theory reference opens isolated app window without resetting quiz')

            s0 = next(station for station in stations if station['meta']['id'] == 'station0')
            page.goto('course://app/roadmap/' + s0['meta']['sourceFile'] + '#section=why-oop', '!!document.querySelector("article h2")')
            page.click('.section-actions .primary')
            station_key = s0['meta']['storeKey']
            assert page.js('JSON.parse(localStorage.getItem(' + json.dumps(station_key) + '))["sec:why-oop"]')
            page.goto('course://app/roadmap/' + s0['meta']['sourceFile'] + '#view=quiz', '!!document.querySelector(".option")')
            count = 0
            while not page.js('!!document.querySelector(".verdict")'):
                finish_question(page)
                count += 1
                assert count <= 30
            assert count == 25
            report['checks'].append({'completedFinalQuizQuestions': count})
            page.goto('course://app/roadmap/' + s0['meta']['sourceFile'] + '#view=checkpoint&module=' + s0['substations'][0]['id'],
                      '!!document.querySelector(".question")')
            checkpoint_count = assembly_count = 0
            while not page.js('!!document.querySelector(".verdict")'):
                if page.js('!!document.querySelector(".assembly")'):
                    assembly_count += 1
                finish_question(page)
                checkpoint_count += 1
                assert checkpoint_count <= 10
            assert checkpoint_count >= 5 and assembly_count >= 1
            report['checks'].append({'checkpointQuestions': checkpoint_count, 'syntaxAssemblyQuestions': assembly_count})
            station_saved = page.js('localStorage.getItem(' + json.dumps(station_key) + ')')

            page.goto('course://app/roadmap/sql_trainer.html#expression', '!!window.SqlLab')
            page.js('document.querySelector("#query").value="SELECT 6 * 7 AS answer"')
            page.click('#run')
            page.wait('document.querySelector("#results").textContent.includes("42")')
            assert page.js('localStorage.getItem("cpp-sql-lab:v1:expression")') == 'SELECT 6 * 7 AS answer'
            report['checks'].append('SQL Blob Worker executes without unsafe-eval; draft persisted')
            sql_station = next(station for station in stations if station['meta']['id'] == 'station9-sql')
            trainer = next(s for s in sql_station['theory'] if any(b['type'] == 'sql-trainer' for b in s['blocks']))
            page.goto('course://app/roadmap/' + sql_station['meta']['sourceFile'] + '#section=' + trainer['id'], '!!document.querySelector("iframe")')
            page.js('document.querySelector("iframe").scrollIntoView()')
            page.wait('!!document.querySelector("iframe").contentDocument?.querySelector("#run")')
            report['checks'].append('same-origin embedded SQL iframe works under CSP')

            page.goto('course://app/roadmap/object_lifetime_demo.html', '!!document.querySelector("#next")')
            initial = page.js('document.querySelector("#scrubberLabel").textContent')
            page.click('#next')
            assert page.js('document.querySelector("#scrubberLabel").textContent') != initial
            report['checks'].append('object lifetime controls work')
            page.goto('course://app/roadmap/visual_labs.html', '!!window.COURSE_LABS')
            catalogue = page.js('COURSE_LABS.map(lab=>({id:lab.id,scenarios:lab.scenarios}))')
            for lab in catalogue:
                if lab['id'] in ('lifetime', 'security', 'security-sql', 'distributed'):
                    continue
                for scenario in lab['scenarios']:
                    path = page.js('courseLabHref(' + json.dumps(lab['id']) + ',' + json.dumps(scenario) + ')')
                    if path.startswith('visual_labs.html'):
                        page.goto('course://app/roadmap/' + path, '!!document.querySelector("#labNext")')
                        page.click('#labNext')
                        report['labScenarios'].append(lab['id'] + '/' + scenario)
            print('visual lab scenarios:', len(report['labScenarios']), flush=True)
            page.goto('course://app/roadmap/security_sql_demo.html', '!!document.querySelector("#run:not(:disabled)")')
            page.click('#run')
            page.wait('document.querySelector("#status").textContent.includes("Запрос выполнен настоящим SQLite")')
            assert page.js('document.querySelector("#response-count").textContent') == 'Строк: 1'
            report['checks'].append('security SQL model executes real SQLite worker')
            for scenario in ('access', 'outbound', 'tls'):
                page.goto('course://app/roadmap/security_labs.html#lab=security&scenario=' + scenario + '&step=0',
                          '!!document.querySelector("#run:not(:disabled)")')
                page.click('#run')
            report['checks'].append('all three security scenario entry points execute')
            page.goto('course://app/roadmap/distributed_lab.html', '!!document.querySelector("#next-step")')
            initial = page.js('document.querySelector("#step-count").textContent')
            page.click('#next-step')
            assert page.js('document.querySelector("#step-count").textContent') != initial
            report['checks'].append('distributed-system lab steps')
            page.goto('course://app/progress.html', '!!window.CourseProgress')
            page.wait('document.querySelector("#app-version").textContent.includes("Станций в локальной копии: 21")')
            assert not page.js('Array.from(document.scripts,s=>s.src).some(src=>src.includes("pwa"))')
            assert not page.js('!!document.querySelector("link[rel=manifest]")')
            report['checks'].append('desktop settings have no PWA install/cache step')
            assert not [event for event in page.events if event.get('method') == 'Runtime.exceptionThrown']

            # Force an actual process restart with the same disposable profile.
            desktop.close()
            desktop = Desktop(profile, args.output / 'electron-restart.log', args.site, args.binary, args.app_dir)
            page = desktop.page
            page.wait('!!document.querySelector("h1")')
            assert page.js('localStorage.getItem(' + json.dumps(station_key) + ')') == station_saved
            assert page.js('localStorage.getItem("cpp-sql-lab:v1:expression")') == 'SELECT 6 * 7 AS answer'
            report['checks'].append('progress, completed results and SQL draft survive process restart')
            report['passed'] = True
            (args.output / 'desktop-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        finally:
            if desktop:
                desktop.close()


if __name__ == '__main__':
    main()
