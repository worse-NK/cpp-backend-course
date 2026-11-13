#!/usr/bin/env python3
"""Real Linux/FRR experiment. Refuses to run outside this offline QEMU guest."""
import json
import os
from pathlib import Path
import subprocess
import time

def guard():
    marker = Path('/course/owned-offline-guest')
    if (os.geteuid() != 0 or not marker.is_file()
        or marker.read_text() != 'course-optional-network-v1\n'
        or 'course_optional_network=1' not in Path('/proc/cmdline').read_text()
        or os.uname().release != '6.8.0-142-generic'
        or set(p.name for p in Path('/sys/class/net').iterdir()) != {'lo'}):
        raise SystemExit('Refusing: expected the owned offline diskless guest with only lo')

def run(*args, ns=None, check=True):
    command = (['ip', 'netns', 'exec', ns] if ns else []) + list(args)
    result = subprocess.run(command, capture_output=True, text=True, timeout=12)
    if check and result.returncode:
        raise RuntimeError(' '.join(command) + '\n' + result.stdout + result.stderr)
    return result

def ip(*args, ns=None): return run('ip', *args, ns=ns).stdout

def namespace(name):
    ip('netns', 'add', name)
    ip('link', 'set', 'lo', 'up', ns=name)

def wire(a, aname, b, bname):
    # Fresh namespace-specific interface names, no external link involved.
    left = 'w' + str(wire.count); right = 'x' + str(wire.count); wire.count += 1
    ip('link', 'add', left, 'type', 'veth', 'peer', 'name', right)
    ip('link', 'set', left, 'netns', a); ip('link', 'set', right, 'netns', b)
    ip('link', 'set', left, 'name', aname, ns=a); ip('link', 'set', right, 'name', bname, ns=b)
wire.count = 0

def address(ns, dev, value):
    ip('address', 'add', value, 'dev', dev, ns=ns)
    ip('link', 'set', dev, 'up', ns=ns)

def ping(ns, target):
    return run('busybox', 'ping', '-c', '1', '-W', '1', target, ns=ns, check=False).returncode == 0

def poll(description, predicate, seconds=40):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        try:
            last = predicate()
            if last: return last
        except (RuntimeError, KeyError, ValueError, TypeError): pass
        time.sleep(.25)
    raise RuntimeError('Timed out: ' + description + '; last=' + repr(last))

def remove(names):
    for name in names: ip('netns', 'delete', name)

def vlan_experiment():
    names = ['vs1', 'vs2', 'va', 'vb', 'vc']
    for name in names: namespace(name)
    for sw in ['vs1', 'vs2']:
        ip('link', 'add', 'br0', 'type', 'bridge', 'vlan_filtering', '1',
           'vlan_default_pvid', '0', 'stp_state', '0', ns=sw)
        ip('link', 'set', 'br0', 'up', ns=sw)
    wire('va', 'eth0', 'vs1', 'access10'); wire('vb', 'eth0', 'vs2', 'access10')
    wire('vc', 'eth0', 'vs2', 'access20'); wire('vs1', 'trunk', 'vs2', 'trunk')
    for sw, dev, vid in [('vs1', 'access10', '10'), ('vs2', 'access10', '10'), ('vs2', 'access20', '20')]:
        ip('link', 'set', dev, 'master', 'br0', ns=sw)
        run('bridge', 'vlan', 'add', 'dev', dev, 'vid', vid, 'pvid', 'untagged', ns=sw)
        ip('link', 'set', dev, 'up', ns=sw)
    for sw in ['vs1', 'vs2']:
        ip('link', 'set', 'trunk', 'master', 'br0', ns=sw)
        for vid in ['10', '20']: run('bridge', 'vlan', 'add', 'dev', 'trunk', 'vid', vid, ns=sw)
        ip('link', 'set', 'trunk', 'up', ns=sw)
    for ns, host in [('va', '10'), ('vb', '20'), ('vc', '30')]:
        address(ns, 'eth0', '192.0.2.' + host + '/24')
    assert ping('va', '192.0.2.20'), 'same VLAN must cross trunk'
    assert not ping('va', '192.0.2.30'), 'different VLAN must not share broadcast domain'
    before = json.loads(run('bridge', '-j', 'vlan', 'show', ns='vs2').stdout)
    run('bridge', 'vlan', 'del', 'dev', 'trunk', 'vid', '10', ns='vs2')
    ip('neigh', 'flush', 'all', ns='va')
    assert not ping('va', '192.0.2.20'), 'missing allowed trunk VLAN must break same-VLAN path'
    run('bridge', 'vlan', 'add', 'dev', 'trunk', 'vid', '10', ns='vs2')
    assert ping('va', '192.0.2.20'), 'restoring membership must restore path'
    result = {'same_vlan': True, 'different_vlan': False, 'trunk_vlan_removed': False,
              'restored': True, 'membership_before': before}
    remove(names); return result

