#!/usr/bin/env python3
"""Build the standalone prepared distributed-systems laboratory."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from course_theme import lab_flask_icon

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "distributed_lab.html"


def asset(name: str) -> str:
    digest = hashlib.sha256((ROOT / "assets" / name).read_bytes()).hexdigest()[:12]
    return f"assets/{name}?v={digest}"


def render() -> str:
    source = """<!doctype html>
<html lang="ru" class="course-dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#18252f">
<meta name="description" content="Пошаговый разбор потерянного ответа, старого лидера и восстановления заказа. Подготовленная учебная модель распределённых решений.">
<title>Распределённые решения — лаборатория станции 16</title>
<link rel="stylesheet" href="{theme}">
<link rel="stylesheet" href="{css}">
<script defer src="{model}"></script>
<script defer src="{script}"></script>
</head>
<body class="course-dark distributed-lab">
<a class="skip-link" href="#experiment">К разбору события</a>
<header class="lab-header">
  <a class="course-home" href="cpp_backend_roadmap.html">C++ и backend</a>
  <nav aria-label="Навигация курса">
    <a href="cpp_station16_distributed_systems.html#section=learning-route">Станция 16</a>
    <a class="lab-catalog-link" href="visual_labs.html">{flask}Все лаборатории</a>
  </nav>
</header>
<main>
<section class="lab-intro" aria-labelledby="lab-title">
  <p class="section-number">Лаборатория станции 16</p>
  <h1 id="lab-title">Кто уже принял решение?</h1>
  <p class="intro-copy">Покупатель нажал кнопку и ждёт подтверждение. Но изменение могло уже сохраниться на сервере, пока ответ ещё идёт или потерялся. Остановимся на каждом событии: сравним, что произошло на самом деле и что знает каждый участник.</p>
  <p class="model-scope"><strong>Подготовленная учебная модель.</strong> Здесь нет настоящего кластера, сетевых задержек или платежей. Шаг назад восстанавливает снимок истории, а не отменяет реальную программу. Ничего не движется само.</p>
</section>
<nav id="scenario-navigation" class="scenario-navigation" aria-label="Выбрать историю"></nav>
<section id="scenario-intro" class="scenario-intro" aria-labelledby="scenario-title">
  <div class="scenario-heading"><h2 id="scenario-title" tabindex="-1"></h2><a id="theory-link" href="cpp_station16_distributed_systems.html#section=raft-log-commit">Разобрать в учебнике</a></div>
  <div id="scenario-context" class="scenario-context"></div>
  <details class="assumptions"><summary>Условия именно этой истории</summary><ul id="scenario-assumptions"></ul></details>
</section>
<div class="experiment-layout" id="experiment" tabindex="-1">
  <aside class="step-rail" aria-label="События истории">
    <h2>Порядок событий</h2>
    <ol id="step-list"></ol>
    <p class="rail-note">Можно выбрать любое событие. Цифры — шаги модели, не измеренные секунды.</p>
  </aside>
  <article class="experiment-content" aria-labelledby="event-title">
    <nav class="step-controls" aria-label="Перемещение по событиям">
      <button id="first-step" type="button">В начало истории</button>
      <div class="step-controls-main">
        <button id="previous-step" type="button">Назад</button>
        <button id="next-step" type="button" class="primary-action">Следующий шаг</button>
      </div>
    </nav>
    <header class="event-header">
      <p id="step-count" class="step-count"></p>
      <h2 id="event-title" tabindex="-1"></h2>
      <p id="event-description" class="event-description"></p>
    </header>
    <section class="state-area" aria-labelledby="states-title">
      <div class="section-heading"><h3 id="states-title">Состояния участников</h3><span id="state-kind"></span></div>
      <p id="state-guide" class="reading-note"></p>
      <div id="participants" class="participants"></div>
    </section>
    <div class="evidence-grid">
      <section class="delivery-area" aria-labelledby="delivery-title">
        <h3 id="delivery-title">Доставка в этом событии</h3>
        <div id="delivery"></div>
      </section>
      <section class="client-area" aria-labelledby="client-title">
        <h3 id="client-title">Что известно клиенту</h3>
        <p id="client-knowledge"></p>
      </section>
    </div>
    <section id="read-comparison" class="read-comparison" aria-labelledby="read-comparison-title" hidden>
      <h3 id="read-comparison-title">Два ответа на один запрос</h3>
      <p>Это альтернативы, а не два последовательных чтения. Сравниваем обещание одного и того же сильного договора.</p>
      <div id="read-alternatives"></div>
    </section>
    <section class="reasoning-area" aria-labelledby="reasoning-title">
      <h3 id="reasoning-title">Почему это важно</h3>
      <p id="event-why"></p>
      <p id="event-rule" class="event-rule"></p>
      <details id="prediction-check" class="prediction-check">
        <summary id="prediction-question"></summary>
        <p id="prediction-answer"></p>
      </details>
    </section>
    <section id="operation-area" class="operation-area" aria-labelledby="operation-title">
      <h3 id="operation-title">История операций</h3>
      <div id="operation-history"></div>
    </section>
    <p class="keyboard-help">Клавиши ← и → меняют шаг. Ссылка в адресной строке открывает выбранное событие; назад и вперёд в браузере сохраняют обычную историю.</p>
  </article>
</div>
<section class="lab-limits" aria-labelledby="limits-title">
  <h2 id="limits-title">Что мы проверяем — и чего не проверяем</h2>
  <p>Состояния и сообщения заданы автором заранее. Они помогают проверить причинное рассуждение: отличить сохранение от применения, неизвестный исход от отказа и локальные данные от полномочий отвечать. Это не выполнение произвольного Raft, банка или внешнего API.</p>
  <p>Проверяемые локальные программы и исходные работы находятся в <a href="cpp_station16_distributed_systems.html#section=distributed-final-workbook">разборе станции 16</a>. Настоящие участники, диски, доставка и безопасность требуют отдельных испытаний в разрешённой среде.</p>
</section>
<noscript><p class="noscript-note">Для пошаговых снимков нужен JavaScript. Те же правила и подробные истории доступны в <a href="cpp_station16_distributed_systems.html#section=learning-route">тексте станции 16</a>.</p></noscript>
<p id="lab-announcement" class="sr-only" role="status" aria-live="polite" aria-atomic="true"></p>
</main>
<footer class="lab-footer"><a href="cpp_station16_distributed_systems.html#section=distributed-observation-lab">Вернуться к главе о лаборатории</a><span>Без счётчика баллов и скрытых сетевых действий</span></footer>
</body>
</html>
""".format(theme=asset("course-theme.css"), css=asset("distributed-lab.css"),
           model=asset("distributed-lab-model.js"), script=asset("distributed-lab.js"), flask=lab_flask_icon())
    from web_security import secure_html
    return secure_html(source.encode(), name='roadmap/distributed_lab.html').decode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check generated output without changing it")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected:
            raise SystemExit("distributed_lab.html is stale; run build_distributed_lab.py")
        print("distributed_lab.html is current")
    else:
        OUTPUT.write_text(expected, encoding="utf-8")
        print("built", OUTPUT.relative_to(ROOT.parent))


if __name__ == "__main__":
    main()
