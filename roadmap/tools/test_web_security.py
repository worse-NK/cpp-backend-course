"""Static security contracts; actual browser enforcement is checked separately."""
import base64
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('course_web_security_test', ROOT / 'tools/web_security.py')
security = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(security)
REACT = 'https://unpkg.com/react@18.3.1/umd/react.production.min.js'
DOM = 'https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js'
VENDOR = ROOT.parent / 'desktop-course/vendor'


class Tags(HTMLParser):
    def __init__(self, value):
        super().__init__()
        self.tags = []
        self.feed(value.decode() if isinstance(value, bytes) else value)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def page(body, head=''):
    return ('<!doctype html><html><head><meta charset="utf-8">' + head +
            '</head><body>' + body + '</body></html>').encode()


def policy(value):
    metas = [attrs for tag, attrs in Tags(value).tags if tag == 'meta'
             and attrs.get('data-course-security') == '1']
    if len(metas) != 1:
        raise AssertionError('Exactly one generated early CSP is required')
    return dict((part.strip().split(' ', 1) + [''])[:2]
                for part in metas[0]['content'].split(';') if part.strip())


class WebSecurityTests(unittest.TestCase):
    def test_csp_precedes_resources_and_reapplying_is_byte_identical(self):
        source = page('<h1>Пример</h1>', '<script src="assets/app.js"></script>')
        result = security.secure_html(source, name='roadmap/example.html')
        self.assertLess(result.index(b'Content-Security-Policy'), result.index(b'assets/app.js'))
        self.assertLess(result.index(b'charset="utf-8"'), result.index(b'Content-Security-Policy'))
        self.assertEqual(security.secure_html(result, name='roadmap/example.html'), result)
        rules = policy(result)
        for name in ('default-src', 'connect-src', 'object-src', 'base-uri', 'form-action', 'script-src-attr'):
            self.assertEqual(rules[name], "'none'")
        self.assertEqual(rules['frame-src'], "'self'")
        self.assertEqual(rules['worker-src'], "'self' blob:")
        self.assertNotIn('frame-ancestors', rules)
        self.assertNotIn("'unsafe-inline'", rules['script-src'])
        self.assertNotIn("'unsafe-eval'", rules['script-src'])

    def test_inline_javascript_hash_preserves_bytes_but_json_is_not_executable(self):
        code = '\nwindow.example = "Привет";\n'
        source = page('<script>' + code + '</script><script type="application/json">{"example":1}</script>')
        result = security.secure_html(source, name='roadmap/example.html')
        expected = "'sha256-" + base64.b64encode(hashlib.sha256(code.encode()).digest()).decode() + "'"
        self.assertIn(expected, policy(result)['script-src'])
        self.assertEqual(policy(result)['script-src'].count("'sha256-"), 1)
        self.assertIn(('<script>' + code + '</script>').encode(), result)
        injected = result.replace(b'</body>', b'<script>window.untrusted=1;</script></body>')
        unknown = "'sha256-" + base64.b64encode(hashlib.sha256(b'window.untrusted=1;').digest()).decode() + "'"
        self.assertNotIn(unknown, policy(injected)['script-src'])

    def test_only_remote_react_gets_sri_and_crossorigin(self):
        source = page('<script src="assets/app.js"></script>',
            '<script crossorigin src="' + REACT + '"></script><script src="' + DOM + '"></script>')
        result = security.secure_html(source, name='roadmap/example.html')
        scripts = {a['src']: a for tag, a in Tags(result).tags if tag == 'script' and 'src' in a}
        for url, filename in ((REACT, 'react.production.min.js'), (DOM, 'react-dom.production.min.js')):
            expected = 'sha384-' + base64.b64encode(hashlib.sha384((VENDOR / 'react' / filename).read_bytes()).digest()).decode()
            self.assertEqual(scripts[url]['integrity'], expected)
            self.assertEqual(scripts[url]['crossorigin'], 'anonymous')
            self.assertIn("'" + expected + "'", policy(result)['script-src'])
        self.assertNotIn('integrity', scripts['assets/app.js'])
        self.assertNotIn('crossorigin', scripts['assets/app.js'])
        self.assertNotIn('unpkg.com', policy(result)['script-src'])

    def test_pinned_vendor_changes_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix='course-web-vendor-') as temporary:
            fixture = Path(temporary)
            (fixture / 'react').mkdir()
            lock = {'format': 1, 'files': {}}
            for filename in ('react.production.min.js', 'react-dom.production.min.js'):
                relative = 'react/' + filename
                (fixture / relative).write_bytes(b'fixture')
                lock['files'][relative] = hashlib.sha256(b'fixture').hexdigest()
            (fixture / 'ORIGIN.json').write_text(json.dumps(lock))
            (fixture / 'react/react.production.min.js').write_bytes(b'changed')
            with patch.object(security, 'VENDOR', fixture), self.assertRaisesRegex(ValueError, 'hash'):
                security.secure_html(page('', '<script src="' + REACT + '"></script>'), name='roadmap/example.html')

    def test_arbitrary_external_runtime_urls_or_inline_event_attributes_are_rejected(self):
        for text in ('<script src="https://other.invalid/a.js"></script>',
                     '<iframe src="https://other.invalid/"></iframe>',
                     '<link rel="stylesheet" href="https://other.invalid/a.css">',
                     '<button onclick="window.untrusted=1">Click</button>',
                     '<script src="javascript:window.untrusted=1"></script>'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                security.secure_html(page(text), name='roadmap/example.html')

    def test_old_stricter_policy_is_preserved_not_weakened(self):
        source = page('<h1>Example</h1>', '<meta http-equiv="Content-Security-Policy" content="connect-src \'none\'; script-src \'none\'">')
        result = security.secure_html(source, name='roadmap/example.html')
        metas = [a for tag, a in Tags(result).tags if tag == 'meta'
                 and a.get('http-equiv', '').lower() == 'content-security-policy']
        self.assertEqual(len(metas), 2)
        self.assertTrue(any(a.get('content') == "connect-src 'none'; script-src 'none'" for a in metas))
        self.assertEqual(security.secure_html(result, name='roadmap/example.html'), result)

    def test_existing_style_attributes_and_script_properties_still_work(self):
        source = page('<p style="white-space:pre-line">Example</p><script>window.onclick=function() {};</script>')
        result = security.secure_html(source, name='roadmap/example.html')
        self.assertIn(b'style="white-space:pre-line"', result)
        self.assertIn("'unsafe-inline'", policy(result)['style-src'])
        self.assertIn(b'window.onclick=function() {};', result)

    def test_local_and_desktop_mode_forbid_external_dependencies(self):
        source = page('<script src="assets/app.js"></script><iframe src="sql_trainer.html"></iframe>')
        for mode in ('local', 'desktop'):
            result = security.secure_html(source, name='roadmap/example.html', mode=mode)
            self.assertNotIn('https:', policy(result)['script-src'])
            self.assertEqual(policy(result)['style-src'], "'self' 'unsafe-inline'")
            self.assertEqual(policy(result)['font-src'], "'self'")
            with self.assertRaises(ValueError):
                security.secure_html(page('', '<script src="' + REACT + '"></script>'), name='roadmap/example.html', mode=mode)

    def test_files_collection_preserves_non_html_and_checks_local_targets(self):
        source = page('<script src="../app.js?v=one"></script>')
        files = {'roadmap/example.html': source, 'app.js': b'window.example=1;', 'binary.ttf': b'\xff\x00fixture'}
        result = security.secure_files(files)
        self.assertEqual(result['app.js'], files['app.js'])
        self.assertEqual(result['binary.ttf'], files['binary.ttf'])
        self.assertEqual(files['roadmap/example.html'], source)
        self.assertIn('default-src', policy(result['roadmap/example.html']))
        with self.assertRaisesRegex(ValueError, 'Missing'):
            security.secure_files({'roadmap/example.html': source})

    def test_crlf_and_cr_are_normalized_for_browser_script_hashes(self):
        code = '\r\nwindow.example = 1;\rwindow.other = 2;\r\n'
        result = security.secure_html(page('<script>' + code + '</script>'))
        normalized = code.replace('\r\n', '\n').replace('\r', '\n')
        expected = "'sha256-" + base64.b64encode(hashlib.sha256(normalized.encode()).digest()).decode() + "'"
        self.assertIn(expected, policy(result)['script-src'])
        self.assertIn(code.encode(), result)

    def test_unicode_separator_does_not_shift_script_source_offsets(self):
        code = '\nwindow.example="A\u2028B";\n'
        result = security.secure_html(page('<script>' + code + '</script>'))
        expected = "'sha256-" + base64.b64encode(hashlib.sha256(code.encode()).digest()).decode() + "'"
        self.assertIn(expected, policy(result)['script-src'])
        self.assertIn(code.encode(), result)

    def test_misplaced_charset_cannot_move_policy_after_active_content(self):
        source = b'<html><head><script>window.example=1;</script><meta charset="utf-8"></head><body></body></html>'
        result = security.secure_html(source)
        self.assertLess(result.index(b'Content-Security-Policy'), result.index(b'<script>'))

    def test_react_attribute_values_are_not_rewritten_as_attribute_names(self):
        source = page('', '<script src="' + REACT + '" title=\'contains integrity="example"\'></script>')
        result = security.secure_html(source)
        script = next(attrs for tag, attrs in Tags(result).tags if tag == 'script')
        self.assertEqual(script['title'], 'contains integrity="example"')
        self.assertTrue(script['integrity'].startswith('sha384-'))
        self.assertEqual(security.secure_html(result), result)

    def test_symlinked_vendor_lock_is_refused(self):
        with tempfile.TemporaryDirectory(prefix='course-lock-symlink-') as temporary:
            fixture = Path(temporary)
            outside = fixture / 'outside.json'
            outside.write_text('{}')
            (fixture / 'ORIGIN.json').symlink_to(outside)
            with patch.object(security, 'VENDOR', fixture), self.assertRaisesRegex(ValueError, 'symlink'):
                security.secure_html(page('', '<script src="' + REACT + '"></script>'))

    def test_duplicate_attributes_and_local_path_escape_are_rejected(self):
        for body in ('<script src="a.js" src="b.js"></script>',
                     '<script src="../outside.js"></script>',
                     '<script src="%2e%2e/outside.js"></script>'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                security.secure_html(page(body))

    def test_validation_goes_red_for_an_injected_script_or_changed_sri(self):
        files = {'index.html': page('<script>window.example=1;</script>',
            '<script src="' + REACT + '"></script>')}
        secured = security.secure_files(files)
        self.assertEqual(security.validate_files(secured), 1)
        injected = dict(secured)
        injected['index.html'] = injected['index.html'].replace(b'</body>', b'<script>window.untrusted=1;</script></body>')
        with self.assertRaisesRegex(ValueError, 'stale'):
            security.validate_files(injected)
        changed = dict(secured)
        changed['index.html'] = changed['index.html'].replace(b'integrity="sha384-', b'integrity="sha512-')
        with self.assertRaisesRegex(ValueError, 'stale'):
            security.validate_files(changed)

    def test_full_publication_pages_are_protected_and_byte_idempotent(self):
        sys.path.insert(0, str(ROOT / 'tools'))
        try:
            import build_publication
            files, stations = build_publication.collect()
        finally:
            sys.path.pop(0)
        secured = security.secure_files(files)
        self.assertGreaterEqual(security.validate_files(secured), 36)
        self.assertEqual(len(stations), 21)


if __name__ == '__main__':
    unittest.main(verbosity=2)
