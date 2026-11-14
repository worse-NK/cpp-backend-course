#!/usr/bin/env python3
"""Build four related, local-only network laboratories from one reader template."""
import argparse
from html import escape
import json
from pathlib import Path
from web_security import secure_html

ROOT = Path(__file__).resolve().parents[1]
LABS = {
    'tcp-delivery': ('tcp_delivery_lab.html', 'Как TCP доставляет поток', 'cpp_station7_networking.html#section=tcp-loss-retransmission'),
    'packetpath': ('packet_path_lab.html', 'Пакет пересекает сети', 'cpp_station7_linux_networks.html#section=netlab-packet-walk'),
    'network-setup': ('network_setup_lab.html', 'Как компьютер подключается к сети', 'cpp_station7_networking.html#section=dhcp-network-config'),
    'vpn-tunnels': ('vpn_tunnels_lab.html', 'Как работает сетевой туннель', 'cpp_station7_networking.html#section=vpn-network-context'),
}


def render(lab_id):
    filename, title, back = LABS[lab_id]
    source = (ROOT / 'templates/network_lab.html').read_text()
    source = source.replace('{{title}}', escape(title)).replace('{{back}}', escape(back, quote=True))
    source = source.replace('{{config}}', json.dumps({'id': lab_id}, ensure_ascii=False))
    return secure_html(source.encode(), name=filename)


def render_all():
    return {details[0]: render(key) for key, details in LABS.items()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for name, content in render_all().items():
        path = ROOT / name
        if args.check:
            if not path.exists() or path.read_bytes() != content:
                raise SystemExit('Stale network laboratory: ' + name)
        else:
            path.write_bytes(content)
    print('PASS: four network laboratories match template and CSP' if args.check else 'Built four network laboratories')
