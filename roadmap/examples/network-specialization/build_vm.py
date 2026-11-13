#!/usr/bin/env python3
"""Prepare a disposable offline QEMU guest; never execute host network commands."""
import argparse
import gzip
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

def pack(image_root, archive):
    # The same small newc writer as the course VM builder, kept self-contained
    # so these four downloaded scripts need no repository-only tools.
    with gzip.open(archive, 'wb', compresslevel=3) as out:
        serial = 1
        def entry(name, mode, data=b'', links=1):
            nonlocal serial
            filename = name.encode() + b'\0'
            values = (serial, mode, 0, 0, links, 0, len(data), 0, 0, 0, 0, len(filename), 0)
            header = b'070701' + ''.join(f'{value:08x}' for value in values).encode()
            out.write(header + filename)
            out.write(b'\0' * (-(len(header) + len(filename)) % 4))
            out.write(data); out.write(b'\0' * (-len(data) % 4)); serial += 1
        for path in sorted(image_root.rglob('*')):
            info = path.lstat(); name = str(path.relative_to(image_root))
            if path.is_symlink(): entry(name, stat.S_IFLNK | 0o777, str(path.readlink()).encode())
            elif path.is_dir(): entry(name, stat.S_IFDIR | (info.st_mode & 0o777), links=2)
            else: entry(name, stat.S_IFREG | (info.st_mode & 0o777), path.read_bytes())
        entry('TRAILER!!!', 0)

