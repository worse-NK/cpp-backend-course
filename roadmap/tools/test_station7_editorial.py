"""Editorial invariants and bounded offline checks for station 7.

These tests do not contact a network, reconfigure a host, or execute the
deliberately dangling Asio example. Execution supplements primary-source
review; it is not a portability or performance proof.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_cpp_editorial_audit import ProseParser

ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False,
                                    sort_keys=True).encode()).hexdigest()


class StationSevenEditorial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / 'content/station7.json').read_text())
        cls.sections = {s['id']: s for s in cls.data['theory']}

    def prose(self, sid):
        return '\n'.join(b.get('html', '') + b.get('prompt', '') +
                         b.get('answer', '') for b in self.sections[sid]['blocks'])

    def cpp(self, source, expected=None):
        compiler = shutil.which('g++')
        if not compiler:
            self.skipTest('g++ unavailable: source checks still run')
        with tempfile.TemporaryDirectory(prefix='station7-editorial-') as folder:
            executable = str(Path(folder) / 'example')
            command = [compiler, '-std=c++20', '-O1', '-Wall', '-Wextra',
                       '-Werror', '-pedantic', '-x', 'c++', '-']
            command += ['-fsyntax-only'] if expected is None else ['-o', executable]
            built = subprocess.run(command, input=source, text=True,
                                   capture_output=True, timeout=45)
            self.assertEqual(built.returncode, 0, built.stderr)
            if expected is not None:
                ran = subprocess.run([executable], text=True, capture_output=True,
                                     timeout=5)
                self.assertEqual(ran.returncode, 0, ran.stderr)
                self.assertEqual(ran.stdout.strip(), expected)

    def complete_parser(self):
        codes = [b['code'] for b in self.sections['framing-final-workbook']['blocks']
                 if b['type'] == 'code' and '#include <array>' in b['code']]
        self.assertEqual(len(codes), 1)
        return codes[0]

    def test_section_addresses_and_progress_are_preserved(self):
        self.assertEqual(len(self.sections), 101)
        self.assertEqual(self.data['meta']['storeKey'], 'cpp_station7_progress_v1')
        self.assertEqual(digest([(x['id'], x.get('substation')) for x in
                                 self.data['theory']]),
                         '90a7a08fc713cd209a19cf890698784695e72ec27c830c61def2808cc454f8c9')

    def test_original_code_and_visual_payloads_are_preserved(self):
        # Deliberate source/diagram changes require reviewing these baselines.
        codes = [(s['id'], [b['code'] for b in s['blocks'] if b['type'] == 'code'])
                 for s in self.data['theory']]
        visual = [(s['id'], [b for b in s['blocks'] if b['type'] not in
                            ('code', 'text', 'note', 'self-check')])
                  for s in self.data['theory']]
        self.assertEqual(digest(codes),
                         'af7301ec538541eb073abbdbb384e63b1425ae75af1c05e916a8a6a5fce70f18')
        self.assertEqual(digest(visual),
                         'd7eeae404c9e70396dd5d790d07a14c91e0c131f939de43dc420fafa56afb41f')

    def test_each_section_has_explained_retrieval_check_and_valid_html(self):
        count = 0
        for s in self.sections.values():
            checks = [b for b in s['blocks'] if b['type'] == 'self-check']
            self.assertTrue(checks, s['id'])
            count += len(checks)
            for b in s['blocks']:
                for field in ('html', 'prompt', 'answer'):
                    if field not in b:
                        continue
                    parser = ProseParser()
                    parser.feed(b[field])
                    self.assertEqual(parser.unknown, [], (s['id'], field))
            for b in checks:
                self.assertGreater(len(b['prompt']), 30, s['id'])
                self.assertGreater(len(b['answer']), 50, s['id'])
        self.assertGreaterEqual(count, 150)

    def test_each_module_ends_with_its_checkpoint(self):
        modules = {}
        for s in self.data['theory']:
            modules[s['substation']] = s
        self.assertEqual(len(modules), 9)
        for module, s in modules.items():
            final = s['blocks'][-1]
            self.assertEqual(final['type'], 'note', module)
            self.assertIn('Контрольная точка', final['html'], module)

    def test_versioned_sources_and_api_boundaries_remain_explicit(self):
        all_prose = '\n'.join(self.prose(sid) for sid in self.sections)
        self.assertNotIn('/doc/libs/latest/', all_prose)
        self.assertNotIn('eel.is/c++draft', all_prose)
        self.assertIn('/1_85_0/', all_prose)
        self.assertIn('rfc9846.html', self.prose('tls13-handshake'))
        self.assertIn('Internet-Draft', self.prose('http-cookies'))
        for term in ('body_limit', 'gzip', 'всю память'):
            self.assertIn(term, self.prose('beast-http-server'))
        self.assertIn('MORE', self.prose('event-loop-scaling-and-completion'))
        self.assertIn('необработан', self.prose('http2-http3-deep'))

    def test_complete_offline_frame_program(self):
        self.cpp(self.complete_parser(),
                 'frame: [ABC]\nframe: [Z]\nclean EOF\ntruncated frame')

    def test_all_chunk_partitions_and_empty_message(self):
        base = self.complete_parser().split('void feed(')[0]
        self.cpp(base + r'''
#include <cassert>
#include <vector>
int main() {
    const std::string wire("\x00\x03" "ABC\x00\x01" "Z\x00\x00", 10);
    const std::vector<std::string> expected{"ABC", "Z", ""};
    unsigned partitions = 0;
    for (unsigned mask = 0; mask < (1u << 9); ++mask) {
        FrameParser parser;
        std::vector<std::string> messages;
        std::size_t start = 0;
        auto chunk = [&](std::size_t end) {
            for (std::size_t i = start; i < end; ++i) {
                auto msg = parser.push(static_cast<unsigned char>(wire[i]));
                if (msg) messages.push_back(std::move(*msg));
            }
            start = end;
        };
        for (unsigned boundary = 0; boundary < 9; ++boundary)
            if (mask & (1u << boundary)) chunk(boundary + 1);
        chunk(wire.size());
        parser.finish();
        assert(messages == expected);
        ++partitions;
    }
    std::cout << partitions << " partitions OK";
}
''', '512 partitions OK')

    def test_parser_rejects_invalid_length_and_truncation(self):
        base = self.complete_parser().split('void feed(')[0]
        self.cpp(base + r'''
#include <cassert>
int main() {
    FrameParser bad;
    assert(!bad.push(0));
    try { (void)bad.push(9); assert(false); }
    catch (const std::runtime_error& e) {
        assert(std::string(e.what()) == "frame too large");
    }
    try { (void)bad.push(0); assert(false); }
    catch (const std::runtime_error& e) {
        assert(std::string(e.what()) == "parser failed");
    }
    FrameParser header;
    assert(!header.push(0));
    try { header.finish(); assert(false); }
    catch (const std::runtime_error& e) {
        assert(std::string(e.what()) == "truncated frame");
    }
    FrameParser body;
    assert(!body.push(0)); assert(!body.push(2)); assert(!body.push('A'));
    try { body.finish(); assert(false); }
    catch (const std::runtime_error& e) {
        assert(std::string(e.what()) == "truncated frame");
    }
    FrameParser maximum;
    assert(!maximum.push(0)); assert(!maximum.push(8));
    for (int i = 0; i < 7; ++i) assert(!maximum.push(0xff));
    auto msg = maximum.push(0xff);
    assert(msg && msg->size() == 8); maximum.finish();
    std::cout << "limits OK";
}
''', 'limits OK')

    def test_multicast_example_is_syntax_checked_not_network_executed(self):
        source = (ROOT / 'examples/interview_gaps/multicast.cpp').read_text()
        section = self.sections['multicast-socket-lab']
        self.assertIn(source, [b['code'] for b in section['blocks']
                               if b['type'] == 'code'])
        self.cpp(source)


if __name__ == '__main__':
    unittest.main()
