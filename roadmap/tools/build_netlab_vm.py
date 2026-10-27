#!/usr/bin/env python3
"""Build a self-contained test initramfs; no host root/network changes.

Inputs are installed system binaries/modules, a separately verified official
Ubuntu kernel .deb, and trusted course files. This builder never invokes ip,
nft, mount or modprobe. It does not start QEMU. No user configuration, keys,
host disk, shared directory or external guest NIC is included.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
from pathlib import Path
import re
import shutil
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VERSION = "6.8.0-142-generic"
KERNEL_SHA256 = "3ea2c34b9f55f1614ce3076b4dae83c514ec7f404e5e3b411c1b17d711fad7a2"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--repack", action="store_true",
                        help="Refresh course scripts and repack this builder's existing temporary rootfs")
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory.parent != Path("/tmp") or not directory.name.startswith("cpp-course-netlab-vm-"):
        parser.error("Use a previously created /tmp/cpp-course-netlab-vm-* directory")
    package = directory / "linux-image.deb"
    if hashlib.sha256(package.read_bytes()).hexdigest() != KERNEL_SHA256:
        raise SystemExit("Kernel package does not match the signed APT metadata SHA-256")
    image_root = directory / "rootfs"
    if args.repack:
        if not (image_root / "course/guest_acceptance.py").is_file() or not (image_root / "init").is_file():
            raise SystemExit("Not this builder's temporary rootfs")
        shutil.copyfile(ROOT / "tools/netlab_vm_init.sh", image_root / "init")
        (image_root / "init").chmod(0o755)
        shutil.copyfile(ROOT / "tools/netlab_vm_guest.py", image_root / "course/guest_acceptance.py")
        shutil.copyfile("/etc/protocols", image_root / "etc/protocols")
        for path in (ROOT / "examples/station7-netlab").iterdir():
            if path.suffix in (".sh", ".nft", ".cpp"):
                shutil.copyfile(path, image_root / "course" / path.name)
        # The executable must match the refreshed source, not a previous build.
        probe = directory / "udp_probe"
        subprocess.run(["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
                        str(ROOT / "examples/station7-netlab/udp_probe.cpp"), "-o", str(probe)], check=True)
        shutil.copyfile(probe, image_root / "course/udp_probe")
        (image_root / "course/udp_probe").chmod(0o755)
        pack(image_root, directory / "initramfs.cpio.gz")
        print("Repacked guest scripts; no VM started and no host network commands invoked")
        return
    if image_root.exists():
        raise SystemExit("Refusing to overwrite an existing rootfs; use a fresh temporary directory")
    image_root.mkdir(mode=0o755)
    extracted = directory / "kernel-package"
    subprocess.run(["dpkg-deb", "-x", str(package), str(extracted)], check=True)
    kernel = extracted / "boot" / ("vmlinuz-" + VERSION)
    if not kernel.is_file():
        raise SystemExit("Expected kernel is missing from the verified package")
    copied = set()

    def copy_file(source, target=None):
        source = Path(source)
        target = target or str(source)
        destination = image_root / target.lstrip("/")
        if str(destination) in copied:
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination, follow_symlinks=True)
        destination.chmod(source.stat().st_mode & 0o777)
        copied.add(str(destination))

    def binary(source, target=None):
        copy_file(source, target)
        result = subprocess.run(["ldd", str(source)], capture_output=True, text=True, check=False)
        if "not found" in result.stdout:
            raise RuntimeError(result.stdout)
        for dependency in re.findall(r"(?:=>\s+|^\s*)(/\S+)\s+\(", result.stdout, re.M):
            copy_file(dependency)

    for name in ("bash", "env", "python3", "ip", "nft", "kmod", "sysctl", "flock",
                 "mkdir", "chmod", "rm", "rmdir", "sleep", "stat", "uname"):
        executable = shutil.which(name)
        if not executable:
            raise SystemExit("Missing installed dependency: " + name)
        binary(executable)
    binary("/bin/busybox")
    # Busybox provides only the guest's init/housekeeping commands; no host calls.
    for name in ("sh", "mount", "poweroff", "sync", "cat"):
        target = image_root / "bin" / name
        target.parent.mkdir(exist_ok=True)
        target.symlink_to("busybox")
    (image_root / "sbin").mkdir(exist_ok=True)
    (image_root / "sbin/modprobe").symlink_to("../usr/bin/kmod")
    # The tested script calls Python's standard library, not pip/user packages.
    stdlib = Path("/usr/lib/python3.12")
    shutil.copytree(stdlib, image_root / stdlib.relative_to("/"),
                    ignore=shutil.ignore_patterns("__pycache__", "test", "tests", "site-packages"))
    for extension in (stdlib / "lib-dynload").glob("*.so"):
        binary(extension)

    module_root = Path("/lib/modules") / VERSION
    dependencies = {}
    for line in (module_root / "modules.dep").read_text().splitlines():
        key, values = line.split(":", 1)
        dependencies[key] = values.split()
    names = {Path(path).name.split(".ko")[0]: path for path in dependencies}
    selected = set()

    def module(name):
        path = names[name]
        if path in selected:
            return
        selected.add(path)
        for child in dependencies[path]:
            module(Path(child).name.split(".ko")[0])

    for name in ("veth", "bridge", "nf_tables", "nft_ct", "nft_chain_nat", "nft_nat",
                 "nf_conntrack_netlink"):
        module(name)
    for path in selected:
        copy_file(module_root / path)
    for path in module_root.glob("modules.*"):
        if path.is_file():
            copy_file(path)
    for name in ("proc", "sys", "dev", "run", "tmp", "etc/netns", "course"):
        (image_root / name).mkdir(parents=True, exist_ok=True)
    # nft's protocol-name parser needs this public system database, not user config.
    copy_file("/etc/protocols")
    copy_file(ROOT / "tools/netlab_vm_init.sh", "/init")
    (image_root / "init").chmod(0o755)
    copy_file(ROOT / "tools/netlab_vm_guest.py", "/course/guest_acceptance.py")
    for path in (ROOT / "examples/station7-netlab").iterdir():
        if path.suffix in (".sh", ".nft", ".cpp"):
            copy_file(path, "/course/" + path.name)
    probe = directory / "udp_probe"
    subprocess.run(["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
                    str(ROOT / "examples/station7-netlab/udp_probe.cpp"), "-o", str(probe)], check=True)
    binary(probe, "/course/udp_probe")

    # newc entries are root-owned INSIDE the archive, not on the host filesystem.
    archive = directory / "initramfs.cpio.gz"
    pack(image_root, archive)
    print(f"Built {archive}: {archive.stat().st_size} bytes, {len(selected)} kernel modules")
    print(f"Kernel: {kernel}")
    print("No VM has been started; no host network commands were invoked.")


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


if __name__ == "__main__":
    main()
