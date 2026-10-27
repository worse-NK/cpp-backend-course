"""Sync canonical station9 C++ listings and preserve the old entry URL."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def updated_page():
    return '''<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Станция 9 · Базы данных</title></head><body>
<p>Станция перенесена в общий интерфейс учебника.</p>
<p><a href="cpp_station9_databases.html">Открыть станцию 9 →</a></p>
<p><a href="cpp_backend_roadmap.html">← К курсу</a></p>
<script>
const legacy = location.hash.slice(1);
const destination = legacy === 'next' ? '#view=final'
    : legacy === 'route' || !legacy ? ''
    : '#section=' + encodeURIComponent(legacy);
location.replace('cpp_station9_databases.html' + destination);
</script></body></html>
'''

def sync_listings():
    path = ROOT / 'content/station9.json'
    data = json.loads(path.read_text())
    for section in data['theory']:
        if section['id'] in ('cpp-storage', 'parking-final-workbook'):
            filename = 'main.cpp' if section['id']=='cpp-storage' else 'parking.cpp'
            code = (ROOT / 'examples/station9' / filename).read_text().strip()
            matches = [b for b in section['blocks'] if b['type']=='code' and '#include <pqxx/pqxx>' in b['code']]
            if len(matches)!=1:
                raise ValueError('Expected one full C++ listing in '+section['id'])
            matches[0]['code']=code
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

if __name__ == '__main__':
    sync_listings()
    (ROOT / 'cpp_station9_databases_intro.html').write_text(updated_page())
    print('Synchronized station9 listings and legacy entry page')
