#!/usr/bin/env python3
"""Run only the owned, diskless/offline acceptance guest and retain its evidence."""
import argparse
import base64
import gzip
import hashlib
import json
import re
from pathlib import Path
import subprocess

VERSION='6.8.0-142-generic'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--label',default='evidence')
    parser.add_argument('--perf',action='store_true')
    args=parser.parse_args();directory=args.directory.resolve()
    if directory.parent!=Path('/tmp') or not directory.name.startswith('course-gap-net-vm-'):
        parser.error('Expected this builder\'s /tmp/course-gap-net-vm-* directory')
    kernel=directory/'kernel/boot'/('vmlinuz-'+VERSION);initrd=directory/'initramfs.cpio.gz'
    if not kernel.is_file() or not initrd.is_file():parser.error('Run the builder first')
    if not re.fullmatch('[a-z][a-z0-9-]{0,40}',args.label):parser.error('Invalid evidence label')
    output=directory/args.label
    if output.exists():parser.error('Refusing to overwrite existing evidence')
    output.mkdir()
    perf_mode=args.perf
    kernel_args='console=ttyS0 rdinit=/init panic=1 course_gap_acceptance=1'
    if perf_mode:kernel_args+=' course_gap_tooling_perf=1'
    args=['qemu-system-x86_64','-accel','tcg','-m','768','-smp','2','-nodefaults',
          '-no-user-config','-display','none','-serial','stdio','-monitor','none',
          '-nic','none','-no-reboot','-kernel',str(kernel),'-initrd',str(initrd),
          '-append',kernel_args]
    with (output/'guest.log').open('w') as log:
        with subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,text=True) as process:
            try:code=process.wait(timeout=120)
            except subprocess.TimeoutExpired:
                process.terminate();process.wait(timeout=5)
                raise SystemExit('Own guest timed out; see retained log')
    raw=(output/'guest.log').read_text();events=[]
    for line in raw.splitlines():
        if line.startswith('{'):events.append(json.loads(line))
    assert code==0 and 'COURSE_GAP_VM_EXIT=0' in raw,raw[-3000:]
    if perf_mode:
        result=next(e for e in events if e.get('kind')=='perf-acceptance')
        assert result['status']=='PASS'
        (output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result,ensure_ascii=False,indent=2))
        print('Evidence',output)
        return
    assert any(e.get('kind')=='acceptance' and e.get('status')=='PASS' for e in events)
    report={'scope':'Real packets, synthetic application payload, isolated offline QEMU guest',
            'kernel_sha256':hashlib.sha256(kernel.read_bytes()).hexdigest(),
            'initrd_sha256':hashlib.sha256(initrd.read_bytes()).hexdigest(),
            'scenarios':[]}
    for event in events:
        if event['kind']=='environment':report['environment']=event
        if event['kind']!='scenario':continue
        capture=event['capture'][0]
        pcap=gzip.decompress(base64.b64decode(capture.pop('pcap_gzip_base64')))
        filename=event['name']+'.pcap';(output/filename).write_bytes(pcap)
        event['capture'][0].update(file=filename,sha256=hashlib.sha256(pcap).hexdigest(),bytes=len(pcap))
        report['scenarios'].append(event)
    assert len(report['scenarios'])==4
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    print('Evidence',output)

if __name__=='__main__':main()
