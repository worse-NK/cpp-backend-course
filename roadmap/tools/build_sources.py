#!/usr/bin/env python3
"""Build a browsable index of existing theory citations, not a verification badge."""
import argparse
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]

def render():
    labs = {lab['id']: lab for lab in json.loads((ROOT / 'content/visual-labs.json').read_text())['labs']}
    parts = ['''<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Источники · C++ и backend-разработка</title>
<style>
body{margin:0;background:#f6f7f9;color:#202b36;font:17px/1.7 system-ui,sans-serif}
main{max-width:900px;margin:auto;padding:40px 24px}h1{line-height:1.2}h2{margin-top:48px}
a{color:#235c9c;text-underline-offset:3px}a:focus-visible,summary:focus-visible{outline:3px solid #ba6d00;outline-offset:4px}
details{border-top:1px solid #cbd3dc;padding:16px 0}summary{cursor:pointer;font-weight:600}
li{margin:10px 0;overflow-wrap:anywhere}.muted{color:#56616e}nav{display:flex;flex-wrap:wrap;gap:16px}
</style><main><a href="cpp_backend_roadmap.html">← К курсу</a>
<h1>На что опирается теория</h1>
<p>Объяснения, аналогии и учебные задачи написаны для этого курса. Ссылки ниже позволяют проверить правила и углубиться в детали; они не означают, что текст дословно взят из источника.</p>
<h2>Как читать ссылки</h2>
<ul>
<li><b>Правила C++.</b> N4861 — открытый рабочий проект стандарта C++20, не опубликованное издание ISO. HTML на timsong-cpp.github.io — удобное представление текста. Текущий draft на eel.is изменяется и может описывать более новые версии языка; для спорного правила C++20 нужна сверка с соответствующей редакцией.</li>
<li><b>Проектирование.</b> C++ Core Guidelines — рекомендации под редакцией Бьёрна Страуструпа и Герба Саттера, а не обязательные требования языка. Их применение зависит от ограничений программы.</li>
<li><b>Сети и HTTP.</b> RFC следует читать вместе с областью применения, обновлениями и errata. RFC 9293 описывает TCP, RFC 9110 — семантику HTTP; устройство конкретного сервера ими полностью не определяется.</li>
<li><b>Инструменты и реализации.</b> Документация CMake, Git, Boost.Asio, Linux man-pages и ABI описывает соответствующие инструменты или платформы. Свойства Linux или конкретного ABI нельзя автоматически переносить на все реализации C++.</li>
<li><b>Практика backend.</b> OWASP, Google SRE и рекомендации по API помогают обсуждать угрозы и компромиссы. Учебная архитектура — пример применения, а не единственно допустимое решение.</li>
</ul>
<p class="muted">Это указатель ссылок из теории, а не отметка о завершённой построчной экспертизе. Наличие ссылки не доказывает корректность каждого утверждения. Если прямой ссылки нет, это явно отмечено: такой раздел нельзя считать проверенным только по этому указателю.</p>
<nav>''']
    paths = sorted((ROOT / 'content').glob('station*.json'), key=lambda p: (int(p.stem[7:].split('-')[0]), -1 if '-sql' in p.stem else 1 if '-' in p.stem else 0))
    for path in paths:
        parts.append(f'<a href="#{path.stem}">{html.escape(json.loads(path.read_text())["meta"]["logo"])}</a>')
    parts.append('</nav>')
    for path in paths:
        data = json.loads(path.read_text())
        parts.append(f'<h2 id="{path.stem}">{html.escape(data["meta"]["title"])}</h2>')
        for section in data['theory']:
            links = {}
            for block in section['blocks']:
                if block.get('type') == 'lab':
                    for source in labs[block['lab']]['sources']:
                        links.setdefault(source['url'], source['title'])
                for url, label in re.findall(r'<a\b[^>]*href=[\"\x27](https?://[^\"\x27]+)[\"\x27][^>]*>(.*?)</a>', block.get('html', ''), re.S):
                    label = html.unescape(re.sub('<[^>]+>', '', label)).strip()
                    url = html.unescape(url)
                    if urlsplit(url).scheme not in ('http', 'https'):
                        continue
                    links.setdefault(url, label or urlsplit(url).netloc)
            title = html.escape(section['title'])
            target = html.escape(data['meta']['sourceFile'] + '#section=' + section['id'], quote=True)
            parts.append(f'<details><summary>{title} · источников: {len(links)}</summary><p><a href="{target}">Открыть раздел теории</a></p>')
            if links:
                parts.append('<ul>')
                for url, label in links.items():
                    parts.append(f'<li><a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(label)}</a> <span class="muted">— {html.escape(urlsplit(url).netloc)}</span></li>')
                parts.append('</ul>')
            else:
                parts.append('<p class="muted">В этом разделе пока нет прямой внешней ссылки. У вводных маршрутов и итогов источники могут находиться в соответствующих тематических разделах.</p>')
            parts.append('</details>')
    parts.append('<section id="service-workshop"><h2>Сквозной серверный практикум</h2><p>Ссылки для воспроизведения команд: версии библиотек и ограничения учебного стенда указаны в самом практикуме. Проверка локального приложения и PostgreSQL не означает, что инструкция была развёрнута на публичном VPS.</p>')
    route = json.loads((ROOT / 'content/service-workshop/route.json').read_text())
    for chapter in route['chapters']:
        fragment = (ROOT / 'content/service-workshop' / (chapter['id'] + '.html')).read_text()
        links = {}
        for url, label in re.findall(r'<a\b[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', fragment, re.S):
            links.setdefault(html.unescape(url), html.unescape(re.sub('<[^>]+>', '', label)).strip())
        parts.append(f'<h3><a href="service_workshop.html#{chapter["id"]}">{html.escape(chapter["title"])}</a></h3><ul>')
        for url, label in links.items():
            parts.append(f'<li><a href="{html.escape(url, quote=True)}">{html.escape(label)}</a></li>')
        parts.append('</ul>')
    parts.append('</section></main></html>\n')
    return '\n'.join(parts)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = ROOT / 'sources.html'
    result = render()
    if args.check:
        if not path.exists() or path.read_text() != result:
            raise SystemExit('sources.html is stale; run build_sources.py')
        print('Sources index is up to date')
    else:
        path.write_text(result)
        print('Built sources.html')