def stp_experiment():
    switches = ['s1', 's2', 's3']; names = switches + ['ha', 'hb']
    for name in names: namespace(name)
    for number, sw in enumerate(switches, 1):
        ip('link', 'add', 'br0', 'address', '02:00:00:00:00:0' + str(number),
           'type', 'bridge', 'stp_state', '1', 'priority', str(4096 * number),
           'forward_delay', '200', 'hello_time', '100', 'max_age', '600', ns=sw)
        ip('link', 'set', 'br0', 'up', ns=sw)
    wire('s1', 'to2', 's2', 'to1'); wire('s2', 'to3', 's3', 'to2')
    wire('s1', 'to3', 's3', 'to1'); wire('ha', 'eth0', 's1', 'client')
    wire('hb', 'eth0', 's3', 'client')
    for sw, ports in [('s1', ['to2', 'to3', 'client']), ('s2', ['to1', 'to3']),
                      ('s3', ['to1', 'to2', 'client'])]:
        for dev in ports:
            ip('link', 'set', dev, 'master', 'br0', ns=sw)
            run('bridge', 'link', 'set', 'dev', dev, 'cost', '10', ns=sw)
            ip('link', 'set', dev, 'up', ns=sw)
    address('ha', 'eth0', '198.51.100.10/24'); address('hb', 'eth0', '198.51.100.20/24')
    def states():
        return {sw: {p['ifname']: p['state'] for p in json.loads(run('bridge', '-j', 'link', ns=sw).stdout)}
                for sw in switches}
    before = poll('STP initial blocked redundant port',
                  lambda: (s if s['s3'].get('to2') == 'blocking' and
                             s['s3'].get('to1') == 'forwarding' and ping('ha', '198.51.100.20') else None)
                  if (s := states()) else None)
    start = time.monotonic()
    ip('link', 'set', 'to3', 'down', ns='s1')
    after = poll('STP alternate path forwarding',
                 lambda: (s if s['s3'].get('to2') == 'forwarding' and ping('ha', '198.51.100.20') else None)
                 if (s := states()) else None)
    result = {'before': before, 'after': after, 'observed_recovery_seconds': round(time.monotonic()-start, 3),
              'classic_stp': True, 'timers_ticks': {'forward_delay': 200, 'hello_time': 100, 'max_age': 600}}
    remove(names); return result

def start_frr(ns, daemon, configuration):
    configdir = Path('/etc/frr') / ns; rundir = Path('/run/frr') / ns
    configdir.mkdir(parents=True, exist_ok=True); rundir.mkdir(parents=True, exist_ok=True)
    # No PAM configuration from the host is copied. Only the isolated guest's
    # root uses these local VTY sockets; this is not a host access-control recipe.
    (configdir / 'vtysh.conf').write_text('username root nopassword\n')
    config = configdir / (daemon + '.conf')
    config.write_text('hostname ' + ns + '\nlog file /tmp/' + ns + '-' + daemon + '.log\n' + configuration)
    run('/usr/lib/frr/' + daemon, '-d', '-N', ns, '-u', 'root', '-g', 'root',
        '-f', str(config), '-P', '0', ns=ns)

def vty(ns, command):
    arguments = ['vtysh', '-N', ns]
    for line in command.splitlines(): arguments.extend(['-c', line])
    return run(*arguments, ns=ns).stdout

def stop_frr(ns, daemons):
    for daemon in daemons:
        path = Path('/run/frr') / ns / (daemon + '.pid')
        if path.exists(): os.kill(int(path.read_text()), 15)
    time.sleep(.2)

def router(ns):
    namespace(ns)
    Path('/proc/sys/net/ipv4/ip_forward').read_text() # No host write: already guarded guest.
    run('busybox', 'sysctl', '-w', 'net.ipv4.ip_forward=1', ns=ns)

