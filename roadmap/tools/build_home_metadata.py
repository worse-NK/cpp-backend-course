#!/usr/bin/env python3
"""Refresh only derived station counters in the editable home-page JSON."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def render():
    path = ROOT / 'cpp_backend_roadmap.html'
    text = path.read_text()
    pattern = r'(<script id="roadmap-data" type="application/json">\n)(.*?)(\n</script>)'
    match = re.search(pattern, text, re.S)
    if not match:
        raise ValueError('home data not found')
    data = json.loads(match[2])
    by_file = {d['meta']['sourceFile']: d for p in (ROOT / 'content').glob('station*.json')
               for d in [json.loads(p.read_text())]}
    for stage in data['stages']:
        if stage.get('station'):
            meta = stage['station']
            station = by_file[meta['file']]
            meta['totalSections'] = len(station['theory'])
            if meta['storeKey'] != station['meta']['storeKey']:
                raise ValueError('progress store identity mismatch; not an automatic migration')
    return text[:match.start(2)] + json.dumps(data, ensure_ascii=False, indent=2) + text[match.end(2):]


if __name__ == '__main__':
    (ROOT / 'cpp_backend_roadmap.html').write_text(render())
    print('Refreshed home station counters; identities and route preserved')
