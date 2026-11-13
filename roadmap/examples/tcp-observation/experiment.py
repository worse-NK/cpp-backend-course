#!/usr/bin/env python3
"""Own isolated QEMU guest only. Refuses ordinary host execution, even root."""
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import sys
import time

CLIENT='gap-tcp-client';SERVER='gap-tcp-server'
ADDRESS='198.51.100.2';PORT=9100;SIZE=256*1024
CHILDREN=[]

def guard(parent=False):
    if os.geteuid()!=0 or 'course_gap_acceptance=1' not in Path('/proc/cmdline').read_text():
        raise SystemExit('REFUSED: use the dedicated disposable QEMU guest, not the host')
    if parent and os.getppid()!=1:raise SystemExit('REFUSED: orchestrator must be started by guest PID1')
    if os.uname().release!='6.8.0-142-generic' or os.uname().machine!='x86_64':
        raise SystemExit('UNSUPPORTED: this acceptance pins the Linux6.8 x86_64 TCP_INFO ABI')

def emit(kind,**values):print(json.dumps(dict(kind=kind,**values)),flush=True)
def command(*args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=15)
    if p.returncode:raise RuntimeError((args,p.returncode,p.stderr))
    return p.stdout
def child(namespace,*args):
    p=subprocess.Popen(['ip','netns','exec',namespace,'python3','-u',__file__,*args],
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    CHILDREN.append(p)
    if not select.select([p.stdout],[],[],8)[0]:raise RuntimeError('child did not become ready')
    line=p.stdout.readline();assert line.startswith('ready'),(line,p.poll())
    return p
def finish(p):
    out,err=p.communicate(timeout=25);CHILDREN.remove(p)
    assert p.returncode==0 and not err,(p.returncode,out,err)
    return [json.loads(line) for line in out.splitlines() if line.startswith('{')]

def exact(s,n):
    data=bytearray()
    while len(data)<n:
        chunk=s.recv(n-len(data))
        if not chunk:raise RuntimeError('short stream')
        data.extend(chunk)
    return bytes(data)

def serve(mode):
    guard()
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        listener.bind((ADDRESS,PORT));listener.listen(1);listener.settimeout(15)
        print('ready server',flush=True)
        connection,_=listener.accept()
        with connection as s:
            s.settimeout(15)
            if mode=='push':
                s.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,8192)
                s.setblocking(False);body=b'x'*(2*1024*1024);sent=0;waits=0
                while sent<len(body):
                    try:sent+=s.send(body[sent:sent+16384])
                    except BlockingIOError:
                        waits+=1
                        if not select.select([], [s], [], 5)[1]:raise RuntimeError('slow reader never resumed')
                s.setblocking(True);s.settimeout(10)
                assert exact(s,2)==b'OK'
                emit('push-server',sent=sent,eagain=waits)
            else:
                body=exact(s,SIZE);s.sendall(hashlib.sha256(body).digest())
                emit('pull-server',received=len(body),sha256=hashlib.sha256(body).hexdigest())

def client(mode):
    guard();start=time.monotonic()
    with socket.socket() as s:
        s.settimeout(20)
        if mode=='push':s.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4096)
        s.connect((ADDRESS,PORT))
        if mode=='push':
            time.sleep(.5)
            body=exact(s,2*1024*1024);assert body==b'x'*len(body);s.sendall(b'OK')
            emit('push-client',received=len(body),sha256=hashlib.sha256(body).hexdigest())
        else:
            body=bytes(range(256))*(SIZE//256)
            s.sendall(body);digest=exact(s,32)
            assert digest==hashlib.sha256(body).digest()
            # Linux TCP_INFO ABI prefix, pinned x86_64 Linux6.8 guest. The
            # host acceptance checks offsetof(tcp_info,tcpi_total_retrans)==100.
            info=s.getsockopt(socket.IPPROTO_TCP,socket.TCP_INFO,104)
            assert len(info)==104
            retrans=int.from_bytes(info[100:104],sys.byteorder)
            emit('pull-client',sent=len(body),sha256=digest.hex(),total_retrans=retrans,
                 elapsed_ms=round((time.monotonic()-start)*1000,3))

def capture(interface):
    guard();records=bytearray(struct.pack('<IHHIIII',0xa1b2c3d4,2,4,0,0,65535,1))
    packets=0;zero_windows=0;seen=set();duplicate_ranges=0
    with socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3)) as s:
        # Only inside this offline guest: enlarge our capture socket, not the
        # TCP endpoint and not global kernel settings. Linux SO_RCVBUFFORCE=33.
        s.setsockopt(socket.SOL_SOCKET,33,4*1024*1024)
        s.bind((interface,0));s.settimeout(.1);print('ready capture',flush=True)
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            try:data=s.recv(65535)
            except socket.timeout:continue
            if len(data)<54 or data[12:14]!=b'\x08\x00' or data[23]!=6:continue
            ip=14;ihl=(data[ip]&15)*4;tcp=ip+ihl
            if len(data)<tcp+20:continue
            ports=struct.unpack('!HH',data[tcp:tcp+4])
            if PORT not in ports:continue
            stamp=time.time();sec=int(stamp);micro=int((stamp-sec)*1000000)
            records.extend(struct.pack('<IIII',sec,micro,len(data),len(data)));records.extend(data);packets+=1
            window=int.from_bytes(data[tcp+14:tcp+16],'big');zero_windows+=window==0
            total=int.from_bytes(data[ip+2:ip+4],'big');thl=(data[tcp+12]>>4)*4;length=total-ihl-thl
            if length>0:
                key=(data[ip+12:ip+20],ports,int.from_bytes(data[tcp+4:tcp+8],'big'),length)
                duplicate_ranges+=key in seen;seen.add(key)
        # Linux PACKET_STATISTICS; counts all packets queued to this raw socket.
        received,dropped=struct.unpack('=II',s.getsockopt(263,6,8))
        assert dropped==0,('capture itself dropped packets',received,dropped)
    emit('real-capture',packets=packets,zero_windows=zero_windows,
         socket_packets=received,socket_drops=dropped,window_seconds=4,
         repeated_exact_ranges=duplicate_ranges,pcap_gzip_base64=base64.b64encode(gzip.compress(records)).decode())

