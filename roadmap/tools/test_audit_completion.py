#!/usr/bin/env python3
"""Regressions for the October 5 completeness audit.

No data-race/invalid-lifetime examples are executed. Asio integration uses only
loopback. Optional dependencies are supplied, never installed by this test:
ROADMAP_BOOST_INCLUDE, ROADMAP_PROTOC, ROADMAP_PROTO_LIBDIR.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest

from test_expanded_examples import code, station
import test_remaining_examples


class CompletionExamples(unittest.TestCase):
    cpp = test_remaining_examples.RemainingExamples.cpp

    def publication(self):
        task = next(t for t in station(6)['tasks']
                    if t['title'] == 'Версия и конфигурация публикуются вместе')
        return ('#include <cstdint>\n#include <iostream>\n'
                'struct Config { int value; };\n'
                'void apply(std::uint64_t, const Config&);\n' + task['code'])

    def test_stop_before_consumer_start(self):
        self.cpp(self.publication() + '''
void apply(std::uint64_t, const Config&) { std::cout << "unexpected"; }
int main() { request_shutdown(); consume_updates();
    std::cout << "stopped " << publish(std::make_shared<const Config>(Config{7})); }
''', 'stopped 0', flags=('-pthread',))

    def test_initial_configuration_is_applied(self):
        self.cpp(self.publication() + '''
void apply(std::uint64_t version, const Config& c) {
    std::cout << version << ':' << c.value << ' '; request_shutdown();
}
int main() { publish(std::make_shared<const Config>(Config{7}));
    consume_updates(); std::cout << "done"; }
''', '1:7 done', flags=('-pthread',))

    def test_stop_between_apply_and_wait(self):
        self.cpp(self.publication() + '''
#include <thread>
std::atomic<int> stage{0};
void apply(std::uint64_t, const Config&) {
    stage.store(1); stage.notify_all();
    stage.wait(1); // main publishes STOP before allowing apply to return
}
int main() {
    publish(std::make_shared<const Config>(Config{7}));
    std::jthread worker(consume_updates);
    stage.wait(0);
    request_shutdown();
    stage.store(2); stage.notify_all();
    worker.join(); std::cout << "joined";
}
''', 'joined', flags=('-pthread',))

    def test_failed_stop_preparation_preserves_state(self):
        source = 'bool fail_stop = true;\n' + self.publication()
        source = source.replace('auto stop = std::make_shared<const PublishedConfig>(',
                                'if (fail_stop) throw std::bad_alloc();\n'
                                '    auto stop = std::make_shared<const PublishedConfig>(')
        self.cpp(source + '''
void apply(std::uint64_t, const Config&) {}
int main() {
    publish(std::make_shared<const Config>(Config{7}));
    try { request_shutdown(); } catch (const std::bad_alloc&) {}
    std::cout << accepting_updates << ' ' << next_version << ' ';
    std::cout << publish(std::make_shared<const Config>(Config{8})) << ' ';
    fail_stop = false; request_shutdown(); consume_updates();
    std::cout << next_version;
}
''', '1 1 1 3', flags=('-pthread',))

    def test_snapshot_owners_and_two_writers(self):
        source = code(6, 'snapshot-container-workbook')
        source = source.replace('struct Model { int id; /* большие неизменяемые данные */ };',
                                'struct Model { int id; explicit Model(int x):id(x){} '
                                'Model(const Model&) = delete; };')
        self.cpp(source + '''
#include <iostream>
#include <thread>
int main() {
    Catalog c;
    c.append(std::make_shared<const Model>(1));
    auto old = c.read();
    { std::jthread a([&]{for(int i=0;i<50;++i)c.append(std::make_shared<const Model>(2));});
      std::jthread b([&]{for(int i=0;i<50;++i)c.append(std::make_shared<const Model>(3));}); }
    auto now = c.read();
    std::cout << old->size() << ' ' << now->size() << ' '
              << ((*old)[0] == (*now)[0]);
}
''', '1 101 1', flags=('-pthread',))

    def test_release_sequence_three_threads(self):
        # Execute only the correct RMW variant; the store variant has a data race.
        self.cpp('''
#include <atomic>
#include <thread>
#include <iostream>
int main() {
 int payload=0, observed=0; std::atomic<int> phase{0};
 std::jthread a([&]{payload=42;phase.store(1,std::memory_order_release);});
 std::jthread b([&]{while(phase.load(std::memory_order_relaxed)!=1){}
                    phase.fetch_add(1,std::memory_order_relaxed);});
 std::jthread c([&]{while(phase.load(std::memory_order_acquire)!=2){}
                    observed=payload;});
 a.join();b.join();c.join();std::cout<<observed;
}
''', '42', flags=('-pthread',))

    def test_bit_count_full_width(self):
        self.cpp(code(3, 'bit-mask-workbook') + '''
#include <iostream>
int main() {
 for(std::uint64_t x=0;x<10000;++x)
  if(count_bits(x)!=std::popcount(x)||count_by_clearing(x)!=std::popcount(x)) return 1;
 auto high=std::uint64_t{1}<<63;
 std::cout<<count_bits(high)<<' '<<count_by_clearing(~std::uint64_t{0});
}
''', '1 64')

    def test_subtree_sets_not_shapes(self):
        self.cpp(code(3, 'subtree-sets-workbook') + '''
#include <iostream>
int main() {
 LetterNode b{'B'}, a{'A'}, ab{'A', &b}, ba{'B', &a}, root{'C', &ab, &ba};
 auto pair=equivalent_subtrees(&root);
 std::cout<<(pair && pair->first==&ab && pair->second==&ba)<<' '
          <<equivalent_subtrees(nullptr).has_value()<<' '
          <<equivalent_subtrees(&a).has_value()<<' ';
 LetterNode bad{'?'};
 try {equivalent_subtrees(&bad);} catch(const std::invalid_argument&) {std::cout<<"invalid";}
}
''', '1 0 0 invalid')

    def test_graph_cycle_identity_and_null(self):
        self.cpp(code(3, 'graph-copy-workbook') + '''
#include <iostream>
int main(){GraphNode a{7},b{7};a.left=&b;a.right=&b;b.left=&a;
 auto out=clone_graph(&a);
 std::cout<<out.nodes.size()<<' '<<(out.root!=&a)<<' '
  <<(out.root->left==out.root->right)<<' '<<(out.root->left->left==out.root)<<' '
  <<clone_graph(nullptr).nodes.size();
}
''', '2 1 1 1 0')

    def test_rle_exhaustive_small_inputs(self):
        self.cpp(code(3, 'rle-workbook') + '''
#include <iostream>
std::string reference(const std::string& s){
 std::string result;
 for(std::size_t i=0;i<s.size();){auto j=i+1;while(j<s.size()&&s[j]==s[i])++j;
  result+=s[i];if(j-i>1)result+=std::to_string(j-i);i=j;}return result;
}
int main(){
 for(int n=0;n<=10;++n)for(int mask=0;mask<(1<<n);++mask){
  std::string s;for(int i=0;i<n;++i)s+=(mask&(1<<i))?'A':'B';
  auto expected=reference(s);if(!compress_rle(s)||s!=expected)return 1;
 }
 for(int n:{1,2,9,10,12,99,100,1000}){std::string s(n,'A');
  auto expected=reference(s);if(!compress_rle(s)||s!=expected)return 2;}
 std::string invalid="AB1", sample="AAABBCCCCD";
 std::cout<<compress_rle(invalid)<<' '<<invalid<<' ';
 compress_rle(sample);std::cout<<sample;
}
''', '0 AB1 A3B2C4D')

    def test_openapi_operation_and_schema_cases(self):
        import yaml
        from jsonschema import Draft202012Validator
        document = yaml.safe_load(code(8, 'openapi-operation-workbook'))
        operation = document['paths']['/tasks']['post']
        self.assertEqual(document['openapi'], '3.1.1')
        self.assertEqual(operation['security'], [{'bearerAuth': []}])
        self.assertTrue(operation['requestBody']['required'])
        self.assertIn('Location', operation['responses']['201']['headers'])
        self.assertIn('WWW-Authenticate', operation['responses']['401']['headers'])
        schema = document['components']['schemas']['CreateTask']
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for payload, valid in (({'title':'Review'},True),({},False),
                              ({'title':None},False),({'title':''},False),
                              ({'title':'Review','owner':'admin'},False)):
            self.assertEqual(validator.is_valid(payload), valid, payload)
        self.assertTrue(validator.is_valid({'title':'Я'*150}))
        self.assertGreater(len(('Я'*150).encode('utf-8')), 200)
        def check_refs(value):
            if isinstance(value,dict):
                if '$ref' in value:
                    node=document
                    for part in value['$ref'].removeprefix('#/').split('/'): node=node[part]
                for child in value.values():check_refs(child)
            elif isinstance(value,list):
                for child in value:check_refs(child)
        check_refs(document)

    @unittest.skipUnless(os.environ.get('ROADMAP_PROTOC'), 'set ROADMAP_PROTOC')
    def test_proto_contract_compiles(self):
        with tempfile.TemporaryDirectory(prefix='roadmap-proto-audit-') as directory:
            path=Path(directory)/'task.proto'
            path.write_text(code(8,'grpc-call-workbook'))
            env=os.environ.copy()
            if os.environ.get('ROADMAP_PROTO_LIBDIR'):
                env['LD_LIBRARY_PATH']=os.environ['ROADMAP_PROTO_LIBDIR']
            result=subprocess.run([os.environ['ROADMAP_PROTOC'],f'-I{directory}',
                f'--descriptor_set_out={directory}/task.pb',str(path)],
                env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertGreater((Path(directory)/'task.pb').stat().st_size,0)

    def test_new_theory_has_practice_links(self):
        refs={3:['bit-mask-workbook','subtree-sets-workbook','graph-copy-workbook','rle-workbook'],
              5:['diagnostic-cases-workbook','profile-comparison-workbook'],
              6:['wait-state-workbook','memory-observation-workbook','snapshot-container-workbook','cache-coherence-workbook'],
              7:['dns-records-workbook','asio-client-workbook','tls-capture-workbook'],
              8:['identity-lifecycle-workbook','openapi-operation-workbook','grpc-call-workbook']}
        for number,sections in refs.items():
            data=station(number)
            for ref in sections:
                questions=[q for qs in data['quizzes'].values() for q in qs if ref in q['theoryRefs']]
                self.assertGreaterEqual(len(questions),2,ref)
                theory=next(s for s in data['theory'] if s['id']==ref)
                self.assertTrue(any('Первоисточник' in b.get('html','') for b in theory['blocks']),ref)


@unittest.skipUnless(os.environ.get('ROADMAP_BOOST_INCLUDE'), 'set ROADMAP_BOOST_INCLUDE')
class AsioClientIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=tempfile.TemporaryDirectory(prefix='roadmap-asio-audit-')
        cls.addClassCleanup(cls.directory.cleanup)
        cls.binary=str(Path(cls.directory.name)/'client')
        result=subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-pthread',
                '-DBOOST_ERROR_CODE_HEADER_ONLY','-I'+os.environ['ROADMAP_BOOST_INCLUDE'],
                '-x','c++','-','-o',cls.binary],input=code(7,'asio-client-workbook'),
                text=True,capture_output=True,timeout=90)
        if result.returncode:raise AssertionError(result.stderr)

    def exchange(self, chunks, expected_exit, expected_output):
        errors=[]
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(6)
            def serve():
                try:
                    conn,_=listener.accept()
                    with conn:
                        conn.settimeout(5)
                        request=b''
                        while not request.endswith(b'\n') and len(request)<100:
                            part=conn.recv(1)
                            if not part:break
                            request+=part
                        if request!=b'PING\n':raise AssertionError(request)
                        if chunks is None:
                            if conn.recv(1)!=b'':raise AssertionError('expected close on timeout')
                        else:
                            for chunk in chunks:conn.sendall(chunk)
                except BaseException as error:errors.append(error)
            thread=threading.Thread(target=serve,daemon=True);thread.start()
            try:
                result=subprocess.run([self.binary,'127.0.0.1',str(listener.getsockname()[1])],
                                      capture_output=True,text=True,timeout=7)
            finally:thread.join(timeout=7)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors,errors)
        self.assertEqual(result.returncode,expected_exit,result.stderr)
        self.assertEqual(result.stdout,expected_output)

    def test_reply_and_extra_bytes(self):self.exchange([b'PO',b'NG\nEXTRA\n'],0,'PONG\n')
    def test_eof_without_delimiter(self):self.exchange([b'PONG'],1,'')
    def test_input_limit(self):self.exchange([b'A'*4096],1,'')
    def test_deadline_closes_socket(self):self.exchange(None,1,'')


if __name__=='__main__':unittest.main()
