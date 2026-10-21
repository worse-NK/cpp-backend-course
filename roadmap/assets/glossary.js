(function () {
  'use strict';
  const input = document.getElementById('term-search');
  if (!input) return;
  const entries = Array.from(document.querySelectorAll('.glossary-entry'));
  const buttons = Array.from(document.querySelectorAll('[data-group]')).filter(el => el.tagName === 'BUTTON');
  const normalize = text => text.toLocaleLowerCase('ru').replace(/ё/g, 'е');
  const records = entries.map(element => ({ element, text: normalize(element.textContent + ' ' + element.dataset.aliases) }));
  let group = '';
  function filter() {
    const words = normalize(input.value.trim()).split(/\s+/).filter(Boolean);
    let visible = 0;
    records.forEach(record => {
      const show = (!group || record.element.dataset.group === group) && words.every(word => record.text.includes(word));
      record.element.hidden = !show;
      if (show) visible++;
    });
    document.getElementById('term-empty').hidden = visible !== 0;
    document.getElementById('term-count').textContent = 'Показано понятий: ' + visible + ' из ' + entries.length;
    buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.group === group)));
  }
  function followHash() {
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch (_) { return; }
    const entry = document.getElementById(id);
    if (!entry || !entry.classList.contains('glossary-entry')) return;
    input.value = ''; group = ''; filter();
    entry.scrollIntoView({ block: 'start', behavior: 'auto' });
    entry.focus({ preventScroll: true });
  }
  document.querySelector('.glossary-search').hidden = false;
  input.addEventListener('input', filter);
  document.getElementById('term-search-clear').addEventListener('click', () => { input.value = ''; filter(); input.focus(); });
  buttons.forEach(button => button.addEventListener('click', () => { group = button.dataset.group; filter(); }));
  window.addEventListener('hashchange', followHash);
  document.addEventListener('click', event => {
    const anchor = event.target.closest && event.target.closest('a[href^="#term-"]');
    if (anchor && anchor.hash === location.hash && !event.ctrlKey && !event.metaKey && !event.shiftKey) { event.preventDefault(); followHash(); }
  });
  if (location.hash) followHash();
})();
