#!/bin/sh
# Only an initramfs /init for a disposable QEMU guest; never run on the host.
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL=C
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mkdir -p /dev/pts /run /tmp /etc/netns
mount -t devpts devpts /dev/pts
mount -t tmpfs -o mode=0755 tmpfs /run
mount -t tmpfs -o mode=1777 tmpfs /tmp
echo 'COURSE7_VM_BOOT: isolated guest, no external NIC or host filesystem'
uname -r
for module in veth bridge nf_tables nft_ct nft_chain_nat nft_nat nf_conntrack_netlink; do
    /sbin/modprobe "$module" || { echo "COURSE7_VM_MODULE_FAILURE: $module"; /bin/busybox dmesg | /bin/busybox tail -25; poweroff -f; }
done
python3 -u /course/guest_acceptance.py
result=$?
echo "COURSE7_VM_EXIT=$result"
sync
poweroff -f
