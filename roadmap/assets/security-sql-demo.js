/* Standalone teaching UI. SQL runs only in a disposable, local SQLite Worker.
 * HTTP and C++ are explanatory views, not network requests or a compiler.
 */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  function updateTheoryLink() {
    const link = $('sql-theory-link');
    if (!link) return;
    let from = '', section = '';
    for (const part of ((window.location && window.location.hash) || '').replace(/^#/, '').split('&')) {
      const at = part.indexOf('=');
      if (at < 0) continue;
      try {
        const key = decodeURIComponent(part.slice(0,at)), value = decodeURIComponent(part.slice(at+1));
        if (key === 'from') from = value;
        if (key === 'section') section = value;
      } catch (_) { /* Malformed context cannot become a navigation target. */ }
    }
    const lab = (window.COURSE_LABS || []).find(item => item.id === 'security-sql');
    const entry = lab && lab.entries.find(item => item.station === from && item.section === section && item.scenario === 'sql');
    link.href = entry ? entry.file + '#section=' + encodeURIComponent(entry.section)
      : 'cpp_station15_security.html#section=sql-injection-laboratory';
  }
  updateTheoryLink();
  window.addEventListener('hashchange', updateTheoryLink);
  const model = window.SecuritySQLDemo;
  if (!model) {
    $('status').textContent = 'Не загрузилась модель разбора. Проверь, что рядом со страницей находится папка assets.';
    $('run').disabled = true;
    return;
  }
  const ATTACK = "' OR 1=1 --";
  const modeNames = {concat:'Склейка SQL', filter:'Запрет кавычки', bind:'Значение отдельно'};
  const stageNames = ['Обычный поиск','Другой ввод','Причина','Исправление','Проверка'];
  const stages = [
    {
      title:'Сначала проверим обычный поиск', term:'RAII', mode:'concat',
      copy:'Начнём с известного названия и убедимся, что понимаем нормальную работу поиска.',
      context:['В блоке «Попробуй поиск» находятся поле и ответ, который увидит посетитель. Рядом показана SQL-команда, которую подготовил обработчик. Пока не нужно разбирать каждое её слово.', '`SELECT id, title, is_public` перечисляет нужные поля, а `FROM lessons` указывает таблицу. Часть после `WHERE` задаёт отбор строк: `is_public = 1` требует публикацию, `title = \'RAII\'` — совпадение названия. `AND` означает «и»: нужны оба условия. Название внутри SQL заключено в одинарные кавычки.'],
      action:'Оставь RAII в поле «Название материала» и нажми «Найти». Остальные кнопки сейчас не нужны.',
      expectation:'В каталоге есть один опубликованный материал RAII. В ответе должна быть одна строка; черновиков быть не должно.',
      hint:'Можно свериться с таблицей в начале страницы: у RAII признак публикации равен 1. Поиск не ищет вхождение части слова — название должно совпасть целиком.',
      explanation:'Что показал обычный поиск',
      paragraphs:['Один обычный запрос помогает проверить, что поиск вообще работает. Следующий опыт проверит другое: останется ли текст из поля поиска только названием.']
    },
    {
      title:'Теперь изменим только текст поиска', term:ATTACK, mode:'concat',
      copy:'В поле подставлен необычный текст: \' OR 1=1 --. Сейчас воспринимай его как ещё одно название. Как он устроен, разберём на следующем шаге.',
      context:['В исходной таблице материала с таким названием нет. Мы не меняли правило публикации и не редактировали данные. Поэтому правильный поиск должен вернуть пустой ответ, независимо от того, какие слова введены в поле.'],
      action:'Нажми «Найти» с уже подставленным учебным вводом. Сравни ответ с таблицей в начале страницы.',
      expectation:'По требованиям должно быть 0 совпадений. Если увидишь материалы и черновики, это нарушение условия, а не правильная работа поиска.',
      hint:'Кнопка «Учебный ввод» подставляет этот же текст, если ты успел изменить поле. Она не выполняет поиск: после неё всё равно нужен «Найти».',
      explanation:'Ожидаем пустой ответ. Проверяем, так ли это.',
      paragraphs:['Изменяем только название; правило публикации должно остаться прежним. Если ответ содержит черновики, клиент повлиял не только на искомое значение, но и на смысл SQL-команды.']
    },
    {
      title:'Разберём, почему появились черновики', term:ATTACK, mode:'concat',
      copy:'Теперь сопоставим результат поиска с показанной SQL-командой. Если ответа ещё нет, нажми «Найти»: здесь уже подставлен тот же учебный ввод.',
      context:['Начальная программа склеивает (объединяет в одну строку) свой SQL и введённое название. Но первая кавычка из нашего ввода закрыла название раньше, чем рассчитывал автор программы. Следующий текст оказался уже частью команды, а не частью названия.', '`OR` означает «или», а `1=1` — всегда истинное условие. В получившейся команде этого достаточно, чтобы пропустить каждую строку. Два дефиса `--` начинают SQL-комментарий: оставшийся текст до конца строки команды не выполняется.', 'Это SQL-инъекция: пользовательский ввод изменил структуру SQL-команды. Мы не сделали черновики опубликованными. Изменился отбор строк, поэтому база вернула лишние данные. Точное выражение с приоритетами `AND` и `OR` разобрано в подробностях внизу.'],
      action:'Посмотри на выделенный ввод внутри SQL и на ответ приложения. Не нужно менять другие поля. Если ответа нет, нажми «Найти».',
      expectation:'Для этого учебного ввода уязвимая версия возвращает все 6 строк. Среди них два черновика, хотя по условию не должно быть ни одного совпадения.',
      hint:'Для этого конкретного ввода условие имеет смысл (is_public = 1 AND title = \'\') OR 1=1. AND связывает сильнее OR. Правая часть истинна даже для черновика.',
      explanation:'Откуда взялся новый смысл команды?',
      paragraphs:['Склейка (объединение строк текста) собрала SQL и пользовательское значение в одну команду. Движок не знает, какую часть текста автор хотел считать «просто названием». Он разбирает всю полученную команду по правилам SQL.', 'Для показанного ввода получается (is_public = 1 AND title = \'\') OR 1=1. А -- начинает комментарий до конца строки запроса, включая дописанную обработчиком кавычку. Переносы в блоке SQL только визуальные.']
    },
    {
      title:'Сравним два способа исправления', term:ATTACK, mode:'filter',
      copy:'Теперь меняем не данные, а обработчик поиска. Ниже три варианта: исходный и два изменения. Сначала выбран запрет символа кавычки.',
      context:['Простой запрет остановит показанный ввод до обращения к базе. Но в каталоге есть допустимое название O\'Reilly с такой же кавычкой. Исправление не должно ломать обычный поиск.', 'Другой вариант — SQL-параметр: обозначенное место для значения в заранее заданной команде. Здесь это `$term`. Само название передаётся отдельно, а не дописывается в SQL. При выборе этого способа справа будут показаны две вещи: команда и отдельное значение.'],
      action:'При запрете кавычки нажми «Найти» с учебным вводом. Потом подставь O\'Reilly и повтори поиск. Затем выбери «Передать значение отдельно» и проверь те же два текста.',
      expectation:'Запрет остановит оба текста, в том числе допустимое название. При передаче параметром O\'Reilly должен находиться, а для учебного ввода должен получаться пустой ответ.',
      hint:'SQL-параметр — место для значения в заранее заданной команде. Здесь это $term. Сам текст передаётся отдельным вызовом; не нужно дописывать его в SQL и окружать SQL-кавычками.',
      explanation:'Исправление должно сохранять нужные возможности.',
      paragraphs:['В этой задаче кавычка разрешена внутри названия: в каталоге действительно есть O\'Reilly. Политика «отклонять любую кавычку» поэтому нарушает требования, даже если остановила один показанный пример.', 'SQL-параметр — место для значения в заранее заданной команде. Здесь это $term: вместо подстановки текста в команду приложение передаёт всё название отдельным вызовом API. Это решает именно проблему смешения значения со структурой SQL.']
    },
    {
      title:'Проверим исправленный поиск', term:ATTACK, mode:'bind',
      copy:'Здесь выбран обработчик с отдельным параметром. Вместо ручного перебора запустим один и тот же набор проверок: для каждого текста зададим правильный ответ и сравним с тем, что вернула база.',
      context:['RAII и O\'Reilly должны давать по одному опубликованному совпадению. Материала с учебным вводом и несуществующего названия в каталоге нет — для них нужны пустые ответы.', 'Число пройденных проверок показывает, сколько требований поиска выполнено в этих примерах. Это не процент безопасности: например, запрет кавычки остановил показанный ввод, но отказал и допустимому названию.'],
      action:'Нажми «Запустить проверки» в блоке ниже. Прочитай не только итог, но и объяснение каждой строки. При желании выбери другой обработчик и повтори тот же набор.',
      expectation:'У варианта с параметром должны пройти все 4 проверки. Обычная работа сохраняется, а показанный ввод больше не меняет SQL-условие.',
      hint:'Для каждого допустимого текста требуется точный поиск среди опубликованных строк. Отказ от допустимого O\'Reilly — ошибка работы поиска. Выдача черновиков — нарушение правила публикации.',
      explanation:'У проверки есть положительные и отрицательные случаи.',
      paragraphs:['Обычные запросы должны продолжать работать. Ввод, похожий на SQL, должен обрабатываться как название, а не расширять условие. И ни один из этих запросов не должен показывать черновики.', 'Успех этих четырёх проверок подтверждает только данный учебный сценарий. Для настоящего сервиса отдельно нужны права доступа, ограничения ресурсов, обработка ошибок и проверки других путей к данным.']
    }
  ];
  let stage = 0, mode = 'concat', activeTab = 'sql';
  let worker = null, workerURL = null, timer = null, epoch = 0, pendingKind = null;
  let lastResult = null, lastChecks = null;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }
  function text(value) { return document.createTextNode(String(value)); }
  function teachingParagraph(value) {
    const paragraph = element('p');
    const pattern = /`([^`]+)`/g;
    let cursor = 0, match;
    while ((match = pattern.exec(value))) {
      paragraph.append(text(value.slice(cursor,match.index)),element('code','',match[1]));
      cursor = pattern.lastIndex;
    }
    paragraph.append(text(value.slice(cursor)));
    return paragraph;
  }
  function rowKind(row) {
    // Free exploration can produce computed rows via UNION. A returned flag
    // alone is not evidence that a result is a stored catalog record.
    const source = model.fixture.find(original => original.id === row.id &&
      original.title === row.title && original.is_public === row.is_public);
    return source ? (source.is_public === 1 ? 'public' : 'private') : 'unknown';
  }
  function renderFollowup() {
    $('after-run-next').hidden = !lastResult || stage === stages.length-1;
    $('after-run-next').textContent = stage < stages.length-1
      ? 'Дальше: ' + stageNames[stage+1].toLowerCase() + ' →' : 'Разбор завершён';
  }
  function setStatus(message, kind) {
    $('status').textContent = message;
    $('status').className = kind || '';
  }
  function busy(value) {
    $('run').disabled = value;
    $('check').disabled = value;
    $('stop').hidden = !value;
    $('experiment').setAttribute('aria-busy', value ? 'true' : 'false');
    $('checks-results').setAttribute('aria-busy', value ? 'true' : 'false');
  }
  function release() {
    if (timer !== null) clearTimeout(timer);
    timer = null;
    if (worker) worker.terminate();
    worker = null;
    if (workerURL) URL.revokeObjectURL(workerURL);
    workerURL = null; pendingKind = null;
    busy(false);
  }
  function cancel() { epoch++; release(); }
  function path(where, blocked) {
    ['input','handler','db','result'].forEach(name => {
      $('path-' + name).className = 'path-node' + (name === where ? (blocked ? ' blocked' : ' active') : '');
    });
  }
  function emptyResults(message) {
    const box = element('div', 'empty-state');
    const icon = element('span', '', '⌕'); icon.setAttribute('aria-hidden','true');
    box.append(icon, element('p', '', message));
    $('results').replaceChildren(box);
    $('response-count').textContent = 'Запрос ещё не выполнен';
    $('result-note').textContent = 'Ответ появится после выполнения запроса.';
    $('result-note').className = 'result-note';
  }
  function clearChecks() {
    lastChecks = null;
    $('checks-results').replaceChildren(element('p','checks-placeholder','Пока нет результатов для выбранного способа обработки.'));
    $('checks-summary').textContent = 'Это проверки конкретного сценария, не полный аудит безопасности.';
  }
  function unfinished(kind, message) {
    if (kind === 'checks') {
      clearChecks();
      $('checks-results').replaceChildren(element('p','checks-placeholder',message));
    } else {
      emptyResults(message);
      $('response-count').textContent = 'Запуск не завершён';
      $('result-note').textContent = 'Для этой попытки результат не получен. Можно повторить запуск.';
    }
    renderInspector();
  }
  function invalidate(message) {
    cancel(); lastResult = null; clearChecks();
    emptyResults('Ввод или обработчик изменился. Нажми «Найти», чтобы получить новый ответ.');
    path('input');
    if (message) setStatus(message);
    renderInspector(); renderExplanation();
  }
  function renderSQL(query) {
    const host = $('sql-code'); host.replaceChildren();
    if (query.rejected) {
      host.textContent = 'SQL не передаётся движку.\n' + query.message;
      return;
    }
    if (query.mode === 'bind') {
      const at = query.sql.indexOf('$term');
      host.append(text(query.sql.slice(0,at)),element('span','parameter-token','$term'),text(query.sql.slice(at+5)));
    } else {
      // Highlight provenance, not an invented SQL parse: the highlighted bytes
      // are exactly the input inserted between the author's two quotes.
      const at = query.sql.indexOf("'" + query.term + "'") + 1;
      if (at > 0) host.append(text(query.sql.slice(0,at)),element('span','input-token',query.term),text(query.sql.slice(at+query.term.length)));
      else host.textContent = query.sql;
    }
  }
  function renderInspector() {
    const term = $('search-term').value;
    const query = model.buildQuery(term,mode);
    const bound = mode === 'bind';
    $('input-count').textContent = model.byteLength(term) + ' / 120 байт';
    $('search-term').setAttribute('aria-invalid',query.rejected ? 'true' : 'false');
    $('mode-badge').textContent = modeNames[mode];
    $('mode-badge').className = 'mode-badge' + (bound ? ' bound' : '');
    $('query-state').textContent = lastResult ? (lastResult.query.rejected ? 'Отклонён до SQLite' : lastResult.error ? 'Ошибка выполнения' : 'Выполнен') : 'До выполнения';
    $('sql-caption').textContent = bound ? 'Неизменный SQL-шаблон' : 'SQL-текст, который получит движок';
    renderSQL(query);
    $('parameter-box').hidden = !bound || query.rejected;
    // Literal text only: input must never be parsed as HTML or executed by JS.
    $('parameter-value').textContent = JSON.stringify(term);
    $('boundary-note').className = 'boundary-note' + (bound ? ' bound' : '');
    $('boundary-copy').textContent = query.rejected ? query.message : bound
      ? 'Шаблон и значение передаются раздельно. Даже кавычки и слова SQL внутри значения не дописывают новое условие.'
      : 'Подсветка показывает происхождение текста, не его тип в SQL. Ввод вставлен в команду и может изменить её структуру.';
    let cpp;
    if (bound) {
      cpp = 'auto stmt = prepare(db,\n'
        + '    "SELECT id, title, is_public FROM lessons "\n'
        + '    "WHERE is_public = 1 AND title = $term "\n'
        + '    "ORDER BY id;");\n\n'
        + 'check(db, sqlite3_bind_text(stmt.get(), 1,\n'
        + '    term.c_str(), static_cast<int>(term.size()),\n'
        + '    SQLITE_TRANSIENT), "bind_text");';
      $('cpp-note').textContent = 'Фрагмент из полной программы. prepare и check — её вспомогательные функции с проверкой ошибок. stmt владеет подготовленным запросом. SQLITE_TRANSIENT просит SQLite скопировать текст до возврата из bind; затем строки читают через sqlite3_step.';
    } else {
      cpp = (mode === 'filter'
        ? 'if (term.find(\'\\\'\') != std::string::npos)\n    return reject_input(); // Отклонит и O\'Reilly.\n\n' : '')
        + 'const std::string sql =\n'
        + '    "SELECT id, title, is_public FROM lessons "\n'
        + '    "WHERE is_public = 1 AND title = \'" + term +\n'
        + '    "\' ORDER BY id;";\n\n'
        + 'auto stmt = prepare(db, sql.c_str());';
      $('cpp-note').textContent = 'Поясняющий фрагмент, не полная программа. Сам вызов prepare не устраняет инъекцию: если ввод уже вклеен в SQL, движок подготовит изменённую команду. reject_input обозначает отказ обработчика. Скачиваемая программа показывает исправленный вариант.';
    }
    $('cpp-code').textContent = cpp;
    try {
      $('http-code').textContent = 'GET /search?title=' + encodeURIComponent(term) + ' HTTP/1.1\nHost: catalog.example.test\n\nПосле декодирования title = ' + JSON.stringify(term);
    } catch (_) {
      $('http-code').textContent = 'Пример HTTP-запроса не построен: строка содержит некорректную последовательность UTF-16.\nЭтот ввод также не передаётся SQLite.';
    }
    ['concat','filter','bind'].forEach(name => $('mode-'+name).setAttribute('aria-pressed',name === mode ? 'true' : 'false'));
    const modeCopy = {
      concat:'Название дописывается прямо в SQL-команду. Поэтому введённый текст может изменить условие поиска.',
      filter:'Этот учебный фильтр запрещает одну кавычку. Он остановит показанный ввод, но одновременно откажет в поиске допустимого O\'Reilly. Это намеренно неполное исправление.',
      bind:'В команде заранее задан параметр $term. Название передаётся отдельно и не дописывается в SQL. Правило is_public = 1 остаётся частью запроса.'
    };
    $('mode-explanation').textContent = modeCopy[mode];
    [['normal','RAII'],['quote',"O'Reilly"],['attack',ATTACK]].forEach(([id,value]) => $('preset-'+id).setAttribute('aria-pressed',term === value ? 'true' : 'false'));
  }
  function renderExplanation() {
    let title = stages[stage].explanation;
    let paragraphs = stages[stage].paragraphs;
    let attention = false;
    if (lastResult) {
      if (lastResult.query.rejected) {
        title = 'Отказ произошёл до выполнения SQL.';
        paragraphs = [lastResult.query.message,
          'Отказ сам по себе ещё не доказывает корректность поиска. Переключись на обычное название с кавычкой, а затем сравни другой способ обработки.'];
        attention = true;
      } else if (lastResult.error) {
        title = 'SQLite не смогла выполнить полученную команду.';
        paragraphs = ['Переданный текст привёл к ошибке SQL. Это наблюдение об этой попытке, а не доказательство защиты от других входов. Посмотри, какой SQL построил обработчик.',
          'В реальном приложении диагностику такого уровня оставляют в защищённой среде разработчика; публичный ответ не должен раскрывать SQL и внутреннее устройство базы.'];
        attention = true;
      } else if (lastResult.rows.some(row => rowKind(row) === 'private')) {
        title = 'В ответ попали строки, которых здесь быть не должно.';
        paragraphs = ['Движок действительно вернул черновики. Условие публикации было записано в исходном SQL, но склеенный с ним ввод изменил смысл команды.',
          lastResult.query.term === ATTACK
            ? 'Часть ввода стала новым условием «или 1=1». Получившаяся команда пропускает каждую строку. Мы не меняли признак публикации в базе — изменилось правило отбора.'
            : 'Сравни полученную команду с исходным правилом отбора. Результат рассчитан SQLite, а не выбран по совпадению с заранее известной строкой ввода.'];
        attention = true;
      } else if (lastResult.rows.some(row => rowKind(row) === 'unknown')) {
        title = 'В ответе есть строки, не совпадающие с исходной таблицей.';
        paragraphs = ['Изменённая SQL-команда может возвращать и вычисленные значения. Поэтому мы не называем такую строку опубликованным материалом или черновиком только по одному полю ответа.', 'Сверь номер, название и признак публикации с исходными данными. Этот вывод не заменяет проверку прав доступа настоящего сервиса.'];
        attention = true;
      } else if (mode === 'bind') {
        title = lastResult.rows.length ? 'Значение найдено без изменения команды.' : 'Ввод остался значением, совпадений нет.';
        paragraphs = ['SQL-шаблон содержит $term, а не подставленный текст. Движок сравнивает title с переданным значением целиком. Кавычки и SQL-слова в значении не добавляют новые условия.',
          'Это результат данного запроса. Для проверки исправления нужно также убедиться, что обычный поиск работает и другие случаи не возвращают черновики.'];
      } else {
        title = lastResult.query.term === 'RAII' && lastResult.rows.length
          ? 'Обычный поиск сработал. Что это доказывает?'
          : lastResult.rows.length ? 'Запрос вернул строки. Совпадают ли они с искомым названием?' : 'Запрос не вернул строк.';
        paragraphs = lastResult.query.term === 'RAII'
          ? ['Вернулся опубликованный материал RAII. Для этого названия сработали оба условия: материал опубликован и название совпадает.', 'Теперь проверим, сохранится ли правило публикации при необычном вводе. Для этого перейди к следующему этапу.']
          : ['Это результат данной попытки. Сравни его с точным названием и правилом публикации. Одна удачная попытка ещё не проверяет, отделено ли введённое значение от структуры SQL.'];
      }
    }
    $('explanation-title').textContent = title;
    $('explanation-body').replaceChildren(...paragraphs.map(teachingParagraph));
    $('explanation-panel').className = 'explanation' + (attention ? ' attention' : '');
    $('explanation-panel').hidden = !lastResult;
    renderFollowup();
  }
  function renderResult(result) {
    $('results').replaceChildren();
    const query = result.query;
    if (query.rejected || result.error) {
      const box = element('div','result-error',query.rejected ? 'Обработчик отклонил ввод. Запрос в SQLite не выполнялся.' : 'SQLite вернула ошибку.');
      box.append(element('code','',result.error || query.message)); $('results').append(box);
      $('response-count').textContent = query.rejected ? 'Отказ до базы' : 'Ошибка SQL';
      $('result-note').textContent = 'Учебная диагностика: в настоящем публичном API подробности ошибки скрывают.';
      $('result-note').className = 'result-note warning';
      path(query.rejected ? 'handler' : 'db',true);
    } else {
      if (!result.rows.length) {
        const box = element('div','empty-state');
        box.append(element('span','','∅'),element('p','','Совпадений нет. Ни одна строка не прошла условие этого запроса.'));
        $('results').append(box);
      }
      result.rows.forEach(row => {
        const item = element('div','result-item');
        const kind = rowKind(row);
        const label = kind === 'public' ? 'Опубликовано' : kind === 'private' ? 'Черновик' : 'Другая строка';
        item.append(element('span','result-id',row.id),element('span','result-title',row.title),element('span','visibility'+(kind === 'public' ? '' : ' '+kind),label));
        $('results').append(item);
      });
      const privateCount = result.rows.filter(row => rowKind(row) === 'private').length;
      const unknownCount = result.rows.filter(row => rowKind(row) === 'unknown').length;
      $('response-count').textContent = 'Строк: ' + result.rows.length;
      $('result-note').textContent = privateCount
        ? 'Нарушение условия: в ответе есть неопубликованные строки (' + privateCount + ').' + (result.truncated ? ' Показ результата ограничен.' : '')
        : unknownCount ? 'В ответе есть строки, не совпадающие с исходными записями. Сверь их с таблицей в начале страницы.'
        : result.truncated ? 'Показ результата ограничен. Не считай такой ответ полной проверкой запроса.'
        : 'Каждая возвращённая строка совпадает с опубликованной записью исходного каталога.';
      $('result-note').className = 'result-note' + (privateCount || unknownCount || result.truncated ? ' warning' : '');
      path('result',privateCount > 0 || unknownCount > 0);
    }
    if (result.engineVersion) $('engine-version').textContent = 'SQLite ' + result.engineVersion + ' · sql.js 1.13.0';
    renderInspector(); renderExplanation();
  }
  function renderChecks(checks, checkedMode) {
    lastChecks = {checks,mode:checkedMode};
    $('checks-results').replaceChildren();
    checks.forEach(check => {
      const row = element('div','check-row' + (check.passed ? '' : ' failed'));
      const copy = element('div'); copy.append(element('strong','',check.label));
      let detail;
      if (check.rejected) detail = 'Ввод отклонён, хотя задача требует поиск по этому тексту как по названию.';
      else if (check.error) detail = 'Вместо результата поиска получена ошибка SQL.';
      else if (check.unexpectedPrivate) detail = 'В результат попали черновики. Ожидалось пустое совпадение.';
      else detail = 'Ввод: ' + JSON.stringify(check.term) + ' · ожидается строк: ' + check.expectedRows.length + ' · получено: ' + check.actualRows.length + '.';
      copy.append(element('p','',detail));
      row.append(element('span','check-mark',check.passed ? '✓' : '×'),copy,element('span','check-verdict',check.passed ? 'Совпало с ожиданием' : 'Требование не выполнено'));
      $('checks-results').append(row);
    });
    const passed = checks.filter(check => check.passed).length;
    $('checks-summary').textContent = modeNames[checkedMode] + ': пройдено ' + passed + ' из ' + checks.length + ' учебных проверок требований поиска. Это не процент безопасности и не полный аудит сервиса.';
    setStatus('Для варианта «' + modeNames[checkedMode] + '» пройдено ' + passed + ' из ' + checks.length + ' проверок.',passed === checks.length ? 'success' : 'error');
  }
  function start(kind) {
    cancel();
    const id = epoch, term = $('search-term').value, selectedMode = mode;
    if (kind === 'run') {
      lastResult = null;
      const query = model.buildQuery(term, selectedMode);
      if (query.rejected) {
        lastResult = {query,rows:[],error:query.message,truncated:false,engineVersion:null};
        renderResult(lastResult); setStatus(query.message,'error'); return;
      }
      emptyResults('Выполняем именно этот запрос на исходных учебных данных…');
      renderInspector(); renderExplanation();
    } else clearChecks();
    try {
      if (typeof window.SECURITY_SQL_WORKER_SOURCE !== 'string') throw new Error('Нет локального worker bundle.');
      workerURL = URL.createObjectURL(new Blob([window.SECURITY_SQL_WORKER_SOURCE],{type:'text/javascript'}));
      worker = new Worker(workerURL);
    } catch (_) {
      release(); path('handler',true);
      unfinished(kind,'Локальный исполнитель не запустился. Результат не получен.');
      setStatus('Не удалось создать локальный SQL-worker. Проверь наличие generated/security-sql-worker.data.js и поддержку Web Worker в браузере.','error');
      return;
    }
    const ownWorker = worker;
    pendingKind = kind;
    busy(true); path('handler');
    setStatus(kind === 'checks' ? 'Готовим четыре независимые проверки…' : 'Создаём свежую базу SQLite в памяти…');
    function timeout() {
      if (epoch !== id || worker !== ownWorker) return;
      cancel(); path('db',true);
      unfinished(kind,'Исполнитель остановлен по лимиту времени. Результат не получен.');
      setStatus('Превышен учебный лимит времени. Исполнитель остановлен; следующий запуск получит новую базу.','error');
    }
    timer = setTimeout(timeout,10000);
    ownWorker.onmessage = event => {
      if (epoch !== id || worker !== ownWorker) return;
      const message = event.data;
      if (!message || message.id !== id) return;
      if (message.type === 'ready') {
        clearTimeout(timer); timer = setTimeout(timeout,3000); path('db');
        setStatus(kind === 'checks' ? 'SQLite выполняет четыре проверки…' : 'SQLite разбирает и выполняет запрос…'); return;
      }
      if (!['result','checks','error'].includes(message.type)) return;
      release();
      if (message.type === 'error') {
        unfinished(kind,'Исполнитель сообщил об ошибке. Результат не получен.');
        path('db',true); setStatus('Ошибка учебного исполнителя: ' + String(message.message || 'без подробностей').slice(0,200),'error'); return;
      }
      if (kind === 'checks' && message.type === 'checks') {
        renderChecks(message.checks,selectedMode); path('result');
      } else if (kind === 'run' && message.type === 'result') {
        lastResult = message.result; renderResult(lastResult);
        setStatus(lastResult.error ? 'Попытка завершилась отказом или ошибкой. Причина показана рядом с результатом.' : 'Запрос выполнен настоящим SQLite. Сравни ответ с правилом публикации.',lastResult.error ? 'error' : '');
      } else {
        unfinished(kind,'Исполнитель вернул ответ другого типа. Повтори запуск.');
        setStatus('Исполнитель вернул неожиданный ответ. Повтори запуск.','error');
      }
    };
    ownWorker.onerror = () => {
      if (epoch !== id || worker !== ownWorker) return;
      cancel(); unfinished(kind,'Исполнитель завершился с ошибкой. Результат не получен.'); path('db',true);
      setStatus('Исполнитель SQLite завершился с ошибкой. Следующий запуск начнётся на свежей базе.','error');
    };
    try { ownWorker.postMessage({id,type:kind,term,mode:selectedMode}); }
    catch (_) { cancel(); unfinished(kind,'Не удалось передать запрос исполнителю. Результат не получен.'); path('handler',true); setStatus('Не удалось передать запрос локальному исполнителю. Повтори запуск.','error'); }
  }
  function setStage(index, focus) {
    if (index < 0 || index >= stages.length) return;
    stage = index; const current = stages[stage];
    const preserveResult = lastResult && pendingKind === null &&
      lastResult.query.term === current.term && lastResult.query.mode === current.mode;
    mode = current.mode; $('search-term').value = current.term;
    if (preserveResult) {
      cancel(); clearChecks(); renderResult(lastResult);
      setStatus('Ответ предыдущего опыта сохранён: название и обработчик не изменились.');
    } else invalidate('Этап ' + (stage+1) + ': ' + stageNames[stage] + '.');
    $('guide-title').textContent = current.title;
    $('guide-copy').textContent = current.copy;
    $('guide-context').replaceChildren(...current.context.map(teachingParagraph));
    $('guide-action').textContent = current.action;
    $('guide-expectation').textContent = current.expectation;
    $('hint-copy').textContent = current.hint;
    $('guide-hint').open = false;
    $('guide-index').textContent = String(stage+1).padStart(2,'0');
    for (let i=0;i<stages.length;i++) {
      if (i === stage) $('stage-'+i).setAttribute('aria-current','step');
      else $('stage-'+i).removeAttribute('aria-current');
    }
    $('fix-panel').hidden = stage < 3;
    $('checks-panel').hidden = stage < 4;
    $('previous').disabled = stage === 0;
    $('next').hidden = stage === stages.length-1;
    $('restart').hidden = stage !== stages.length-1;
    $('next').textContent = stage < stages.length-1 ? 'Дальше: ' + stageNames[stage+1].toLowerCase() + ' →' : 'Дальше →';
    $('stage-position').textContent = 'Этап ' + (stage+1) + ' из ' + stages.length;
    $('technical-details').open = false;
    tab('sql',false);
    renderFollowup();
    if (focus) $('guide-title').focus();
  }
  function choosePreset(value) {
    $('search-term').value = value;
    invalidate('Пример подставлен. Предскажи ответ, затем нажми «Найти».');
    $('search-term').focus();
  }
  function chooseMode(value) {
    if (!model.modes.includes(value)) return;
    mode = value;
    invalidate('Способ обработки изменён: ' + modeNames[mode] + '. Повтори поиск или проверки.');
  }
  function tab(name, focus) {
    activeTab = name;
    if (name !== 'sql') $('technical-details').open = true;
    ['sql','cpp','http'].forEach(value => {
      const selected = value === name;
      $('tab-'+value).setAttribute('aria-selected', selected ? 'true' : 'false');
      $('tab-'+value).setAttribute('tabindex', selected ? '0' : '-1');
      $('view-'+value).hidden = !selected;
    });
    if (focus) $('tab-'+name).focus();
  }
  function fixtureTable() {
    const table = element('table');
    const head = element('thead'), header = element('tr');
    ['№','Название','Публикация'].forEach(value => {const th=element('th','',value);th.setAttribute('scope','col');header.append(th);});
    head.append(header);table.append(head);
    const body = element('tbody');
    model.fixture.forEach(row => {const tr=element('tr');[row.id,row.title,row.is_public === 1 ? 'Опубликовано' : 'Черновик'].forEach(value=>tr.append(element('td','',value)));body.append(tr);});
    table.append(body);$('fixture-table').append(table);
  }
  for (let i=0;i<stages.length;i++) $('stage-'+i).addEventListener('click',()=>setStage(i,true));
  ['concat','filter','bind'].forEach(name => $('mode-'+name).addEventListener('click',()=>chooseMode(name)));
  [['normal','RAII'],['quote',"O'Reilly"],['attack',ATTACK]].forEach(([id,value])=>$('preset-'+id).addEventListener('click',()=>choosePreset(value)));
  ['sql','cpp','http'].forEach(name => {
    $('tab-'+name).addEventListener('click',()=>tab(name,false));
    $('tab-'+name).addEventListener('keydown',event => {
      const keys = ['ArrowRight','ArrowLeft','Home','End'];
      if (!keys.includes(event.key)) return;
      event.preventDefault(); const names=['sql','cpp','http'];
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (names.indexOf(activeTab)+(event.key === 'ArrowRight' ? 1 : 2))%3;
      tab(names[next],true);
    });
  });
  $('search-form').addEventListener('submit',event=>{event.preventDefault();start('run');});
  $('search-term').addEventListener('input',()=>invalidate('Ввод изменён. Нажми «Найти», чтобы выполнить новый запрос.'));
  $('check').addEventListener('click',()=>start('checks'));
  $('stop').addEventListener('click',()=>{const kind=pendingKind;cancel();unfinished(kind,'Запуск остановлен пользователем. Результат не получен.');path('handler',true);setStatus('Запуск остановлен. Ни один следующий запрос не использует его базу.');});
  $('previous').addEventListener('click',()=>setStage(stage-1,true));
  $('next').addEventListener('click',()=>setStage(stage+1,true));
  $('after-run-next').addEventListener('click',()=>setStage(stage+1,true));
  $('technical-details').addEventListener('toggle',()=>{if (!$('technical-details').open) tab('sql',false);});
  $('restart').addEventListener('click',()=>{tab('sql',false);setStage(0,true);});
  window.addEventListener('pagehide',cancel);
  fixtureTable(); setStage(0,false); tab('sql',false);
})();
