#!/bin/sh
# QEMU guest PID1 only. No disk, host mount or external network is attached.
[ "$$" = "1" ] || { echo "Refused outside guest PID1" >&2; exit 2; }
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL=C
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mkdir -p /dev/pts /run /tmp /etc/netns
mount -t devpts devpts /dev/pts
mount -t tmpfs -o mode=0755 tmpfs /run
mount -t tmpfs -o mode=1777 tmpfs /tmp
/sbin/modprobe veth
/sbin/modprobe sch_netem
python3 -u /course/experiment.py run
result=$?
echo "COURSE_GAP_VM_EXIT=$result"
sync
poweroff -f
