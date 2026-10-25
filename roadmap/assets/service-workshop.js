(function () {
  'use strict';
  var chapters = Array.from(document.querySelectorAll('.workshop-chapter'));
  var links = Array.from(document.querySelectorAll('.workshop-contents nav a'));
  var lastId = null;
  function selectChapter() {
    var id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch (_) { id = ''; }
    if (id === 'workshop-main' && lastId) {
      document.getElementById(lastId).focus();
      return;
    }
    var target = document.getElementById(id);
    var chapter = target && target.closest('.workshop-chapter');
    if (!chapter) chapter = chapters[0];
    chapters.forEach(function (item) { item.hidden = item !== chapter; });
    links.forEach(function (link) {
      if (link.hash === '#' + chapter.id) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    document.title = chapter.querySelector('h1').textContent + ' · Свой C++-сервис';
    if (lastId !== null && lastId !== chapter.id) {
      chapter.focus({preventScroll: true});
      window.scrollTo({top: 0, behavior: 'instant'});
    }
    lastId = chapter.id;
    if (target && target !== chapter) target.scrollIntoView();
  }
  document.querySelectorAll('.command pre').forEach(function (pre) {
    var button = document.createElement('button');
    button.type = 'button'; button.className = 'copy-code';
    button.textContent = 'Копировать';
    button.setAttribute('aria-label', 'Скопировать команды: ' + pre.parentNode.querySelector('.command-place').textContent);
    button.addEventListener('click', function () {
      if (!navigator.clipboard || !window.isSecureContext) {
        document.getElementById('workshop-status').textContent = 'Копирование недоступно: выделите команды вручную.';
        button.textContent = 'Выделите текст'; return;
      }
      navigator.clipboard.writeText(pre.textContent).then(function () {
        button.textContent = 'Скопировано';
        document.getElementById('workshop-status').textContent = 'Команды скопированы. Проверьте место выполнения и значения-заполнители.';
        setTimeout(function () { button.textContent = 'Копировать'; }, 2000);
      }, function () { button.textContent = 'Выделите текст'; });
    });
    pre.parentNode.appendChild(button);
  });
  window.addEventListener('hashchange', selectChapter);
  selectChapter();
}());