def main():
    guard(parent=True)
    assert {x['ifname'] for x in json.loads(command('ip','-j','link','show'))}=={'lo'}
    assert command('ip','netns','list').strip()==''
    command('ip','netns','add',CLIENT);command('ip','netns','add',SERVER)
    command('ip','link','add','cl0','type','veth','peer','name','sv0')
    command('ip','link','set','cl0','netns',CLIENT);command('ip','link','set','sv0','netns',SERVER)
    try:
        for ns,iface,ip in [(CLIENT,'cl0','198.51.100.1/24'),(SERVER,'sv0',ADDRESS+'/24')]:
            command('ip','-n',ns,'link','set','lo','up');command('ip','-n',ns,'addr','add',ip,'dev',iface)
            command('ip','-n',ns,'link','set',iface,'up')
            command('ip','netns','exec',ns,'ethtool','-K',iface,
                    'tso','off','gso','off','gro','off','tx','off','rx','off')
        emit('environment',kernel=command('uname','-r').strip(),tc=command('tc','-V').strip(),external_nic=False)
        for scenario in ['baseline','delay','loss','slow-reader']:
            if scenario=='delay':command('ip','netns','exec',CLIENT,'tc','qdisc','add','dev','cl0','root','netem','delay','15ms')
            if scenario=='loss':
                command('ip','netns','exec',CLIENT,'tc','qdisc','del','dev','cl0','root')
                command('ip','netns','exec',CLIENT,'tc','qdisc','add','dev','cl0','root','netem','delay','15ms','loss','5%')
            if scenario=='slow-reader':command('ip','netns','exec',CLIENT,'tc','qdisc','del','dev','cl0','root')
            mode='push' if scenario=='slow-reader' else 'pull'
            cap=child(SERVER,'capture','sv0');srv=child(SERVER,'server',mode)
            result=command('ip','netns','exec',CLIENT,'python3','-u',__file__,'client',mode)
            sr=finish(srv);trace=finish(cap)
            stats=command('ip','netns','exec',CLIENT,'tc','-s','-j','qdisc','show','dev','cl0')
            emit('scenario',name=scenario,client=json.loads(result),server=sr,capture=trace,qdisc=json.loads(stats))
            if scenario=='slow-reader':assert sr[0]['eagain']>0
            if scenario=='loss':
                assert any(x.get('drops',0)>0 for x in json.loads(stats)),stats
                assert json.loads(result)['total_retrans']>0,result
    finally:
        for p in CHILDREN:
            if p.poll() is None:p.terminate()
            p.communicate(timeout=3)
        command('ip','netns','delete',CLIENT);command('ip','netns','delete',SERVER)
    emit('acceptance',status='PASS',real_kernel=True,synthetic_packets=False)

if __name__=='__main__':
    role=sys.argv[1] if len(sys.argv)>1 else 'help'
    if role=='run':main()
    elif role=='server':serve(sys.argv[2])
    elif role=='client':client(sys.argv[2])
    elif role=='capture':capture(sys.argv[2])
    else:print('Only the dedicated offline QEMU guest may run this experiment.')
