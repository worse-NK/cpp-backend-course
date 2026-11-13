"""Offline/content checks; optional owned loopback HTTP test without the OTel SDK.

No Docker daemon, Collector, Prometheus, Grafana or Jaeger is contacted. Passing
the SDK-header test checks C++ API compatibility, not linking or OTLP delivery.
Set COURSE_HTTP_HEADER and COURSE_OTEL_SOURCE to local, already fetched sources.
"""
from collections import Counter
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock
import urllib.error
import urllib.request

from build_stations import validate
from checkpoint_data import normalize_prompt, with_checkpoints
from test_linux_systems import Fragment, fields

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'content/station14.json'
EXAMPLES=ROOT/'examples/station14'
FILES={'metrics.hpp','metrics_model.cpp','app.cpp','CMakeLists.txt','Dockerfile',
       'compose.yaml','collector.yaml','prometheus.yaml','alerts.yaml',
       'datasource.yaml','dashboards.yaml','dashboard.json','lab.py','README.txt',
       '.dockerignore','.gitignore'}
EXPECTED='''# TYPE course_requests_total counter
course_requests_total{outcome="ok"} 4
course_requests_total{outcome="error"} 1
# TYPE course_good_requests_total counter
course_good_requests_total 3
# TYPE course_inflight gauge
course_inflight 0
# TYPE course_request_duration_seconds histogram
course_request_duration_seconds_bucket{le="0.1"} 2
course_request_duration_seconds_bucket{le="0.3"} 4
course_request_duration_seconds_bucket{le="1"} 5
course_request_duration_seconds_bucket{le="+Inf"} 5
course_request_duration_seconds_sum 1.370000
course_request_duration_seconds_count 5
'''


