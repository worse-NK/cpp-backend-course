#!/usr/bin/env python3
"""Add own bounded workload/perf to the existing offline acceptance initramfs."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
from build_netlab_vm import pack

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
    directory=p.parse_args().directory.resolve();root=directory/'rootfs'
    if directory.parent!=Path('/tmp') or not directory.name.startswith('course-gap-net-vm-'):
        p.error('Expected an owned temporary acceptance directory')
    if not (root/'course/experiment.py').is_file() or not (root/'init').is_file():
        p.error('Build the isolated network rootfs first')
    binary=directory/'perf_workload'
    subprocess.run(['g++','-std=c++20','-O2','-g','-fno-omit-frame-pointer','-fno-inline','-pthread',
                    str(ROOT/'examples/tooling-closed-loop/perf_workload.cpp'),'-o',str(binary)],check=True)
    def copy(src,target=None):
        src=Path(src);out=root/str(target or src).lstrip('/')
        out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,out);out.chmod(src.stat().st_mode&0o777)
    # Ubuntu's /usr/bin/perf is a kernel-version wrapper, not the executable.
    perf=Path('/usr/lib/linux-tools-6.8.0-142/perf')
    if not perf.is_file() or perf.read_bytes()[:4]!=b'\x7fELF':
        raise SystemExit('Pinned perf ELF is missing; no package or host policy change')
    for src,target in [(str(perf),'/usr/bin/perf'),(str(binary),'/course/perf_workload')]:
        if not src:raise SystemExit('perf missing; no action on kernel policy')
        copy(src,target)
        dependencies=subprocess.run(['ldd',src],capture_output=True,text=True,check=True).stdout
        if 'not found' in dependencies:raise SystemExit(dependencies)
        for dep in re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(',dependencies,re.M):copy(dep)
    copy(ROOT/'tools/tooling_perf_vm_guest.py','/course/tooling_perf.py')
    copy(ROOT/'tools/gap_network_vm_init.sh','/init')
    (root/'init').chmod(0o755)
    pack(root,directory/'initramfs.cpio.gz')
    print('Prepared own workload and perf; no host policy change and no VM started')

if __name__=='__main__':main()