def ospf_experiment():
    names = ['r1', 'r2', 'r3']
    for name in names: router(name)
    wire('r1', 'ab', 'r2', 'ab'); wire('r2', 'bc', 'r3', 'bc'); wire('r1', 'ac', 'r3', 'ac')
    for ns, dev, value in [('r1','ab','192.0.2.1/30'),('r2','ab','192.0.2.2/30'),
        ('r2','bc','192.0.2.5/30'),('r3','bc','192.0.2.6/30'),
        ('r1','ac','192.0.2.9/30'),('r3','ac','192.0.2.10/30')]: address(ns, dev, value)
    address('r3', 'lo', '203.0.113.33/32')
    for i, ns in enumerate(names, 1):
        start_frr(ns, 'zebra', '')
        ports = {'r1':[('ab',10),('ac',50)], 'r2':[('ab',10),('bc',10)], 'r3':[('bc',10),('ac',50)]}[ns]
        text = ''
        for dev, cost in ports:
            text += ('interface ' + dev + '\n ip ospf area 0\n ip ospf network point-to-point\n'
                     ' ip ospf cost ' + str(cost) + '\n ip ospf hello-interval 1\n ip ospf dead-interval 4\n!\n')
        if ns == 'r3': text += 'interface lo\n ip ospf area 0\n ip ospf passive\n!\n'
        text += 'router ospf\n ospf router-id 0.0.0.' + str(i) + '\n'
        start_frr(ns, 'ospfd', text)
    def route(expected):
        routes = json.loads(vty('r1', 'show ip route ospf json'))
        entries = routes.get('203.0.113.33/32', [])
        if entries and any(h.get('ip') == expected for h in entries[0].get('nexthops', [])):
            return entries[0]
    before = poll('OSPF path via B', lambda: route('192.0.2.2'), 55)
    assert ping('r1', '203.0.113.33'), 'OSPF-selected forwarding path failed'
    database = vty('r1', 'show ip ospf database router')
    start = time.monotonic(); ip('link', 'set', 'bc', 'down', ns='r2')
    after = poll('OSPF direct alternate', lambda: route('192.0.2.10'))
    assert ping('r1', '203.0.113.33'), 'alternate OSPF-selected path failed'
    result = {'before': before, 'after': after, 'router_lsa_before': database,
              'observed_recovery_seconds': round(time.monotonic()-start, 3),
              'kernel_route_after': ip('route', 'get', '203.0.113.33', ns='r1')}
    for ns in names: stop_frr(ns, ['ospfd', 'zebra'])
    remove(names); return result

