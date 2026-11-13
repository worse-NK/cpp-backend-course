/* Progress transfer is deliberately independent of PWA registration.
   A backup is a user file, not a trusted program or an authenticated score. */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.CourseProgress = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function progressFactory() {
  'use strict';
  var FORMAT = 'cpp-backend-course-progress';
  var MAX_BYTES = 4 * 1024 * 1024;
  var MAX_VALUE = 1024 * 1024;
  var MAX_KEYS = 150;
  var exact = new Set([
    'cpp_roadmap_progress_v1', 'cpp_basic_progress_v1',
    'cpp_course_last_read_v1', 'cpp_course_text_size_v1',
    'cpp_station5_linux_progress_v1', 'cpp_station7_netlab_progress_v1',
    'cpp_station7_traffic_progress_v1', 'cpp_station9_sql_progress_v1'
  ]);
  for (var i = 0; i <= 16; i++) exact.add('cpp_station' + i + '_progress_v1');

  function allowedKey(key) {
    return typeof key === 'string' && (exact.has(key) || /^cpp-sql-lab:v1:[a-z][a-z0-9-]{0,79}$/.test(key));
  }
  function plain(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value)
      && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
  }
  function inspectTree(value, depth, budget) {
    if (depth > 24 || --budget.left < 0) throw new Error('В файле слишком сложные данные. Выбери резервную копию курса.');
    if (value === null || typeof value !== 'object') return;
    Object.keys(value).forEach(function (key) {
      if (key === '__proto__' || key === 'prototype' || key === 'constructor') {
        throw new Error('В файле есть недопустимое имя поля. Прогресс не изменён.');
      }
      inspectTree(value[key], depth + 1, budget);
    });
  }
  function validateValue(key, raw) {
    if (typeof raw !== 'string' || raw.length > MAX_VALUE) throw new Error('Некорректная или слишком большая запись: ' + key);
    if (key.indexOf('cpp-sql-lab:v1:') === 0) return;
    if (key === 'cpp_course_text_size_v1') {
      if (raw !== 'normal' && raw !== 'large') throw new Error('В файле указан неизвестный размер текста.');
      return;
    }
    var value;
    try { value = JSON.parse(raw); } catch (_) { throw new Error('Повреждены данные прогресса: ' + key); }
    if (!plain(value)) throw new Error('Ожидался объект прогресса: ' + key);
    inspectTree(value, 0, { left: 75000 });
    if (key === 'cpp_course_last_read_v1') {
      if (typeof value.file !== 'string' || !/^cpp_station[0-9][a-z0-9_]*\.html$/.test(value.file)
        || typeof value.section !== 'string' || !/^[a-z0-9-]{1,180}$/.test(value.section)
        || typeof value.title !== 'string' || value.title.length > 2000) {
        throw new Error('Некорректная ссылка на последний раздел. Прогресс не изменён.');
      }
    }
  }
  function validateSnapshot(snapshot) {
    if (!plain(snapshot) || snapshot.format !== FORMAT || snapshot.schemaVersion !== 1 || !plain(snapshot.entries)) {
      throw new Error('Это не поддерживаемая резервная копия курса. Нужен JSON-файл, сохранённый кнопкой «Сохранить прогресс».');
    }
    Object.keys(snapshot).forEach(function (key) {
      if (['format', 'schemaVersion', 'exportedAt', 'sourceOrigin', 'courseVersion', 'entries'].indexOf(key) < 0) {
        throw new Error('В файле есть неизвестное поле: ' + key);
      }
    });
    ['exportedAt', 'sourceOrigin', 'courseVersion'].forEach(function (key) {
      if (snapshot[key] !== undefined && (typeof snapshot[key] !== 'string' || snapshot[key].length > 2000)) {
        throw new Error('Некорректные сведения о резервной копии.');
      }
    });
    var keys = Object.keys(snapshot.entries);
    if (keys.length > MAX_KEYS) throw new Error('В файле слишком много записей. Прогресс не изменён.');
    var total = 0;
    keys.forEach(function (key) {
      if (!allowedKey(key)) throw new Error('Файл содержит данные, не относящиеся к курсу: ' + key);
      validateValue(key, snapshot.entries[key]);
      total += key.length + snapshot.entries[key].length;
    });
    if (total > MAX_BYTES) throw new Error('Резервная копия слишком большая. Прогресс не изменён.');
    if (new TextEncoder().encode(JSON.stringify(snapshot)).length > MAX_BYTES - 65536) {
      throw new Error('Резервная копия слишком большая. Прогресс не изменён.');
    }
    return keys.length;
  }
  function exportSnapshot(storage, metadata) {
    var entries = Object.create(null);
    for (var i = 0; i < storage.length; i++) {
      var key = storage.key(i);
      if (allowedKey(key)) {
        var value = storage.getItem(key);
        if (value !== null) entries[key] = value;
      }
    }
    var snapshot = {
      format: FORMAT, schemaVersion: 1, exportedAt: new Date().toISOString(),
      sourceOrigin: metadata && metadata.origin || '',
      courseVersion: metadata && metadata.version || '', entries: entries
    };
    validateSnapshot(snapshot);
    return snapshot;
  }
  function importSnapshot(storage, snapshot) {
    var count = validateSnapshot(snapshot);
    var keys = Object.keys(snapshot.entries);
    var previous = Object.create(null);
    keys.forEach(function (key) { previous[key] = storage.getItem(key); });
    try {
      keys.forEach(function (key) { storage.setItem(key, snapshot.entries[key]); });
    } catch (error) {
      var rollbackFailed = false;
      keys.forEach(function (key) {
        try {
          if (previous[key] === null) storage.removeItem(key);
          else storage.setItem(key, previous[key]);
        } catch (_) { rollbackFailed = true; }
      });
      var failure = new Error(rollbackFailed
        ? 'Браузер не сохранил все записи и не смог полностью вернуть прежние. Закрой другие окна курса и восстанови скачанную перед импортом копию.'
        : 'Браузер не смог сохранить импорт. Прежний прогресс восстановлен; проверь свободное место и разрешение на хранение данных.');
      failure.cause = error;
      failure.rollbackFailed = rollbackFailed;
      throw failure;
    }
    return count;
  }
  function buildBookmarklet() {
    // Embed the same validator/exporter, not a second hand-maintained allowlist.
    // The javascript: URL runs only when the reader explicitly invokes the bookmark.
    var program = '(function(){"use strict";var api=(' + progressFactory.toString() + ')();(' + legacyExport.toString() + ')(api);})()';
    return 'javascript:' + encodeURIComponent(program);
  }
  function legacyExport(api) {
    var github = location.origin === 'https://worse-nk.github.io'
      && location.pathname.indexOf('/cpp-backend-course/') === 0;
    var localFile = location.protocol === 'file:'
      && /\/(?:cpp_backend_roadmap|cpp_basic_level|cpp_station[0-9][a-z0-9_]*|sql_trainer)\.html$/.test(location.pathname);
    var oldPwa = location.origin === 'http://127.0.0.1:47653'
      && /^\/roadmap\/(?:cpp_backend_roadmap|cpp_basic_level|cpp_station[0-9][a-z0-9_]*|sql_trainer)\.html$/.test(location.pathname);
    if (!github && !localFile && !oldPwa) {
      alert('Открой прежнюю страницу учебника на worse-nk.github.io/cpp-backend-course/, HTML-файл станции или локальную PWA на 127.0.0.1:47653, затем снова нажми закладку. Данные не изменены.');
      return;
    }
    try {
      var data = api.exportSnapshot(localStorage, { origin: location.origin });
      if (!Object.keys(data.entries).length) {
        alert('На этой странице браузер не нашёл сохранённого прогресса курса. Проверь профиль браузера и прежний адрес. Если учился через file://, попробуй страницу нужной станции.');
        return;
      }
      var url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2) + '\n'], { type: 'application/json' }));
      var a = document.createElement('a'); a.href = url;
      a.download = 'cpp-course-progress-legacy-' + new Date().toISOString().slice(0, 10) + '.json';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 30000);
    } catch (error) { alert('Не удалось сохранить прогресс: ' + error.message + '. Данные не изменены.'); }
  }
  return { FORMAT: FORMAT, MAX_BYTES: MAX_BYTES, allowedKey: allowedKey,
    exportSnapshot: exportSnapshot, validateSnapshot: validateSnapshot, importSnapshot: importSnapshot,
    buildBookmarklet: buildBookmarklet };
});
