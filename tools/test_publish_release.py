"""Release publication contracts; HTTP and package commands are mocked."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('course_publish_release', ROOT / 'tools/publish_release.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
SHA = 'a' * 40
TAG = 'desktop-v1.1.1'
REPOSITORY = 'worse-NK/cpp-backend-course'


class FakeGitHub:
    def __init__(self, manifest, tagged=True):
        self.repository = REPOSITORY
        self.manifest = manifest
        self.tag_sha = SHA if tagged else None
        self.release = None
        self.assets = {}
        self.calls = []
        self.corrupt_upload = False

    def request(self, method, path, payload=None, data=None, content_type=None, upload=False):
        self.calls.append((method, path, payload, upload))
        base = '/repos/' + REPOSITORY
        if method == 'GET' and path.startswith(base + '/git/ref/tags/'):
            if self.tag_sha is None:
                raise release.GitHubError(404)
            return {'object': {'type': 'commit', 'sha': self.tag_sha}}
        if method == 'GET' and path.startswith(base + '/releases/tags/'):
            if self.release is None:
                raise release.GitHubError(404)
            return dict(self.release)
        if method == 'POST' and path == base + '/releases':
            self.release = {'id': 123, **payload}
            return dict(self.release)
        if method == 'GET' and path == base + '/releases/123/assets?per_page=100':
            return list(self.assets.values())
        if method == 'POST' and path.startswith(base + '/releases/123/assets?'):
            if not upload:
                raise AssertionError('Asset must use the fixed upload host')
            name = parse_qs(urlsplit(path).query)['name'][0]
            if name in self.assets:
                raise AssertionError('Existing asset was overwritten')
            checksum = '0' * 64 if self.corrupt_upload else hashlib.sha256(data).hexdigest()
            self.assets[name] = {'name': name, 'size': len(data),
                'state': 'uploaded', 'digest': 'sha256:' + checksum}
            return self.assets[name]
        if method == 'PATCH' and path == base + '/releases/123':
            if set(self.assets) != set(self.manifest['files']):
                raise AssertionError('Release was published before all uploads')
            self.release.update(payload)
            self.tag_sha = self.tag_sha or SHA
            return dict(self.release)
        raise AssertionError('Unexpected mocked API request: ' + method + ' ' + path)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='course-release-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        app = self.root / 'desktop-course/app/package.json'
        app.parent.mkdir(parents=True)
        app.write_text(json.dumps({'name': release.PACKAGE, 'version': '1.1.1'}))
        self.deb = self.root / 'desktop-course/release' / release.asset_names('1.1.1')[0]
        self.deb.parent.mkdir()
        self.deb.write_bytes(b'!<arch>\nfixture')
        self.make_zip(self.root / 'publish/cpp-backend-course.zip')
        self.make_zip(self.root / 'build/cpp-backend-course-local.zip')
        self.output = self.root / 'build/release-assets'
        self.source = patch.object(release, 'source_sha', return_value=SHA)
        self.source.start()
        self.addCleanup(self.source.stop)
        self.package = patch.object(release, 'check_package')
        self.package.start()
        self.addCleanup(self.package.stop)

    def make_zip(self, path, name='course/index.html'):
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr(name, b'<!doctype html><title>Fixture</title>')

    def prepare(self):
        return release.prepare(TAG, SHA, self.output, self.root)

    def publish(self, client, **overrides):
        arguments = dict(directory=self.output, repository=REPOSITORY, tag=TAG,
                         sha=SHA, client=client, root=self.root, env={})
        arguments.update(overrides)
        return release.publish(**arguments)

    def test_bundle_is_exactly_four_public_assets_with_consistent_hashes(self):
        manifest = self.prepare()
        self.assertEqual(set(manifest['files']), set(release.asset_names('1.1.1')) | {'SHA256SUMS'})
        loaded, payloads = release.read_bundle(self.output, TAG, SHA, self.root)
        self.assertEqual(loaded, manifest)
        self.assertEqual(len(payloads['SHA256SUMS'].decode().splitlines()), 3)
        self.assertEqual({p.name for p in self.output.iterdir()}, set(payloads) | {release.MANIFEST})
        for name, data in payloads.items():
            self.assertEqual(manifest['files'][name]['sha256'], hashlib.sha256(data).hexdigest())

    def test_wrong_version_source_or_output_refuses_without_overwrite(self):
        for tag, sha in [('desktop-v2.0.0', SHA), (TAG, 'short')]:
            with self.subTest(tag=tag, sha=sha), self.assertRaises(ValueError):
                release.prepare(tag, sha, self.output, self.root)
        self.assertFalse(self.output.exists())
        with patch.object(release, 'source_sha', return_value='b' * 40), self.assertRaises(ValueError):
            self.prepare()
        self.prepare()
        before = {p.name: p.read_bytes() for p in self.output.iterdir()}
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual({p.name: p.read_bytes() for p in self.output.iterdir()}, before)

    def test_unsafe_archive_or_symlink_input_is_refused(self):
        self.make_zip(self.root / 'publish/cpp-backend-course.zip', '../outside.txt')
        with self.assertRaisesRegex(ValueError, 'Unsafe path'):
            self.prepare()
        self.assertFalse(self.output.exists())
        self.make_zip(self.root / 'publish/cpp-backend-course.zip')
        self.deb.rename(self.deb.with_suffix('.fixture'))
        self.deb.symlink_to(self.deb.with_suffix('.fixture'))
        with self.assertRaisesRegex(ValueError, 'symbolic'):
            self.prepare()

    def test_tampered_or_extra_bundle_file_is_refused(self):
        self.prepare()
        first = self.output / release.asset_names('1.1.1')[0]
        first.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'differs'):
            release.read_bundle(self.output, TAG, SHA, self.root)
        first.write_bytes(self.deb.read_bytes())
        (self.output / 'unexpected.txt').write_text('fixture')
        with self.assertRaisesRegex(ValueError, 'Unexpected files'):
            release.read_bundle(self.output, TAG, SHA, self.root)

    def test_publish_keeps_draft_until_server_hashes_match(self):
        manifest = self.prepare()
        client = FakeGitHub(manifest)
        url = self.publish(client)
        self.assertEqual(url, 'https://github.com/' + REPOSITORY + '/releases/tag/' + TAG)
        creates = [payload for method, path, payload, _ in client.calls if method == 'POST' and path.endswith('/releases')]
        self.assertEqual(len(creates), 1)
        self.assertTrue(creates[0]['draft'])
        self.assertEqual(creates[0]['target_commitish'], SHA)
        self.assertFalse(client.release['draft'])
        self.assertEqual(len([call for call in client.calls if call[3]]), 4)
        patch_index = next(i for i, call in enumerate(client.calls) if call[0] == 'PATCH')
        self.assertTrue(all(i < patch_index for i, call in enumerate(client.calls) if call[3]))

    def test_corrupt_server_digest_never_publishes(self):
        client = FakeGitHub(self.prepare())
        client.corrupt_upload = True
        with self.assertRaisesRegex(ValueError, 'hash or size mismatch'):
            self.publish(client)
        self.assertTrue(client.release['draft'])
        self.assertFalse(any(call[0] == 'PATCH' for call in client.calls))

    def test_matching_published_release_is_a_read_only_noop(self):
        client = FakeGitHub(self.prepare())
        self.publish(client)
        client.calls.clear()
        self.publish(client)
        self.assertTrue(all(call[0] == 'GET' for call in client.calls))

    def test_partial_matching_draft_resumes_without_overwrite(self):
        manifest = self.prepare()
        client = FakeGitHub(manifest)
        client.release = {'id': 123, 'tag_name': TAG, 'draft': True,
            'body': release.release_body('1.1.1', SHA, REPOSITORY)}
        name, info = next(iter(manifest['files'].items()))
        client.assets[name] = {'name': name, 'state': 'uploaded',
                               'size': info['bytes'], 'digest': 'sha256:' + info['sha256']}
        self.publish(client)
        self.assertEqual(len([call for call in client.calls if call[3]]), 3)

    def test_existing_foreign_release_or_ref_is_never_overwritten(self):
        client = FakeGitHub(self.prepare())
        client.tag_sha = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'different source'):
            self.publish(client)
        self.assertFalse(any(call[0] == 'POST' for call in client.calls))
        client.tag_sha = SHA
        client.release = {'id': 123, 'tag_name': TAG, 'draft': False, 'body': 'Not our bundle'}
        with self.assertRaisesRegex(ValueError, 'not this source'):
            self.publish(client)
        self.assertFalse(any(call[0] in ('POST', 'PATCH') for call in client.calls))

    def test_manual_draft_can_create_tag_on_publication(self):
        client = FakeGitHub(self.prepare(), tagged=False)
        self.publish(client)
        self.assertEqual(client.tag_sha, SHA)
        self.assertFalse(client.release['draft'])

    def test_repository_environment_mismatch_is_refused_before_api(self):
        client = FakeGitHub(self.prepare())
        with self.assertRaisesRegex(ValueError, 'Actions repository'):
            self.publish(client, env={'GITHUB_REPOSITORY': 'someone/else'})
        self.assertEqual(client.calls, [])

    def test_metadata_accepts_validated_tag_or_manual_event_only(self):
        for event in ('push', 'workflow_dispatch'):
            output = self.root / (event + '.output')
            env = {'GITHUB_EVENT_NAME': event, 'GITHUB_REF': 'refs/tags/' + TAG,
                   'GITHUB_SHA': SHA, 'REQUESTED_RELEASE_TAG': TAG, 'GITHUB_OUTPUT': str(output)}
            result = release.ci_metadata(env, self.root)
            self.assertEqual(result, {'tag': TAG, 'version': '1.1.1', 'source_sha': SHA})
            self.assertEqual(len(output.read_text().splitlines()), 3)
        with self.assertRaises(ValueError):
            release.ci_metadata({'GITHUB_EVENT_NAME': 'pull_request'}, self.root)
        with self.assertRaises(ValueError):
            release.ci_metadata({'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/main'}, self.root)

    def test_package_identity_uses_version_and_architecture(self):
        with patch.object(release.subprocess, 'check_output', return_value='Package: cpp-backend-course-desktop\nVersion: 1.1.1\nArchitecture: amd64\n'):
            # Invoke the original function saved before the fixture mock.
            original_check_package(self.deb, '1.1.1')
        with patch.object(release.subprocess, 'check_output', return_value='Package: cpp-backend-course-desktop\nVersion: 1.1.0\nArchitecture: amd64\n'), self.assertRaises(ValueError):
            original_check_package(self.deb, '1.1.1')


original_check_package = release.check_package


class ApiAndWorkflowTests(unittest.TestCase):
    def test_api_origin_is_fixed_and_credentials_never_follow_redirects(self):
        opener = Mock()
        response = io.BytesIO(b'{"id": 1}')
        opener.open.return_value = response
        client = release.GitHub(REPOSITORY, 'fixture', opener=opener)
        client.request('POST', '/repos/' + REPOSITORY + '/releases', payload={'draft': True})
        request = opener.open.call_args.args[0]
        self.assertEqual(urlsplit(request.full_url).netloc, 'api.github.com')
        self.assertEqual(request.get_header('Authorization'), 'Bearer fixture')
        for path in ('https://other.invalid/', '/repos/else/repo/releases',
                     '/repos/' + REPOSITORY + '/../other', '/repos/' + REPOSITORY + '/%2e%2e/other'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                client.request('GET', path)
        self.assertIsNone(release.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid/'))

    def test_api_error_does_not_expose_response_body_or_token(self):
        opener = Mock()
        opener.open.side_effect = HTTPError('https://api.github.com/', 403, 'Denied', {}, io.BytesIO(b'private-response-fixture'))
        client = release.GitHub(REPOSITORY, 'fixture', opener=opener)
        with self.assertRaises(release.GitHubError) as caught:
            client.request('GET', '/repos/' + REPOSITORY + '/releases')
        self.assertEqual(str(caught.exception), 'GitHub API request failed with HTTP 403')
        self.assertNotIn('fixture', str(caught.exception))

    def test_workflow_has_pinned_actions_and_a_separate_write_job(self):
        workflow = (ROOT / '.github/workflows/release-desktop.yml').read_text()
        uses = re.findall(r'uses:\s*([^\s#]+)', workflow)
        self.assertEqual(len(uses), 4)
        self.assertTrue(all(re.fullmatch(r'actions/[a-z-]+@[0-9a-f]{40}', value) for value in uses))
        self.assertIn('permissions:\n  contents: read', workflow)
        self.assertIn('    permissions:\n      contents: write', workflow)
        self.assertIn('    needs: build', workflow)
        self.assertEqual(workflow.count('persist-credentials: false'), 2)
        self.assertNotIn('pull_request:', workflow)
        self.assertNotIn('sudo ', workflow)
        self.assertNotIn('--no-sandbox', workflow)


if __name__ == '__main__':
    unittest.main()