def bgp_experiment():
    names = ['a', 'b', 'c']
    for name in names: router(name)
    wire('a', 'to_b', 'b', 'to_a'); wire('a', 'to_c', 'c', 'to_a')
    for ns, dev, value in [('a','to_b','192.0.2.1/30'),('b','to_a','192.0.2.2/30'),
                           ('a','to_c','192.0.2.5/30'),('c','to_a','192.0.2.6/30')]: address(ns,dev,value)
    for ns in ['b','c']: address(ns,'lo','203.0.113.1/24')
    configs = {
      'a': 'router bgp 65000\n bgp router-id 0.0.0.1\n neighbor 192.0.2.2 remote-as 65010\n'
           ' neighbor 192.0.2.6 remote-as 65020\n address-family ipv4 unicast\n'
           '  neighbor 192.0.2.2 route-map FROM-B in\n  neighbor 192.0.2.6 route-map FROM-C in\n'
           ' exit-address-family\n!\nroute-map FROM-B permit 10\n set local-preference 200\n!\n'
           'route-map FROM-C permit 10\n set local-preference 100\n',
      'b': 'router bgp 65010\n bgp router-id 0.0.0.2\n neighbor 192.0.2.1 remote-as 65000\n'
           ' address-family ipv4 unicast\n  network 203.0.113.0/24\n'
           '  neighbor 192.0.2.1 route-map ADVERTISE out\n exit-address-family\n!\n'
           'route-map ADVERTISE permit 10\n match ip address prefix-list LAB\n'
           ' set as-path prepend 65010 65010\n!\nip prefix-list LAB permit 203.0.113.0/24\n',
      'c': 'router bgp 65020\n bgp router-id 0.0.0.3\n neighbor 192.0.2.5 remote-as 65000\n'
           ' address-family ipv4 unicast\n  network 203.0.113.0/24\n'
           '  neighbor 192.0.2.5 route-map ADVERTISE out\n exit-address-family\n!\n'
           'route-map ADVERTISE permit 10\n match ip address prefix-list LAB\n!\n'
           'ip prefix-list LAB permit 203.0.113.0/24\n'}
    for ns in names:
        start_frr(ns,'zebra','')
        # Explicit filters above limit what is originated. Lab peers need no imported routes on B/C.
        start_frr(ns,'bgpd', configs[ns])
    def best(expected, minimum_paths=1):
        table = json.loads(vty('a','show bgp ipv4 unicast 203.0.113.0/24 json'))
        paths = table.get('paths', [])
        if len(paths) < minimum_paths or not all(p.get('valid') for p in paths): return None
        selected = [p for p in paths if p.get('bestpath', {}).get('overall')]
        if selected and any(h.get('ip') == expected for h in selected[0].get('nexthops', [])):
            return table
    # Waiting for B alone would NOT prove that policy beat C: C might not yet
    # have advertised anything. Require both valid competing paths first.
    before = poll('BGP two valid candidates; policy selects longer B path',
                  lambda: best('192.0.2.2', minimum_paths=2), 55)
    candidates = {p['peer']['peerId']: p for p in before['paths']}
    assert candidates['192.0.2.2']['locPrf'] == 200 and candidates['192.0.2.2']['aspath']['length'] == 3
    assert candidates['192.0.2.6']['locPrf'] == 100 and candidates['192.0.2.6']['aspath']['length'] == 1
    # Do not accept just a best-path flag: inspect actual kernel route and delivery too.
    poll('BGP FIB via B', lambda: 'via 192.0.2.2' in ip('route','get','203.0.113.1',ns='a'))
    assert ping('a','203.0.113.1'), 'BGP-selected B forwarding failed'
    vty('b','configure terminal\nrouter bgp 65010\naddress-family ipv4 unicast\nno network 203.0.113.0/24\nend')
    after = poll('BGP withdrawal selects C', lambda: best('192.0.2.6'))
    poll('BGP FIB via C', lambda: 'via 192.0.2.6' in ip('route','get','203.0.113.1',ns='a'))
    assert ping('a','203.0.113.1'), 'BGP-selected C forwarding failed'
    result = {'before': before, 'after_withdraw': after,
              'kernel_route_after': ip('route','get','203.0.113.1',ns='a')}
    for ns in names: stop_frr(ns,['bgpd','zebra'])
    remove(names); return result

def main():
    guard()
    evidence = {'scope': 'own offline QEMU guest; no NIC/disks/shared host mount',
                'kernel': os.uname().release,
                'frr': run('/usr/lib/frr/bgpd','--version').stdout.splitlines()[0]}
    only = next((arg.split('=', 1)[1] for arg in Path('/proc/cmdline').read_text().split()
                 if arg.startswith('course_optional_only=')), None)
    for name, experiment in [('vlan',vlan_experiment),('stp',stp_experiment),
                             ('ospf',ospf_experiment),('bgp',bgp_experiment)]:
        if only and name != only: continue
        print('START ' + name, flush=True)
        try: evidence[name] = experiment()
        except Exception:
            # Only our guest's generated configs/logs, never host or user captures.
            for path in sorted(Path('/tmp').glob('*-*.log')):
                print('GUEST_LOG ' + path.name + '\n' + path.read_text()[-6000:], flush=True)
            for ns in ['r1', 'r2', 'r3', 'a', 'b', 'c']:
                if Path('/run/netns', ns).exists():
                    for command in ['show running-config', 'show ip ospf neighbor',
                                    'show ip route', 'show bgp summary']:
                        result = run('vtysh', '-N', ns, '-c', command, ns=ns, check=False)
                        print('GUEST_DIAGNOSTIC ' + ns + ' ' + command + '\n' + result.stdout + result.stderr, flush=True)
            raise
        print('EVIDENCE_' + name.upper() + '=' + json.dumps(evidence[name], sort_keys=True), flush=True)
    print('COURSE_OPTIONAL_EVIDENCE=' + json.dumps(evidence, sort_keys=True), flush=True)

if __name__ == '__main__': main()
