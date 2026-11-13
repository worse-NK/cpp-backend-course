(function () {
  'use strict';
  if (document.body.classList.contains('desktop-progress') || document.querySelector('meta[http-equiv="refresh"]')) return;
  var base = new URL('.', document.currentScript.src);
  var footer = document.createElement('footer');
  footer.className = 'desktop-course-footer';
  var link = document.createElement('a');
  var url = new URL('progress.html', base);
  url.searchParams.set('return', location.pathname + location.search + location.hash);
  link.href = url.href;
  link.textContent = 'Прогресс и приложение';
  footer.appendChild(link);
  document.body.appendChild(footer);
})();
