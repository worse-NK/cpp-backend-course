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
case "$(/usr/bin/busybox cat /proc/cmdline)" in
  *course_gap_tooling_perf=1*) python3 -u /course/tooling_perf.py ;;
  *) python3 -u /course/experiment.py run ;;
esac
result=$?
echo "COURSE_GAP_VM_EXIT=$result"
sync
poweroff -f
