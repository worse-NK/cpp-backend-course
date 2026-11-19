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


def quorum_map() -> str:
    """Two independent duplex channels. Geometry is mirrored, text is not."""
    channels = []
    nodes = []
    for replica, flip, x in (("B", "", 11), ("C", ' transform="translate(480 0) scale(-1 1)"', 334)):
        out = "M203 74V82Q203 98 186 98H73Q56 98 56 115V167"
        back = "M104 167V142Q104 126 121 126H208Q225 126 225 109V74"
        channels.append(f'''<g id="quorum-channels-{replica}" data-phase="0"{flip}>
          <path class="q-out" d="{out}"/><path class="q-back" d="{back}"/>
          <path class="q-flash q-write-flash" d="{out}" pathLength="100"/>
          <path class="q-flash q-return-flash" d="{back}" pathLength="100"/>
          <path class="q-out-tip" d="m52 156 4 7 4-7"/><path class="q-back-tip" d="m221 85 4-7 4 7"/>
          <g class="q-packet" transform="translate(132 98)"><rect x="-12" y="-9" width="24" height="18" rx="3"/><path d="M-6-3H6M-6 2H2"/></g>
          <g class="q-receipt" transform="translate(159 126)"><path d="m0-11 12 11L0 11l-12-11z"/><path class="q-tick" d="m-5 0 3 3 7-7"/></g>
          <circle class="q-arrived" cx="225" cy="76" r="4.7"/>
        </g>''')
        nodes.append(f'''<g id="quorum-server-{replica}" class="q-server" transform="translate({x} 167)" data-phase="0">
          <path class="q-case" d="M0 6 6 0h122l7 7v61H0z"/>
          <text x="12" y="29" class="q-letter">{replica}</text><text x="44" y="26" class="q-role">копия</text>
          <rect class="q-old" x="12" y="38" width="48" height="22" rx="3"/><text x="36" y="54" class="q-index">07</text>
          <rect class="q-new" x="65" y="38" width="54" height="22" rx="3"/><text id="quorum-slot-{replica}" class="q-index q-entry" x="92" y="54">—</text>
        </g>''')
    return '''<figure class="quorum-figure">
      <svg class="quorum-map" viewBox="0 0 480 244" role="img" aria-labelledby="quorum-svg-title quorum-svg-desc" focusable="false">
        <title id="quorum-svg-title">Маршруты между лидером A и двумя копиями</title><desc id="quorum-svg-desc"></desc>
        ''' + "".join(channels) + '''
        <g class="q-server q-leader" transform="translate(175 6)">
          <path class="q-case" d="M0 6 6 0h117l7 7v61H0z"/>
          <text x="12" y="29" class="q-letter">A</text><text x="44" y="26" class="q-role">лидер</text>
          <rect class="q-old" x="12" y="38" width="48" height="22" rx="3"/><text x="36" y="54" class="q-index">07</text>
          <rect class="q-new" x="65" y="38" width="51" height="22" rx="3"/><text class="q-index q-entry" x="90" y="54">08</text>
        </g>
        ''' + "".join(nodes) + '''
      </svg>
      <div class="quorum-controls">
        <button type="button" id="quorum-B">Доставить запись на B</button>
        <button type="button" id="quorum-C">Доставить запись на C</button>
      </div>
      <figcaption class="quorum-key"><span><i class="key-record" aria-hidden="true"></i>Запись к копии</span><span><i class="key-ack" aria-hidden="true"></i>Ответ к лидеру</span><span>07, 08 — номера записей на диске</span><button type="button" id="quorum-reset">Сначала</button></figcaption>
    </figure>'''


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
  <p id="quorum-jump-row" hidden><a id="quorum-jump" href="#scenario=lost-reply&amp;step=2"><svg width="32" height="27" viewBox="0 0 32 27" aria-hidden="true" focusable="false"><path d="M16 6v6M16 12H5v7M16 12h11v7" fill="none" stroke="currentColor" stroke-width="1.6"/><rect x="12" y="1" width="8" height="6" rx="1"/><rect x="1" y="19" width="8" height="6" rx="1"/><rect x="23" y="19" width="8" height="6" rx="1"/></svg><span>Открыть схему доставки <small>Опыт на шаге 3</small></span><span aria-hidden="true">→</span></a></p>
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
    <section id="quorum-desk" class="quorum-desk" role="region" aria-labelledby="quorum-title" hidden>
      <p class="step-count">Опыт с доставкой · запись № 8</p>
      <h3 id="quorum-title" tabindex="-1">На двух дисках — значит, лидер уже знает?</h3>
      <p>Сервер A записал команду Анны. Теперь он рассылает её двум другим серверам, B и C. Ты выбираешь, какое сообщение дойдёт следующим. Попробуй сохранить запись на всех трёх дисках так, чтобы A по-прежнему знал только о своей копии.</p>
      {quorum_diagram}
      <div class="quorum-ledgers">
        <div class="quorum-ledger"><h4>Где есть запись</h4><p>Что на самом деле лежит на дисках</p><ul id="quorum-stored"></ul></div>
        <div class="quorum-ledger"><h4>О чём знает A</h4><p>Своя копия и полученные ответы</p><ul id="quorum-known"></ul></div>
      </div>
      <p id="quorum-status" class="quorum-status" role="status" aria-live="polite" aria-atomic="true"></p>
      <p class="reading-note">Это отдельный опыт: кнопки не меняют историю ниже. Лидер не меняется; запись создана в его текущем раунде. Для такой записи достаточно большинства — двух серверов из трёх. Для записей прошлых раундов одного подсчёта копий недостаточно. <a href="https://raft.github.io/raft.pdf">Raft, § 5.3 и 5.4.2 (PDF)</a>.</p>
    </section>
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
  <p>В трёх историях последовательность событий задана заранее. В опыте с доставкой ты сам выбираешь порядок сообщений, но меняются только копии одной записи и сведения о них у лидера. Ни один из этих режимов не запускает настоящий кластер или платёжную систему.</p>
  <p>Проверяемые локальные программы и исходные работы находятся в <a href="cpp_station16_distributed_systems.html#section=distributed-final-workbook">разборе станции 16</a>. Настоящие участники, диски, доставка и безопасность требуют отдельных испытаний в разрешённой среде.</p>
</section>
<noscript><p class="noscript-note">Для пошаговых снимков нужен JavaScript. Те же правила и подробные истории доступны в <a href="cpp_station16_distributed_systems.html#section=learning-route">тексте станции 16</a>.</p></noscript>
<p id="lab-announcement" class="sr-only" role="status" aria-live="polite" aria-atomic="true"></p>
</main>
<footer class="lab-footer"><a href="cpp_station16_distributed_systems.html#section=distributed-observation-lab">Вернуться к главе о лаборатории</a><span>Без счётчика баллов и скрытых сетевых действий</span></footer>
</body>
</html>
""".format(theme=asset("course-theme.css"), css=asset("distributed-lab.css"),
           model=asset("distributed-lab-model.js"), script=asset("distributed-lab.js"), flask=lab_flask_icon(), quorum_diagram=quorum_map())
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
