#!/usr/bin/env python3
"""Start only the prepared diskless guest: no NIC, disk, or shared host mount."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--only', choices=['vlan', 'stp', 'ospf', 'bgp'], help='Run one guest diagnostic, not the full acceptance')
    args = parser.parse_args(); directory = args.directory.resolve()
    marker = directory / 'rootfs/course/owned-offline-guest'
    if directory.parent != Path('/tmp') or not directory.name.startswith('course-optional-net-vm-'):
        parser.error('Expected this builder\'s owned /tmp directory')
    if not marker.is_file() or marker.read_text() != 'course-optional-network-v1\n':
        parser.error('Not a prepared owned guest')
    command = ['qemu-system-x86_64', '-accel', 'tcg', '-machine', 'q35', '-m', '512',
        '-smp', '1', '-nodefaults', '-nic', 'none', '-display', 'none', '-monitor', 'none',
        '-serial', 'stdio', '-no-reboot', '-kernel',
        str(directory / 'kernel/boot/vmlinuz-6.8.0-142-generic'),
        '-initrd', str(directory / 'initramfs.cpio.gz'), '-append',
        'console=ttyS0 panic=-1 quiet course_optional_network=1' +
        (' course_optional_only=' + args.only if args.only else '')]
    chunks = []; expired = threading.Event()
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory,
            prefix='console-', suffix='.log', delete=False) as log, \
         subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as process:
        print('Owned guest console:', log.name, flush=True)
        def timeout():
            expired.set(); process.kill()
        timer = threading.Timer(240, timeout); timer.daemon = True; timer.start()
        try:
            for line in process.stdout:
                chunks.append(line); print(line, end='', flush=True)
                log.write(line); log.flush()
            result = process.wait()
        finally: timer.cancel()
    if expired.is_set(): raise SystemExit('Guest did not finish within 240 s; QEMU was stopped')
    output = ''.join(chunks)
    if result or 'COURSE_OPTIONAL_VM_EXIT=0' not in output:
        raise SystemExit('Guest acceptance did not pass')

if __name__ == '__main__': main()
