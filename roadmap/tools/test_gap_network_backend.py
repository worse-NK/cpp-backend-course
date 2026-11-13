"""Content/compilation guards. Real server acceptance is verify.py, not a mock."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from build_stations import validate
from checkpoint_data import with_checkpoints
from test_cpp_editorial_audit import ProseParser

ROOT = Path(__file__).resolve().parents[1]
NEW = ['linux-name-resolution-path', 'split-dns-debug-workbook',
       'bounded-asio-server-contract', 'bounded-asio-server-lab']


class NetworkPracticeGaps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT/'content/station7.json').read_text())
        cls.sections = {s['id']:s for s in cls.data['theory']}

    def test_schema_and_independent_checkpoints(self):
        validate(self.data, ROOT/'content/station7.json')
        resolved = with_checkpoints(self.data)
        new_questions = [q for k,n in [('basic',53),('advanced',85),('interview',64)]
                         for q in self.data['quizzes'][k][n:]
                         if set(q['theoryRefs']) & set(NEW)]
        self.assertEqual(len(new_questions),10)
        stems = {q['q'].strip().casefold() for q in new_questions}
        for questions in resolved['checkpoints'].values():
            self.assertGreaterEqual(len(questions),5)
            for q in questions:
                if set(q['theoryRefs']) & set(NEW):
                    self.assertNotIn(q['q'].strip().casefold(),stems)

    def test_teaching_edges_sources_and_reveals(self):
        ids=list(self.sections)
        for a,b in [('dns-resolution','linux-name-resolution-path'),
                    ('linux-name-resolution-path','split-dns-debug-workbook'),
                    ('asio-cancellation-shutdown-proof','bounded-asio-server-contract'),
                    ('bounded-asio-server-contract','bounded-asio-server-lab')]:
            self.assertLess(ids.index(a),ids.index(b))
        for sid in NEW:
            section=self.sections[sid]
            self.assertTrue(any(b['type']=='self-check' for b in section['blocks']))
            self.assertTrue(any('https://' in b.get('html','') for b in section['blocks']))
            for b in section['blocks']:
                for field in ('html','prompt','answer'):
                    parser=ProseParser();parser.feed(b.get(field,''))
                    self.assertEqual(parser.unknown,[],(sid,field))

    def test_download_and_listing_are_identical(self):
        block=next(b for b in self.sections[NEW[0]]['blocks']
                   if b.get('exampleId')=='s7-resolver-candidates')
        self.assertEqual(block['standard'],'20/23')
        self.assertEqual(block['code'],(ROOT/'examples/bounded-asio/resolve.cpp').read_text())
        for name in ['server.cpp','CMakeLists.txt','verify.py','README.txt','resolve.cpp']:
            self.assertTrue((ROOT/'examples/bounded-asio'/name).is_file())

    def test_numeric_resolver_has_no_network_target(self):
        compiler=shutil.which('g++')
        self.assertIsNotNone(compiler,'Explicitly install/provide a compiler for this check')
        for edition in ('20','23'):
            with self.subTest(edition=edition),tempfile.TemporaryDirectory(prefix='course-resolver-') as tmp:
                binary=Path(tmp)/'resolve'
                built=subprocess.run([compiler,'-std=c++'+edition,'-Wall','-Wextra','-Wpedantic','-Werror',
                    str(ROOT/'examples/bounded-asio/resolve.cpp'),'-o',str(binary)],capture_output=True,text=True,timeout=30)
                self.assertEqual(built.returncode,0,built.stderr)
                run=subprocess.run([str(binary),'127.0.0.1'],capture_output=True,text=True,timeout=5)
                self.assertEqual(run.returncode,0,run.stderr)
                self.assertEqual(run.stdout,'IPv4 127.0.0.1 port=443\n')

    def test_server_contract_is_bounded_and_loopback_only(self):
        source=(ROOT/'examples/bounded-asio/server.cpp').read_text()
        for contract in ['max_payload = 65536','max_sessions = 16','make_address("127.0.0.1")',
                         'deadline_(Clock::now() + budget)','done_ = true;',
                         'if (Clock::now() >= deadline_)','auto pending = std::vector']:
            self.assertIn(contract,source)
        self.assertLess(source.index('length > max_payload'),source.index('body_.resize(length)'))
        self.assertNotIn('io.stop(',source)
        self.assertNotIn('0.0.0.0',source)
        # Read-only structural checks do not pretend the server has run.
        self.assertIn('finish deadline phase=write',(ROOT/'examples/bounded-asio/verify.py').read_text())


if __name__ == '__main__':unittest.main()
