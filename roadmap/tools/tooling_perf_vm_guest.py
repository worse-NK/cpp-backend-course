#!/usr/bin/env python3
"""Software events only, own process, isolated guest. Not hardware PMU evidence."""
import json
import os
from pathlib import Path
import subprocess

def main():
    if os.geteuid()!=0 or os.getppid()!=1 or 'course_gap_tooling_perf=1' not in Path('/proc/cmdline').read_text():
        raise SystemExit('Refused outside the dedicated offline guest')
    interfaces=json.loads(subprocess.check_output(['ip','-j','link','show'],text=True))
    assert {i['ifname'] for i in interfaces}=={'lo'}
    report={'kind':'perf-acceptance','environment':'offline QEMU/TCG, x86_64 Linux6.8',
            'events':'software only; no hardware cycles claim','cases':[]}
    for mode in ['cpu','wait']:
        command=['perf','stat','-x',';','-e','task-clock,context-switches,page-faults',
                 '--','/course/perf_workload',mode,'4']
        r=subprocess.run(command,capture_output=True,text=True,timeout=45)
        assert r.returncode==0,(command,r.stdout,r.stderr)
        assert 'not supported' not in r.stderr and 'not counted' not in r.stderr,r.stderr
        assert 'task-clock' in r.stderr and 'checksum=' in r.stdout
        report['cases'].append({'mode':mode,'stdout':r.stdout,'perf_stat':r.stderr})
    r=subprocess.run(['perf','record','-e','cpu-clock:u','-F','49','-g','--call-graph','fp',
                      '-o','/tmp/course-perf.data','--','/course/perf_workload','cpu','8'],
                     capture_output=True,text=True,timeout=60)
    assert r.returncode==0,(r.stdout,r.stderr)
    assert Path('/tmp/course-perf.data').stat().st_size>0
    out=subprocess.run(['perf','report','--stdio','--no-children','--sort','symbol',
                        '--percent-limit','0.5','-i','/tmp/course-perf.data'],capture_output=True,text=True,timeout=20)
    assert out.returncode==0,(out.stdout,out.stderr)
    assert 'mix' in out.stdout,out.stdout
    report.update(status='PASS',record_stdout=r.stdout,record_stderr=r.stderr,
                  report=out.stdout,data_bytes=Path('/tmp/course-perf.data').stat().st_size)
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
