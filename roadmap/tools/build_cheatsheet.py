#!/usr/bin/env python3
"""Build an offline, progressively enhanced reference from formatted content."""
import json
from html import escape
from pathlib import Path
from build_glossary import catalog_version

ROOT = Path(__file__).resolve().parents[1]


def render():
    data = json.loads((ROOT / 'content/cheatsheet.json').read_text())
    groups = data['stations']
    extra_sources = {'5Б': '5-linux', '7Б': '7-netlab', '7В': '7-traffic'}
    ids = ['station-' + (extra_sources.get(s['num'], s['num'])) if s['num'].isdigit() or s['num'] in extra_sources else ('code-review' if s['num'] == '★' else 'std-functions') for s in groups]
    nav, body = [], []
    for index, (station, anchor) in enumerate(zip(groups, ids)):
        title = escape(station['title'])
        label = escape(station['num'])
        nav.append(f'<a href="#{anchor}"><span>{label}</span> {title}</a>')
        sections = []
        toc = []
        for j, section in enumerate(station['sections']):
            sid = f'{anchor}-section-{j + 1}'
            heading = escape(section['h'])
            toc.append(f'<a href="#{sid}">{heading}</a>')
            items = []
            for item in section['items']:
                # Editorial HTML is local trusted course content, not user input.
                code = f'<pre><code>{escape(item["code"])}</code></pre>' if 'code' in item else ''
                rule = f'<p class="rule">{item["rule"]}</p>' if 'rule' in item else ''
                items.append(f'<div class="reference-item"><h4>{escape(item["t"])}</h4>{code}{rule}</div>')
            sections.append(f'<section class="reference-section" id="{sid}" tabindex="-1"><h3>{heading}</h3>{"".join(items)}</section>')
        chapter = ''
        if station['num'].isdigit() or station['num'] in extra_sources:
            source_id = extra_sources.get(station['num'], station['num'])
            meta = json.loads((ROOT / f'content/station{source_id}.json').read_text())['meta']
            chapter = f'<a class="button" href="{escape(meta["sourceFile"])}">Читать полную станцию {label} ↗</a>'
        previous = f'<a href="#{ids[index-1]}">← {escape(groups[index-1]["title"])}</a>' if index else '<a href="#top">← К началу</a>'
        following = f'<a href="#{ids[index+1]}">{escape(groups[index+1]["title"])} →</a>' if index+1 < len(ids) else '<a href="cpp_backend_roadmap.html">К курсу →</a>'
        body.append(f'''<details class="reference-group" id="{anchor}" open>
<summary><span class="number">{label}</span><h2>{title}</h2><span class="chevron" aria-hidden="true">⌄</span></summary>
<div class="group-body"><div class="chapter-link">{chapter}<a href="#contents">К оглавлению ↑</a></div>
<nav class="section-toc" aria-label="Темы: {title}">{''.join(toc)}</nav>
{''.join(sections)}
<nav class="chapter-pagination" aria-label="Переходы: {title}">{previous}{following}</nav></div></details>''')
    embedded = json.dumps(data, ensure_ascii=False, indent=2).replace('</', '<\\/')
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(data['title'])}</title><link rel="stylesheet" href="assets/cheatsheet.css"><link rel="stylesheet" href="assets/terms.css?v=20261021"></head>
<body id="top"><a class="skip-link" href="#reference">К справочнику</a>
<div class="reference-layout"><aside id="contents" tabindex="-1">
<a class="course-link" href="cpp_backend_roadmap.html">← C++ и backend</a>
<details class="contents-disclosure" open><summary>Оглавление шпаргалки</summary>
<nav aria-label="Станции шпаргалки">{''.join(nav)}</nav></details>
<a class="sources-link" href="glossary.html">Глоссарий терминов ↗</a>
<a class="sources-link" href="sources.html">Источники курса ↗</a></aside>
<main id="reference"><header><p class="eyebrow">СПРАВОЧНИК · СТАНЦИИ 0–10</p>
<h1>{escape(data['title'])}</h1><p class="lead">{escape(data['subtitle'])}</p>
<p class="scope-note">Для первого знакомства открывай полную главу. Здесь — опорные правила для повторения; подсказки не заменяют разбор предусловий и проверку кода.</p>
<div class="search-panel" hidden><label for="reference-search">Найти правило или пример</label>
<div class="search-row"><input id="reference-search" type="search" placeholder="Например: владение, epoll, ETag, noexcept"><button id="clear-search" type="button">Очистить</button></div>
<p id="search-status" role="status" aria-live="polite"></p>
<div class="controls"><button id="expand-all" type="button">Раскрыть всё</button><button id="collapse-all" type="button">Свернуть всё</button></div></div></header>
{''.join(body)}
<footer><a href="#top">Наверх ↑</a><a href="cpp_backend_roadmap.html">← Вернуться к курсу</a><p>Редакция от 26 октября 2026. Материал хранится локально; ссылки на первоисточники требуют интернета. UB означает отсутствие гарантий поведения, а не особый вариант вывода.</p></footer>
</main></div><script id="cheat-data" type="application/json">{embedded}</script><script src="assets/cheatsheet.js" defer></script><script src="generated/terms.data.js?v={catalog_version()}" defer></script><script src="assets/terms-core.js?v=20261021" defer></script><script src="assets/terms.js?v=20261021" defer></script></body></html>'''


if __name__ == '__main__':
    (ROOT / 'cpp_cheatsheet.html').write_text(render())
    print('Built cpp_cheatsheet.html (offline HTML, local CSS/JS)')