def helper():
    spec=importlib.util.spec_from_file_location('observe_lab14',EXAMPLES/'lab.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ObservabilityContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads(SOURCE.read_text())
        cls.resolved=with_checkpoints(cls.data)
        cls.sections={s['id']:s for s in cls.data['theory']}

    def test_schema_counts_and_independent_checks(self):
        validate(self.data,SOURCE)
        self.assertEqual((30,7,9),(len(self.sections),len(self.data['substations']),len(self.data['tasks'])))
        self.assertEqual({'basic':28,'advanced':21,'interview':14},
                         {k:len(v) for k,v in self.data['quizzes'].items()})
        self.assertEqual({5},{len(v) for v in self.resolved['checkpoints'].values()})
        questions=[q for bank in self.data['quizzes'].values() for q in bank]
        questions += [q for cp in self.resolved['checkpoints'].values() for q in cp]
        prompts=[normalize_prompt(q['q']) for q in questions]
        self.assertEqual(98,len(set(prompts)))
        order={s['id']:i for i,s in enumerate(self.data['substations'])}
        for q in questions:
            for ref in q['theoryRefs']:
                self.assertLessEqual(order[self.sections[ref]['substation']],order[q['substation']])
            self.assertEqual(len(q['options']),len(set(q['options'])))
        for bank in self.data['quizzes'].values():
            self.assertEqual({0,1,2,3},set(Counter(q['answer'] for q in bank)))

    def test_html_selfchecks_and_final_markers(self):
        for section in self.data['theory']:
            checks=[b for b in section['blocks'] if b['type']=='self-check']
            self.assertEqual(1,len(checks),section['id'])
            self.assertGreater(len(checks[0]['answer']),120,section['id'])
        for field in ('html','answer','prompt'):
            for html in fields(self.data['theory'],field):
                parsed=Fragment(html)
                self.assertFalse(parsed.errors,(field,parsed.errors))
                self.assertFalse(parsed.stack,(field,parsed.stack))
        for group in self.data['substations']:
            last=[s for s in self.data['theory'] if s['substation']==group['id']][-1]
            self.assertIn('Контрольная точка',last['blocks'][-1]['html'])

    def test_workbook_is_complete_and_exactly_matches_downloads(self):
        combined=(EXAMPLES/'metrics.hpp').read_text().replace('#pragma once\n','')
        combined+='\n'+(EXAMPLES/'metrics_model.cpp').read_text().replace('#include "metrics.hpp"\n','')
        workbook=self.sections['observability-final-workbook']
        blocks=[b['code'] for b in workbook['blocks'] if b['type']=='code']
        self.assertIn(combined,blocks)
        self.assertTrue(any(EXPECTED.rstrip() in b for b in blocks))
        self.assertEqual(FILES,{p.name for p in EXAMPLES.iterdir() if p.is_file()})
        links={link for html in fields(self.data['theory'],'html')
               for link in Fragment(html).links if link and link.startswith('examples/station14/')}
        self.assertEqual({'examples/station14/'+p for p in FILES},links)

    def test_units_and_arithmetic(self):
        self.assertAlmostEqual((97*20+3*1200)/100,55.4)
        self.assertEqual(1008,6*3*8*7)
        self.assertEqual(2016000,1008*2000)
        self.assertEqual(240,240000*.001)
        self.assertAlmostEqual(.006/.001,6)
        self.assertAlmostEqual(14.4/(30*24),.02)
        self.assertAlmostEqual((90+990)/(100+1000),1080/1100)
        self.assertEqual(16800,40*1.5*280)

    def test_lab_configuration_contract(self):
        compose=(EXAMPLES/'compose.yaml').read_text()
        for image in ('prom/prometheus:v3.15.1','grafana/grafana:13.3.0',
                      'otel/opentelemetry-collector-contrib:0.164.0',
                      'cr.jaegertracing.io/jaegertracing/jaeger:2.22.0'):
            self.assertIn(image,compose)
        self.assertNotIn('privileged:',compose)
        self.assertNotIn('/var/run/docker.sock',compose)
        for line in compose.splitlines():
            if re.search(r'- ["\']?\d+\.\d+\.\d+\.\d+:',line):
                self.assertIn('127.0.0.1:',line)
        collector=(EXAMPLES/'collector.yaml').read_text()
        self.assertIn('memory_limiter:',collector)
        self.assertIn('queue_size: 256',collector)
        self.assertIn('max_elapsed_time: 10s',collector)
        self.assertIn('otlp_grpc/jaeger',collector)
        self.assertNotIn('debug:',collector)
        dashboard=json.loads((EXAMPLES/'dashboard.json').read_text())
        self.assertEqual(4,len(dashboard['panels']))
        expressions=' '.join(t['expr'] for p in dashboard['panels'] for t in p['targets'])
        self.assertIn('sum by (le) (rate(',expressions)


class LocalHelper(unittest.TestCase):
    def test_exclusive_secret_init_and_permissions(self):
        m=helper()
        with tempfile.TemporaryDirectory(prefix='course14-config-') as directory:
            with patch.object(m,'ROOT',Path(directory)),patch('sys.argv',['lab.py','init']):
                m.main()
                values=m.config()
                self.assertRegex(values['COMPOSE_PROJECT_NAME'],r'^course-station14-[a-f0-9]{12}$')
                self.assertEqual(0o600,stat.S_IMODE((m.ROOT/'.env').stat().st_mode))
                before=(m.ROOT/'.env').read_bytes()
                with self.assertRaises(FileExistsError):m.main()
                self.assertEqual(before,(m.ROOT/'.env').read_bytes())

    def test_refuses_unrelated_or_symlink_configuration(self):
        m=helper()
        with tempfile.TemporaryDirectory(prefix='course14-foreign-') as directory:
            root=Path(directory)
            foreign=root/'foreign'
            foreign.write_text('COMPOSE_PROJECT_NAME=work\n')
            with patch.object(m,'ROOT',root):
                (root/'.env').symlink_to(foreign)
                with self.assertRaises(SystemExit):m.config()
                (root/'.env').unlink()
                (root/'.env').write_text('COURSE_LAB_ID=0123456789ab\nCOMPOSE_PROJECT_NAME=work\n')
                with self.assertRaises(SystemExit):m.config()
                self.assertEqual('COMPOSE_PROJECT_NAME=work\n',foreign.read_text())

    def test_refuses_remote_context_and_foreign_ownership_before_mutation(self):
        m=helper()
        with patch.dict(os.environ,{'DOCKER_HOST':'ssh://unrelated'}):
            with patch.object(m,'docker',side_effect=AssertionError('must reject before Docker')):
                with self.assertRaises(SystemExit):m.local_engine()
        with patch.dict(os.environ,{},clear=True):
            with patch.object(m,'docker',return_value='[{"Endpoints":{"docker":{"Host":"tcp://remote:2375"}}}]'):
                with self.assertRaises(SystemExit):m.local_engine()
        with patch.object(m,'docker',side_effect=['foreign-id','[{"Config":{"Labels":{}}}]']) as commands:
            with self.assertRaises(SystemExit):m.owned({'COMPOSE_PROJECT_NAME':'course-station14-0123456789ab','COURSE_LAB_ID':'0123456789ab'})
            self.assertEqual(2,commands.call_count)
            self.assertTrue(all(c.args[0] in ('ps','inspect') for c in commands.call_args_list))

    def test_compose_configuration_without_engine(self):
        if not shutil.which('docker'):self.skipTest('Docker CLI absent; no daemon is required')
        values={'COMPOSE_PROJECT_NAME':'course-station14-0123456789ab',
                'COURSE_LAB_ID':'0123456789ab','COURSE_GRAFANA_PASSWORD':'A'*40}
        with patch.dict(os.environ,{'COURSE_LAB_ID':'ffffffffffff','COURSE_GRAFANA_PASSWORD':'foreign','COMPOSE_PROJECT_NAME':'work'}):
            environment=helper().compose_environment(values)
        result=subprocess.run(['docker','compose','config','--format','json'],cwd=EXAMPLES,
            env=environment,
            capture_output=True,text=True,timeout=30)
        self.assertEqual(0,result.returncode,result.stderr)
        data=json.loads(result.stdout)
        self.assertEqual({'api','worker','collector','jaeger','prometheus','grafana'},set(data['services']))
        for service in data['services'].values():
            for port in service.get('ports',[]):self.assertEqual('127.0.0.1',port['host_ip'])
            self.assertEqual('14',service['labels']['org.cpp-course.station'])
            self.assertEqual('0123456789ab',service['labels']['org.cpp-course.run'])
        self.assertEqual('A'*40,data['services']['grafana']['environment']['GF_SECURITY_ADMIN_PASSWORD'])
        self.assertEqual('0123456789ab',data['services']['api']['environment']['COURSE_LAB_ID'])
        self.assertEqual('0123456789ab',data['networks']['default']['labels']['org.cpp-course.run'])

    def test_refuses_foreign_network_before_mutation(self):
        m=helper()
        with patch.object(m,'docker',side_effect=['','','network-id','[{"Labels":{}}]']) as calls:
            with self.assertRaises(SystemExit):
                m.owned({'COMPOSE_PROJECT_NAME':'course-station14-0123456789ab','COURSE_LAB_ID':'0123456789ab'},'unix:///lab.sock')
            self.assertEqual(('network','inspect','network-id'),calls.call_args.args)
            self.assertTrue(all(c.kwargs['endpoint']=='unix:///lab.sock' for c in calls.call_args_list))

    def test_start_pins_validated_project_environment_and_endpoint(self):
        m=helper()
        values={'COMPOSE_PROJECT_NAME':'course-station14-0123456789ab',
                'COURSE_LAB_ID':'0123456789ab','COURSE_GRAFANA_PASSWORD':'A'*40}
        with patch.object(m,'config',return_value=values),patch.object(m,'local_engine',return_value='unix:///owned.sock'),patch.object(m,'owned'),patch.object(m.subprocess,'run') as run,patch('sys.argv',['lab.py','start']),patch.dict(os.environ,{'COURSE_LAB_ID':'ffffffffffff','COURSE_GRAFANA_PASSWORD':'wrong'}):
            m.main()
            command=run.call_args.args[0]
            self.assertEqual(['docker','--host','unix:///owned.sock','compose'],command[:4])
            self.assertEqual(values['COMPOSE_PROJECT_NAME'],command[command.index('--project-name')+1])
            for key,value in values.items():self.assertEqual(value,run.call_args.kwargs['env'][key])

    def test_http_guard_requires_this_run_before_body_read(self):
        m=helper();response=MagicMock()
        response.__enter__.return_value=response
        response.headers={'X-Course-Lab':'station14','X-Course-Lab-Run':'ffffffffffff'}
        with patch.object(m.urllib.request,'build_opener') as factory:
            factory.return_value.open.return_value=response
            with self.assertRaises(SystemExit):m.request('/healthz','0123456789ab')
            response.read.assert_not_called()
            self.assertEqual('http://127.0.0.1:18140/healthz',factory.return_value.open.call_args.args[0])


class CppModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler=shutil.which('g++')
        if not cls.compiler:raise unittest.SkipTest('g++ absent')

    def compile(self,source,output,*flags):
        result=subprocess.run([self.compiler,'-std=c++20','-Wall','-Wextra','-Wpedantic',
            '-Werror','-pthread','-I'+str(EXAMPLES),*flags,str(source),'-o',str(output)],
            capture_output=True,text=True,timeout=120)
        self.assertEqual(0,result.returncode,result.stderr)

    def test_complete_model_and_console(self):
        with tempfile.TemporaryDirectory(prefix='course14-model-') as directory:
            binary=Path(directory)/'model'
            self.compile(EXAMPLES/'metrics_model.cpp',binary)
            result=subprocess.run([binary],capture_output=True,text=True,timeout=10)
            self.assertEqual((0,EXPECTED),(result.returncode,result.stdout))

    def test_invalid_inputs_and_concurrent_snapshots(self):
        # This fixture tests the defined model, not performance or lock-freedom.
        code=r'''#include "metrics.hpp"
#include <cassert>
#include <limits>
#include <thread>
#include <vector>
int main(){
 Metrics m; m.enter(); const auto before=m.exposition();
 for(double bad:{-1.0,std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()}){
  try {m.complete(bad,true);assert(false);}catch(const std::invalid_argument&){}
  assert(m.exposition()==before);
 }
 m.complete(0,true); const auto after=m.exposition();
 try {m.complete(.1,true);assert(false);}catch(const std::logic_error&){}
 assert(m.exposition()==after);
 std::vector<std::thread> workers;
 for(int i=0;i<4;++i)workers.emplace_back([&]{for(int j=0;j<100;++j){m.enter();m.complete(.05,true);}});
 for(int i=0;i<100;++i){const auto text=m.exposition();assert(text.find("# TYPE course_inflight gauge")!=std::string::npos);}
 for(auto& t:workers)t.join();
 const auto text=m.exposition();
 assert(text.find("course_inflight 0\n")!=std::string::npos);
 assert(text.find("course_request_duration_seconds_count 401\n")!=std::string::npos);
 assert(text.find("course_good_requests_total 401\n")!=std::string::npos);
}
'''
        with tempfile.TemporaryDirectory(prefix='course14-boundaries-') as directory:
            path=Path(directory)/'boundaries.cpp';path.write_text(code)
            binary=Path(directory)/'boundaries';self.compile(path,binary)
            result=subprocess.run([binary],capture_output=True,text=True,timeout=10)
            self.assertEqual(0,result.returncode,result.stderr)

    def test_real_sdk_headers_syntax_only(self):
        header=Path(os.environ.get('COURSE_HTTP_HEADER','/nonexistent/httplib.h'))
        sdk=Path(os.environ.get('COURSE_OTEL_SOURCE','/nonexistent/otel'))
        if not header.is_file() or not (sdk/'api/include').is_dir():
            self.skipTest('Set cached COURSE_HTTP_HEADER and COURSE_OTEL_SOURCE; no downloads in tests')
        result=subprocess.run([self.compiler,'-std=c++20','-Wall','-Wextra','-Wpedantic',
            '-Werror','-pthread','-DCOURSE_WITH_OTEL=1','-fsyntax-only','-I'+str(header.parent),
            *['-I'+str(sdk/p) for p in ('api/include','sdk/include','exporters/otlp/include','ext/include')],
            str(EXAMPLES/'app.cpp')],capture_output=True,text=True,timeout=120)
        self.assertEqual(0,result.returncode,result.stderr)

    def test_owned_http_pair_without_sdk(self):
        header=Path(os.environ.get('COURSE_HTTP_HEADER','/nonexistent/httplib.h'))
        if not header.is_file():self.skipTest('Set cached COURSE_HTTP_HEADER; no dependency download')
        try:
            sockets=[socket.socket() for _ in range(2)]
            for sock in sockets:sock.bind(('127.0.0.1',0))
            ports=[sock.getsockname()[1] for sock in sockets]
        except PermissionError:
            self.skipTest('Sandbox disallows owned loopback listeners')
        finally:
            for sock in locals().get('sockets',[]):sock.close()
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with tempfile.TemporaryDirectory(prefix='course14-http-') as directory:
            binary=Path(directory)/'app'
            self.compile(EXAMPLES/'app.cpp',binary,'-I'+str(header.parent))
            invalid=subprocess.run([binary],env={**os.environ,'COURSE_PORT':'8080junk'},timeout=10)
            self.assertEqual(2,invalid.returncode)
            children=[]
            try:
                for role,port in zip(('worker','api'),ports):
                    children.append(subprocess.Popen([binary],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        text=True,env={**os.environ,'COURSE_ROLE':role,'COURSE_PORT':str(port),
                            'COURSE_BIND':'127.0.0.1','COURSE_LAB_ID':'0123456789ab','COURSE_WORKER_URL':'http://127.0.0.1:'+str(ports[0])}))
                    for attempt in range(80):
                        if children[-1].poll() is not None:self.fail('Owned app exited before health check')
                        try:
                            with opener.open(f'http://127.0.0.1:{port}/healthz',timeout=.2) as response:
                                self.assertEqual('station14',response.headers.get('X-Course-Lab'))
                                self.assertEqual('0123456789ab',response.headers.get('X-Course-Lab-Run'))
                                break
                        except (urllib.error.URLError,TimeoutError):time.sleep(.025)
                    else:self.fail('Owned app startup timed out')
                for mode,expected in (('normal',200),('slow',200),('error',503),('invalid',400)):
                    try:response=opener.open(f'http://127.0.0.1:{ports[1]}/work?mode={mode}',timeout=3)
                    except urllib.error.HTTPError as error:response=error
                    with response:
                        self.assertEqual(expected,response.status)
                        self.assertEqual('0123456789ab',response.headers['X-Course-Lab-Run'])
                        self.assertEqual('disabled',response.headers['X-Course-Trace-Id'])
                for port in ports:
                    with opener.open(f'http://127.0.0.1:{port}/metrics',timeout=2) as response:
                        text=response.read().decode()
                        self.assertIn('course_requests_total{outcome="ok"} 2',text)
                        self.assertIn('course_inflight 0',text)
                        self.assertIn('course_request_duration_seconds_count '+('3' if port==ports[0] else '4'),text)
            finally:
                for child in reversed(children):
                    if child.poll() is None:child.terminate()
                    try:out,err=child.communicate(timeout=8)
                    except subprocess.TimeoutExpired:
                        child.kill();out,err=child.communicate(timeout=5)
                        self.fail('Owned app did not stop within the test budget: '+err)
                    self.assertEqual(0,child.returncode,err)
                    for line in out.splitlines():
                        event=json.loads(line)
                        self.assertEqual('disabled',event['trace_id'])


if __name__=='__main__':unittest.main()
