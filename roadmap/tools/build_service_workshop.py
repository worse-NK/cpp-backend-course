#!/usr/bin/env python3
"""Render the guided server practice from small, editable chapter fragments."""
import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'content/service-workshop'


def render():
    data = json.loads((SOURCE / 'route.json').read_text())
    chapters = data['chapters']
    ids = [chapter['id'] for chapter in chapters]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate workshop chapter')
    nav, body = [], []
    for index, chapter in enumerate(chapters):
        anchor = chapter['id']
        if not anchor.isascii() or not anchor.replace('-', '').isalnum():
            raise ValueError('Unsafe workshop chapter ID')
        fragment = (SOURCE / (anchor + '.html')).read_text()
        title = escape(chapter['title'])
        nav.append(f'<a href="#{anchor}"><span>{index + 1:02}</span><span>{title}<small>{escape(chapter["context"])}</small></span></a>')
        previous = f'<a href="#{ids[index - 1]}">← {escape(chapters[index - 1]["title"])}</a>' if index else '<a href="cpp_station8_rest_api.html#section=httplib-example">← К станции 8</a>'
        following = f'<a href="#{ids[index + 1]}">{escape(chapters[index + 1]["title"])} →</a>' if index + 1 < len(ids) else '<a href="cpp_station10_production.html">Вернуться к станции 10 →</a>'
        body.append(f'''<article class="workshop-chapter" id="{anchor}" tabindex="-1" aria-labelledby="{anchor}-title">
<header class="chapter-header"><p class="eyebrow">ПРАКТИКУМ · ШАГ {index + 1} ИЗ {len(chapters)}</p>
<h1 id="{anchor}-title">{title}</h1><p class="lead">{escape(chapter['lead'])}</p></header>
{fragment}
<nav class="chapter-pagination" aria-label="Следующий этап">{previous}{following}</nav></article>''')
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Свой C++-сервис: от localhost до Linux-сервера · Практикум</title>
<meta name="description" content="Пошаговый практикум: C++ HTTP API, curl, PostgreSQL, Docker Compose, SSH, Linux-VM и необязательный HTTPS на VPS.">
<link rel="stylesheet" href="assets/service-workshop.css?v=20261025"></head>
<body><a class="skip-link" href="#workshop-main">К текущему шагу</a>
<div class="workshop-layout"><aside class="workshop-sidebar"><a class="course-link" href="cpp_backend_roadmap.html">← C++ и backend</a>
<p class="eyebrow">СКВОЗНАЯ ПРАКТИКА</p><p class="workshop-name">Один сервис.<br>Три среды.</p>
<p class="sidebar-intro">От процесса на своём компьютере до сервиса на отдельной Linux-машине.</p>
<details class="workshop-contents" id="workshop-contents" open><summary>Маршрут практикума</summary><nav aria-label="Этапы практикума">{''.join(nav)}</nav></details>
<div class="course-stations"><span>Опираемся на главы</span><a href="cpp_station8_rest_api.html">8 · HTTP API</a><a href="cpp_station9_databases.html">9B · PostgreSQL</a><a href="cpp_station10_production.html">10 · Эксплуатация</a></div>
<a class="download-link" href="https://github.com/worse-NK/cpp-backend-course/tree/main/roadmap/examples/service-workshop">Файлы проекта на GitHub ↗</a>
</aside><main id="workshop-main">{''.join(body)}<p id="workshop-status" class="sr-only" role="status" aria-live="polite"></p></main></div>
<script src="assets/service-workshop.js?v=20261025-mobile" defer></script></body></html>'''


if __name__ == '__main__':
    (ROOT / 'service_workshop.html').write_text(render())
    count = len(json.loads((SOURCE / 'route.json').read_text())['chapters'])
    print(f'Built service_workshop.html ({count} guided stages; no browser-side commands)')
