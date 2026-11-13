(function () {
  'use strict';
  var api = window.CourseProgress;
  var pending = null;
  var version = '';
  function el(id) { return document.getElementById(id); }
  function say(id, text) { el(id).textContent = text; }
  function errorText(error) { return error && error.message ? error.message : String(error); }
  function exportSnapshot() { return api.exportSnapshot(localStorage, { origin: location.origin, version: version }); }
  function download(snapshot, prefix) {
    var url = URL.createObjectURL(new Blob([JSON.stringify(snapshot, null, 2) + '\n'], { type: 'application/json' }));
    var link = document.createElement('a');
    link.href = url;
    link.download = (prefix || 'cpp-course-progress') + '-' + new Date().toISOString().slice(0, 10) + '.json';
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 30000);
  }
  fetch('desktop-meta.json').then(function (response) { if (!response.ok) throw new Error('metadata'); return response.json(); })
    .then(function (data) { version = data.version; say('app-version', 'Версия приложения: ' + data.applicationVersion + '. Станций в локальной копии: ' + data.stationCount + '. Все учебные файлы уже входят в установку.'); })
    .catch(function () { el('app-status').dataset.error = 'true'; say('app-version', 'Не удалось прочитать сведения о сборке. Главы могут оставаться доступны; переустанови пакет, если файлы приложения повреждены. Прогресс не очищай.'); });
  var back = new URLSearchParams(location.search).get('return');
  if (back) {
    try {
      var url = new URL(back, location.href);
      if (url.protocol === location.protocol && url.host === location.host && url.pathname.startsWith('/roadmap/') && url.pathname.endsWith('.html')) {
        el('progress-return').href = url.href; el('progress-return').hidden = false;
      }
    } catch (_) {}
  }
  el('progress-export').addEventListener('click', function () {
    try { var data = exportSnapshot(); download(data); say('export-message', 'Файл подготовлен. Записей: ' + Object.keys(data.entries).length.toLocaleString('ru-RU') + '. Выбери место сохранения; отметки в приложении не изменены.'); }
    catch (error) { say('export-message', errorText(error)); }
  });
  el('progress-file').addEventListener('change', async function () {
    pending = null; el('progress-import').hidden = true; el('import-preview').hidden = true;
    var oldConfirm = el('progress-confirm-import'); if (oldConfirm) oldConfirm.remove();
    say('import-message', '');
    var file = el('progress-file').files[0]; if (!file) return;
    try {
      if (file.size > api.MAX_BYTES) throw new Error('Файл больше 4 МБ. Выбери резервную копию курса.');
      var data = JSON.parse(await file.text()); var count = api.validateSnapshot(data);
      pending = data;
      say('import-preview', 'Файл прошёл проверку. Записей: ' + count.toLocaleString('ru-RU') + '. Одноимённые данные будут заменены только после подтверждения.');
      el('import-preview').hidden = false; el('progress-import').hidden = count === 0;
      if (!count) say('import-message', 'В файле нет прогресса. Ничего не изменено.');
    } catch (error) { say('import-message', errorText(error)); }
  });
  el('progress-import').addEventListener('click', function () {
    if (!pending) return;
    if (!confirm('Перед восстановлением сохрани нынешний прогресс: сейчас откроется выбор файла резервной копии. Затем подтверди восстановление отдельно. Закрой остальные окна курса. Продолжить?')) return;
    try { download(exportSnapshot(), 'cpp-course-before-import'); }
    catch (error) { say('import-message', errorText(error)); return; }
    // The renderer cannot know if a native save dialog was cancelled. Require
    // a second explicit confirmation rather than claiming the backup was saved.
    el('progress-import').hidden = true;
    var confirmButton = document.createElement('button'); confirmButton.type = 'button';
    confirmButton.id = 'progress-confirm-import'; confirmButton.textContent = 'Резервная копия сохранена — восстановить выбранный прогресс';
    el('progress-import').parentNode.appendChild(confirmButton);
    say('import-message', 'Сначала закончи сохранение резервной копии. Если отменил диалог, не продолжай восстановление.');
    confirmButton.addEventListener('click', function () {
      if (!pending) return;
      if (!confirm('Заменить одноимённые записи прогресса данными из выбранного файла?')) return;
      try {
        var count = api.importSnapshot(localStorage, pending);
        say('import-message', 'Восстановлено записей: ' + count.toLocaleString('ru-RU') + '. Открой главу заново, чтобы увидеть отметки.');
        pending = null; confirmButton.remove();
      } catch (error) { say('import-message', errorText(error)); }
    });
  });
  var bookmarklet = api.buildBookmarklet(); el('legacy-export').href = bookmarklet;
  el('legacy-copy').addEventListener('click', async function () {
    try { await navigator.clipboard.writeText(bookmarklet); say('legacy-message', 'Адрес скопирован. Создай в прежнем браузере закладку и вставь его в поле адреса.'); }
    catch (_) {
      el('legacy-label').hidden = false; el('legacy-address').hidden = false;
      el('legacy-address').value = bookmarklet; el('legacy-address').focus(); el('legacy-address').select();
      say('legacy-message', 'Автоматическое копирование недоступно. Адрес выделен в поле: нажми Ctrl+C и вставь его в адрес закладки прежнего браузера.');
    }
  });
})();
