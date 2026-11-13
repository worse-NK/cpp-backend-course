#!/usr/bin/env python3
"""Run transfer logic in a real JavaScript engine without third-party JS modules."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

JAVASCRIPT = r'''
(function () {
  var tests = 0;
  function assert(value, label) { tests++; if (!value) throw new Error(label); }
  function throws(fn, label) { var thrown = false; try { fn(); } catch (_) { thrown = true; } assert(thrown, label); }
  function store(initial, failAt) {
    var data = Object.assign(Object.create(null), initial || {}), writes = 0;
    return {
      get length() { return Object.keys(data).length; },
      key: function (i) { return Object.keys(data)[i]; },
      getItem: function (k) { return Object.prototype.hasOwnProperty.call(data, k) ? data[k] : null; },
      setItem: function (k, v) { if (++writes === failAt) throw new Error('quota'); data[k] = v; },
      removeItem: function (k) { delete data[k]; },
      dump: function () { return JSON.stringify(data); }
    };
  }
  var api = CourseProgress;
  var original = store({
    cpp_station0_progress_v1: '{"sec:why-oop":true,"quiz:basic":{"score":3,"total":5}}',
    cpp_station7_netlab_progress_v1: '{"sec:route":true}',
    cpp_course_text_size_v1: 'large',
    cpp_course_last_read_v1: '{"file":"cpp_station0_oop_basics.html","section":"why-oop","title":"Зачем классы"}',
    'cpp-sql-lab:v1:expression': 'SELECT 1;\n-- Черновик <script>',
    'cpp-sql-lab:v1:join': '',
    unrelated: 'do not export'
  });
  var snap = api.exportSnapshot(original, { origin: 'https://example.test', version: 'test' });
  assert(api.validateSnapshot(snap) === 6, 'all actual progress types included');
  assert(!Object.prototype.hasOwnProperty.call(snap.entries, 'unrelated'), 'unrelated excluded');
  assert(snap.entries['cpp-sql-lab:v1:join'] === '', 'empty SQL draft retained');
  for (var i = 0; i <= 16; i++) assert(api.allowedKey('cpp_station' + i + '_progress_v1'), 'station key ' + i);
  ['cpp_station5_linux_progress_v1','cpp_station7_netlab_progress_v1','cpp_station7_traffic_progress_v1','cpp_station9_sql_progress_v1','cpp_basic_progress_v1','cpp_roadmap_progress_v1'].forEach(function (k) { assert(api.allowedKey(k), k); });
  ['cpp_station17_progress_v1','cpp_station0_linux_progress_v1','password','__proto__','cpp-sql-lab:v1:../../bad'].forEach(function (k) { assert(!api.allowedKey(k), 'unknown rejected ' + k); });
  var target = store({ unrelated: 'keep', cpp_station1_progress_v1: '{"sec:existing":true}', cpp_station0_progress_v1: '{}' });
  api.importSnapshot(target, JSON.parse(JSON.stringify(snap)));
  assert(target.getItem('unrelated') === 'keep', 'unrelated kept');
  assert(target.getItem('cpp_station1_progress_v1') === '{"sec:existing":true}', 'missing backup entries kept');
  assert(target.getItem('cpp_station0_progress_v1') === original.getItem('cpp_station0_progress_v1'), 'progress byte-for-byte');
  assert(target.getItem('cpp-sql-lab:v1:expression') === original.getItem('cpp-sql-lab:v1:expression'), 'SQL raw text');
  var invalid = JSON.parse(JSON.stringify(snap)); invalid.entries.password = 'leak';
  var before = target.dump(); throws(function () { api.importSnapshot(target, invalid); }, 'arbitrary storage import rejected');
  assert(target.dump() === before, 'invalid import no writes');
  invalid = JSON.parse(JSON.stringify(snap)); invalid.schemaVersion = 2;
  throws(function () { api.validateSnapshot(invalid); }, 'future schema rejected');
  invalid = JSON.parse(JSON.stringify(snap)); invalid.entries.cpp_station0_progress_v1 = '{"__proto__":{"polluted":true}}';
  throws(function () { api.validateSnapshot(invalid); }, 'prototype pollution rejected');
  assert({}.polluted === undefined, 'prototype untouched');
  invalid.entries.cpp_station0_progress_v1 = '[]';
  throws(function () { api.validateSnapshot(invalid); }, 'station arrays rejected');
  invalid.entries.cpp_station0_progress_v1 = '{bad';
  throws(function () { api.validateSnapshot(invalid); }, 'corrupt JSON rejected');
  invalid = JSON.parse(JSON.stringify(snap)); invalid.entries.cpp_course_last_read_v1 = '{"file":"javascript:alert(1)","section":"ok","title":"x"}';
  throws(function () { api.validateSnapshot(invalid); }, 'unsafe last-read URL rejected');
  invalid.entries.cpp_course_last_read_v1 = '{"file":"../cpp_station0.html","section":"ok","title":"x"}';
  throws(function () { api.validateSnapshot(invalid); }, 'traversal last-read URL rejected');
  invalid = JSON.parse(JSON.stringify(snap)); invalid.entries.cpp_course_text_size_v1 = '<script>';
  throws(function () { api.validateSnapshot(invalid); }, 'unknown text size rejected');
  invalid = JSON.parse(JSON.stringify(snap)); invalid.entries['cpp-sql-lab:v1:expression'] = 7;
  throws(function () { api.validateSnapshot(invalid); }, 'nonstring raw draft rejected');
  invalid.entries['cpp-sql-lab:v1:expression'] = 'x'.repeat(1024 * 1024 + 1);
  throws(function () { api.validateSnapshot(invalid); }, 'oversized draft rejected');
  var quota = store({ unrelated: 'keep', cpp_station0_progress_v1: '{}' }, 2);
  before = quota.dump(); throws(function () { api.importSnapshot(quota, snap); }, 'quota failure reported');
  assert(quota.dump() === before, 'quota rollback restores writes and absent keys');
  var empty = api.exportSnapshot(store({ unrelated: 'keep' }));
  assert(api.validateSnapshot(empty) === 0, 'empty backup valid');
  var bookmarklet = api.buildBookmarklet();
  assert(bookmarklet.indexOf('javascript:') === 0, 'bookmarklet is explicit executable bookmark');
  var legacyCode = decodeURIComponent(bookmarklet.slice('javascript:'.length));
  assert(!/\bfetch\s*\(|\beval\s*\(|XMLHttpRequest|sendBeacon/.test(legacyCode), 'legacy exporter has no networking or eval');
  var invokeLegacy = new Function('location','localStorage','document','URL','Blob','alert','setTimeout',legacyCode);
  var blobs = [], notices = [], downloads = 0;
  var fakeDocument = {
    body: {appendChild:function(){}},
    createElement:function(){return {click:function(){downloads++;},remove:function(){}};}
  };
  var fakeURL = {createObjectURL:function(blob){blobs.push(blob);return 'blob:test';},revokeObjectURL:function(){}};
  function invoke(location) { invokeLegacy(location, original, fakeDocument, fakeURL, Blob, function(t){notices.push(t);}, function(){}); }
  invoke({origin:'https://foreign.test',protocol:'https:',pathname:'/cpp-backend-course/roadmap/cpp_station0_oop_basics.html'});
  assert(downloads === 0 && notices.length === 1, 'foreign origin cannot export');
  invoke({origin:'https://worse-nk.github.io',protocol:'https:',pathname:'/not-our-course/'});
  assert(downloads === 0, 'other GitHub Pages project cannot export');
  invoke({origin:'null',protocol:'file:',pathname:'/tmp/unrelated.html'});
  assert(downloads === 0, 'unrelated local HTML cannot export');
  invoke({origin:'https://worse-nk.github.io',protocol:'https:',pathname:'/cpp-backend-course/roadmap/cpp_station0_oop_basics.html'});
  assert(downloads === 1 && blobs.length === 1, 'known course page produces exactly one download');
  invoke({origin:'null',protocol:'file:',pathname:'/home/reader/roadmap/cpp_station0_oop_basics.html'});
  assert(downloads === 2, 'known local station supported');
  blobs[0].text().then(async function(text){
    var exported = JSON.parse(text);
    assert(JSON.stringify(exported.entries) === JSON.stringify(snap.entries), 'legacy bookmarklet uses identical allowlist and exporter');
    assert(api.validateSnapshot(exported) === 6, 'legacy backup validates on local PWA');
    var nativeClick = HTMLAnchorElement.prototype.click;
    var nativeCreate = URL.createObjectURL;
    var actualBlob = null;
    HTMLAnchorElement.prototype.click = function(){ if (this.download) return; return nativeClick.call(this); };
    URL.createObjectURL = function(blob){ actualBlob = blob; return 'blob:export-test'; };
    localStorage.setItem('cpp_station0_progress_v1', '{"sec:why-oop":true}');
    var bookmark = document.createElement('a'); bookmark.href = bookmarklet; document.body.appendChild(bookmark);
    nativeClick.call(bookmark);
    await new Promise(function(resolve){setTimeout(resolve,100);});
    assert(actualBlob !== null, 'real javascript bookmark URL executes on old local file');
    var actualLegacy = JSON.parse(await actualBlob.text());
    assert(actualLegacy.entries.cpp_station0_progress_v1 === '{"sec:why-oop":true}', 'real legacy bookmark captures file-origin progress');
    HTMLAnchorElement.prototype.click = nativeClick; URL.createObjectURL = nativeCreate;
    document.getElementById('result').textContent = JSON.stringify({ pass: true, assertions: tests });
  }).catch(function(e){document.getElementById('result').textContent=JSON.stringify({pass:false,error:e.message});});
})()
'''


class ProgressBrowserTests(unittest.TestCase):
    def test_transfer(self):
        chrome = shutil.which('google-chrome') or shutil.which('chromium')
        if not chrome:
            self.skipTest('Chrome/Chromium not available')
        source = (ROOT / 'web/progress-core.js').read_text()
        with tempfile.TemporaryDirectory(prefix='course-progress-') as folder:
            path = Path(folder) / 'cpp_station0_oop_basics.html'
            path.write_text('<!doctype html><meta charset="utf-8"><pre id="result"></pre><script>'
                            + source + '</script><script>try {' + JAVASCRIPT
                            + '} catch(e) { document.getElementById("result").textContent = JSON.stringify({pass:false,error:e.message,stack:e.stack}); }</script>')
            result = subprocess.run([chrome, '--headless', '--disable-gpu', '--no-first-run',
                                     '--user-data-dir=' + str(Path(folder) / 'profile'),
                                     '--virtual-time-budget=1000', '--dump-dom', path.as_uri()], capture_output=True, text=True, timeout=35)
            self.assertEqual(result.returncode, 0, result.stderr[-3000:])
            import re
            match = re.search(r'<pre id="result">(.*?)</pre>', result.stdout, re.S)
            self.assertIsNotNone(match, result.stdout[-3000:])
            report = json.loads(match.group(1))
            self.assertTrue(report.get('pass'), report)
            self.assertGreaterEqual(report['assertions'], 45)


if __name__ == '__main__':
    unittest.main()
