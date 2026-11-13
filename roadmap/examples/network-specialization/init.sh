#!/bin/sh
# PID 1 of our diskless offline QEMU guest only.
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL=C
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/frr:/usr/lib/x86_64-linux-gnu
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mkdir -p /dev/pts /run /tmp /etc/netns
mkdir -p /var/tmp
/usr/bin/busybox ln -s /run /var/run
mount -t devpts devpts /dev/pts
mount -t tmpfs -o mode=0755 tmpfs /run
mount -t tmpfs -o mode=1777 tmpfs /tmp
/sbin/modprobe veth
/sbin/modprobe bridge
/sbin/modprobe 8021q
python3 -u /course/guest.py
result=$?
echo "COURSE_OPTIONAL_VM_EXIT=$result"
sync
poweroff -f