VERSION = '6.8.0-142-generic'
HASHES = {
    'kernel': '51772494d46f23d0fad486c7bcd59e21727ec59b9b1894f9c6b4d61ca1899d3c',
    'frr': 'ccedcc8a053756575bd9f8935be012080eb70091991afd8bb44c95bd51267a20',
    'yang': 'ee00c785b39db8e2da6f2e8d43cffcb501b5a6c7e54bebc64ee34918cc869e21',
    'modules': 'ee4feb479079151441883b451f0e627df040798c2524641486ce0a90a3811c20',
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--repack', action='store_true', help='Refresh guest scripts in this builder\'s own rootfs')
    for name in HASHES:
        parser.add_argument('--' + name + '-deb', required=True, type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory.parent != Path('/tmp') or not directory.name.startswith('course-optional-net-vm-'):
        parser.error('Use a new owned /tmp/course-optional-net-vm-* directory')
    root = directory / 'rootfs'
    for name, digest in HASHES.items():
        source = getattr(args, name + '_deb')
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            parser.error(name + ' archive hash differs from pinned APT metadata')
    if args.repack:
        marker = root / 'course/owned-offline-guest'
        if not marker.is_file() or marker.read_text() != 'course-optional-network-v1\n':
            parser.error('Not this builder\'s prepared rootfs')
        shutil.copyfile(Path(__file__).with_name('guest.py'), root / 'course/guest.py')
        shutil.copyfile(Path(__file__).with_name('init.sh'), root / 'init')
        (root / 'init').chmod(0o755)
        pack(root, directory / 'initramfs.cpio.gz')
        print('Repacked only owned guest scripts; no VM started')
        return
    if root.exists(): parser.error('Refusing to overwrite an existing rootfs')
    root.mkdir(parents=True)
    packages = directory / 'packages'
    packages.mkdir()
    for name in ['frr', 'yang', 'modules']:
        subprocess.run(['dpkg-deb', '-x', str(getattr(args, name + '_deb')), str(packages)], check=True)
    subprocess.run(['dpkg-deb', '-x', str(args.kernel_deb), str(directory / 'kernel')], check=True)
    copied = set()
    def copy(source, destination=None):
        source = Path(source)
        target = root / str(destination or source).lstrip('/')
        if str(target) in copied: return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target, follow_symlinks=True)
        target.chmod(source.stat().st_mode & 0o777)
        copied.add(str(target))
    libdirs = [packages / 'usr/lib/x86_64-linux-gnu', packages / 'usr/lib/x86_64-linux-gnu/frr']
    env = dict(os.environ, LD_LIBRARY_PATH=':'.join(map(str, libdirs)))
    def dependencies(source):
        result = subprocess.run(['ldd', str(source)], env=env, capture_output=True, text=True)
        if result.returncode and not any(term in result.stdout + result.stderr
                                         for term in ['not a dynamic executable', 'statically linked']):
            raise SystemExit(result.stdout + result.stderr)
        if 'not found' in result.stdout: raise SystemExit(result.stdout)
        for path in re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(', result.stdout, re.M):
            p = Path(path)
            copy(p, '/' + str(p.relative_to(packages)) if p.is_relative_to(packages) else p)
    for name in ['bash', 'env', 'python3', 'ip', 'bridge', 'kmod', 'busybox', 'uname']:
        source = shutil.which(name)
        if not source: raise SystemExit('Missing installed input: ' + name)
        copy(source); dependencies(source)
    for name in ['zebra', 'ospfd', 'bgpd']:
        source = packages / ('usr/lib/frr/' + name)
        copy(source, '/usr/lib/frr/' + name); dependencies(source)
    source = packages / 'usr/bin/vtysh'
    copy(source, '/usr/bin/vtysh'); dependencies(source)
    shutil.copytree(packages / 'usr/share/yang', root / 'usr/share/yang')
    stdlib = Path('/usr/lib/python3.12')
    shutil.copytree(stdlib, root / stdlib.relative_to('/'),
                    ignore=shutil.ignore_patterns('__pycache__', 'test', 'tests', 'site-packages'))
    for extension in (stdlib / 'lib-dynload').glob('*.so'): dependencies(extension)
    for name in ['sh', 'mount', 'poweroff', 'sync', 'mkdir']:
        target = root / 'bin' / name
        target.parent.mkdir(exist_ok=True)
        target.symlink_to('/usr/bin/busybox')
    (root / 'sbin').mkdir(exist_ok=True)
    (root / 'sbin/modprobe').symlink_to('/usr/bin/kmod')
    modules = packages / 'usr/lib/modules' / VERSION
    if not modules.is_dir(): modules = packages / 'lib/modules' / VERSION
    subprocess.run(['depmod', '-b', str(packages), VERSION], check=True)
    deps = dict(line.split(':', 1) for line in (modules / 'modules.dep').read_text().splitlines())
    names = {Path(name).name.split('.ko')[0]: name for name in deps}
    selected = set()
    def module(name):
        path = names[name]
        if path in selected: return
        selected.add(path)
        for dep in deps[path].split(): module(Path(dep).name.split('.ko')[0])
    for name in ['veth', 'bridge', '8021q', 'dummy']: module(name)
    for name in selected: copy(modules / name, '/lib/modules/' + VERSION + '/' + name)
    for p in modules.glob('modules.*'):
        if p.is_file(): copy(p, '/lib/modules/' + VERSION + '/' + p.name)
    for name in ['proc', 'sys', 'dev', 'run', 'tmp', 'etc/netns', 'course', 'etc/frr']:
        (root / name).mkdir(parents=True, exist_ok=True)
    # These are guest-only accounts, not a copy or modification of host accounts.
    (root / 'etc/passwd').write_text('root:x:0:0:root:/root:/bin/sh\nfrr:x:100:100:FRR:/run/frr:/bin/sh\n')
    (root / 'etc/group').write_text('root:x:0:\nfrr:x:100:\nfrrvty:x:101:root,frr\n')
    (root / 'etc/frr/vtysh.conf').write_text('service integrated-vtysh-config\n')
    copy('/etc/protocols')
    copy(Path(__file__).with_name('guest.py'), '/course/guest.py')
    copy(Path(__file__).with_name('init.sh'), '/init')
    (root / 'init').chmod(0o755)
    (root / 'course/owned-offline-guest').write_text('course-optional-network-v1\n')
    pack(root, directory / 'initramfs.cpio.gz')
    print('Prepared verified inputs; no VM started, no host network commands executed.')
    print('kernel:', directory / 'kernel/boot' / ('vmlinuz-' + VERSION))
    print('initrd:', directory / 'initramfs.cpio.gz')

if __name__ == '__main__': main()
