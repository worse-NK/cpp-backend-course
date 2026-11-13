#!/usr/bin/env python3
"""Build an isolated acceptance initramfs. Never runs host ip/tc/modprobe."""
import argparse
import hashlib
import gzip
import stat
from pathlib import Path
import re
import shutil
import subprocess


HERE=Path(__file__).resolve().parent
VERSION='6.8.0-142-generic'
# Ubuntu noble-updates package6.8.0-142.142, signed APT metadata checked2026-11-05.
SHA256='51772494d46f23d0fad486c7bcd59e21727ec59b9b1894f9c6b4d61ca1899d3c'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--repack',action='store_true')
    args=parser.parse_args();directory=args.directory.resolve()
    if directory.parent!=Path('/tmp') or not directory.name.startswith('course-gap-net-vm-'):
        parser.error('Expected a new /tmp/course-gap-net-vm-* directory')
    package=directory/'linux-image-6.8.0-142-generic_6.8.0-142.142_amd64.deb'
    if hashlib.sha256(package.read_bytes()).hexdigest()!=SHA256:
        raise SystemExit('Kernel archive does not match the checked APT metadata')
    root=directory/'rootfs'
    if args.repack:
        if not (root/'course/experiment.py').is_file() or not (root/'init').is_file():
            raise SystemExit('Not this builder\'s owned rootfs')
        shutil.copyfile(HERE/'experiment.py',root/'course/experiment.py')
        shutil.copyfile(HERE/'guest_init.sh',root/'init')
        pack(root,directory/'initramfs.cpio.gz')
        print('Repacked known guest scripts only; no VM started')
        return
    if root.exists():raise SystemExit('Refusing to overwrite an existing rootfs')
    root.mkdir();extracted=directory/'kernel'
    subprocess.run(['dpkg-deb','-x',str(package),str(extracted)],check=True)
    copied=set()
    def copy(source,destination=None):
        source=Path(source);destination=root/str(destination or source).lstrip('/')
        if str(destination) in copied:return
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,destination,follow_symlinks=True)
        destination.chmod(source.stat().st_mode&0o777);copied.add(str(destination))
    def binary(name):
        source=shutil.which(name)
        if not source:raise SystemExit('Missing installed input: '+name)
        copy(source)
        result=subprocess.run(['ldd',source],capture_output=True,text=True)
        if 'not found' in result.stdout:raise SystemExit(result.stdout)
        for path in re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(',result.stdout,re.M):copy(path)
    for name in ['bash','env','python3','ip','tc','ethtool','kmod','busybox','uname']:
        binary(name)
    for name in ['sh','mount','poweroff','sync','mkdir']:
        target=root/'bin'/name;target.parent.mkdir(exist_ok=True);target.symlink_to('/usr/bin/busybox')
    (root/'sbin').mkdir(exist_ok=True);(root/'sbin/modprobe').symlink_to('/usr/bin/kmod')
    stdlib=Path('/usr/lib/python3.12')
    shutil.copytree(stdlib,root/stdlib.relative_to('/'),
                    ignore=shutil.ignore_patterns('__pycache__','test','tests','site-packages'))
    for extension in (stdlib/'lib-dynload').glob('*.so'):
        result=subprocess.run(['ldd',str(extension)],capture_output=True,text=True)
        for path in re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(',result.stdout,re.M):copy(path)
    modules=Path('/lib/modules')/VERSION;deps={}
    for line in (modules/'modules.dep').read_text().splitlines():
        name,values=line.split(':',1);deps[name]=values.split()
    names={Path(name).name.split('.ko')[0]:name for name in deps};selected=set()
    def module(name):
        path=names[name]
        if path in selected:return
        selected.add(path)
        for dep in deps[path]:module(Path(dep).name.split('.ko')[0])
    for name in ['veth','sch_netem']:module(name)
    for name in selected:copy(modules/name)
    for p in modules.glob('modules.*'):
        if p.is_file():copy(p)
    for name in ['proc','sys','dev','run','tmp','etc/netns','course']:
        (root/name).mkdir(parents=True,exist_ok=True)
    copy('/etc/protocols');copy(HERE/'experiment.py','/course/experiment.py')
    copy(HERE/'guest_init.sh','/init');(root/'init').chmod(0o755)
    pack(root,directory/'initramfs.cpio.gz')
    print('kernel',extracted/'boot'/('vmlinuz-'+VERSION))
    print('initrd',directory/'initramfs.cpio.gz')
    print('No VM started. No host network settings changed.')

def pack(image_root, archive):
    with gzip.open(archive, "wb", compresslevel=3) as out:
        serial = 1

        def entry(name, mode, data=b"", links=1):
            nonlocal serial
            filename = name.encode() + b"\0"
            values = (serial, mode, 0, 0, links, 0, len(data), 0, 0, 0, 0, len(filename), 0)
            header = b"070701" + "".join(f"{value:08x}" for value in values).encode()
            out.write(header + filename)
            out.write(b"\0" * (-(len(header) + len(filename)) % 4))
            out.write(data)
            out.write(b"\0" * (-len(data) % 4))
            serial += 1

        for path in sorted(image_root.rglob("*")):
            name = str(path.relative_to(image_root))
            info = path.lstat()
            if path.is_symlink():
                entry(name, stat.S_IFLNK | 0o777, str(path.readlink()).encode())
            elif path.is_dir():
                entry(name, stat.S_IFDIR | (info.st_mode & 0o777), links=2)
            else:
                entry(name, stat.S_IFREG | (info.st_mode & 0o777), path.read_bytes())
        entry("TRAILER!!!", 0)


if __name__=='__main__':main()
