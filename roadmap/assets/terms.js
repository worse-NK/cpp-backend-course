/* Progressive enhancement: the original definitions stay readable without this file. */
(function () {
  'use strict';
  if (!window.COURSE_TERMS || !window.CourseTermsCore || !window.MutationObserver) return;
  const model = window.CourseTermsCore.create(window.COURSE_TERMS);
  const scopes = '[data-terms-scope],.reference-group';
  const paragraphs = '.theory-text,.note-text,.visual-item-text,.diagram-item p,.section-lead,.rule,[data-terms-prose],main[data-terms-scope] section p';
  let observer, pending = false, opener = null, popup = null;

  function texts(element) {
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    const nodes = []; let node, total = 0, value = '';
    while ((node = walker.nextNode())) {
      nodes.push({ node, start: total, end: total + node.nodeValue.length });
      value += node.nodeValue; total += node.nodeValue.length;
    }
    return { value, nodes };
  }
  function allowed(record, end) {
    if (!record || end > record.end) return false;
    const parent = record.node.parentElement;
    if (!parent || parent.closest('a,button,pre,script,style,textarea,select,[data-no-terms]')) return false;
    const code = parent.closest('code');
    // A standalone inline identifier may name a concept; a C++ expression is not prose.
    return !code || (code.textContent.trim() === record.node.nodeValue.trim() &&
      model.scan(code.textContent).some(m => m.start === 0 && m.end === code.textContent.length));
  }
  function enhance(scope) {
    const seen = new Set(Array.from(scope.querySelectorAll('a[data-course-term]')).map(a => a.dataset.courseTerm));
    scope.querySelectorAll(paragraphs).forEach(paragraph => {
      if (paragraph.closest('.source-note,pre,[data-no-terms]')) return;
      // Some editorial blocks contain their own <p>s. Only process the outer selected block.
      if (paragraph.parentElement && paragraph.parentElement.closest(paragraphs) &&
          scope.contains(paragraph.parentElement.closest(paragraphs))) return;
      const { value, nodes } = texts(paragraph), changes = [];
      let consumed = -1;
      model.scan(value).forEach(match => {
        const record = nodes.find(n => n.start <= match.start && n.end > match.start);
        if (match.start < consumed || !allowed(record, match.end)) return;
        if (seen.has(match.id)) {
          if (match.definitionEnd > match.end) changes.push(Object.assign({}, match, { removeOnly: true }));
          consumed = match.definitionEnd; return;
        }
        changes.push(match); seen.add(match.id); consumed = match.definitionEnd;
      });
      // Work backwards: the saved DOM offsets for earlier matches stay valid.
      changes.reverse().forEach(match => {
        const first = nodes.find(n => n.start <= match.start && n.end > match.start);
        const last = nodes.find(n => n.start < match.definitionEnd && n.end >= match.definitionEnd);
        if (!first || !last) return;
        const range = document.createRange();
        range.setStart(first.node, (match.removeOnly ? match.end : match.start) - first.start);
        range.setEnd(last.node, match.definitionEnd - last.start);
        if (match.removeOnly) { range.deleteContents(); return; }
        const anchor = document.createElement('a');
        anchor.className = 'course-term';
        anchor.href = 'glossary.html#term-' + match.id;
        anchor.textContent = match.label;
        anchor.dataset.courseTerm = match.id;
        anchor.dataset.termDefinition = model.entries.get(match.id).short;
        anchor.setAttribute('aria-haspopup', 'dialog');
        anchor.setAttribute('aria-expanded', 'false');
        anchor.setAttribute('aria-label', match.label + ' — краткое определение');
        range.deleteContents(); range.insertNode(anchor);
      });
    });
  }
  function refresh() {
    pending = false;
    observer.disconnect();
    try {
      if (opener && !opener.isConnected) close(false);
      document.querySelectorAll(scopes).forEach(enhance);
    } finally {
      observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    }
  }
  function schedule() {
    if (pending) return;
    pending = true;
    window.requestAnimationFrame(refresh);
  }
  function close(restoreFocus) {
    const previous = opener;
    if (popup) { popup.remove(); popup = null; }
    if (previous) { previous.setAttribute('aria-expanded', 'false'); previous.removeAttribute('aria-controls'); }
    opener = null;
    if (restoreFocus && previous && previous.isConnected) previous.focus({ preventScroll: true });
  }
  function position() {
    if (!popup || !opener) return;
    const rect = opener.getBoundingClientRect(), gap = 10, edge = 16;
    if (rect.bottom < 0 || rect.top > window.innerHeight) { close(false); return; }
    const width = Math.min(370, window.innerWidth - edge * 2);
    popup.style.width = width + 'px';
    if (window.innerWidth <= 600) {
      popup.style.left = edge + 'px'; popup.style.top = 'auto'; popup.style.bottom = edge + 'px';
      return;
    }
    popup.style.bottom = 'auto';
    popup.style.left = Math.max(edge, Math.min(rect.left, window.innerWidth - width - edge)) + 'px';
    const height = popup.getBoundingClientRect().height;
    const below = rect.bottom + gap;
    popup.style.top = Math.max(edge, below + height <= window.innerHeight - edge ? below : rect.top - height - gap) + 'px';
  }
  function open(anchor) {
    const entry = model.entries.get(anchor.dataset.courseTerm);
    if (!entry) return;
    if (opener === anchor) { close(true); return; }
    close(false); opener = anchor;
    popup = document.createElement('div');
    popup.id = 'course-term-popup'; popup.className = 'term-popup';
    popup.setAttribute('role', 'dialog');
    popup.setAttribute('aria-labelledby', 'course-term-heading');
    popup.setAttribute('aria-describedby', 'course-term-description');
    // No aria-modal and no focus trap: reading remains interactive outside this small dialog.
    const tag = document.createElement('p'); tag.className = 'term-popup-label'; tag.textContent = 'ТЕРМИН КУРСА';
    const heading = document.createElement('h2'); heading.id = 'course-term-heading'; heading.textContent = entry.title;
    const description = document.createElement('p'); description.id = 'course-term-description'; description.textContent = entry.short;
    const dismiss = document.createElement('button'); dismiss.type = 'button'; dismiss.className = 'term-popup-close';
    dismiss.setAttribute('aria-label', 'Закрыть определение'); dismiss.textContent = '×'; dismiss.addEventListener('click', () => close(true));
    const link = document.createElement('a'); link.className = 'term-popup-more';
    link.href = anchor.getAttribute('href'); link.target = '_blank'; link.rel = 'noopener';
    link.textContent = 'Подробно в глоссарии ↗';
    link.setAttribute('aria-label', 'Подробно: ' + entry.title + ' — в новой вкладке');
    popup.append(tag, heading, description, dismiss, link);
    document.body.append(popup);
    anchor.setAttribute('aria-expanded', 'true'); anchor.setAttribute('aria-controls', popup.id);
    position(); dismiss.focus({ preventScroll: true });
  }
  function start() {
    observer = new MutationObserver(schedule);
    refresh();
    document.addEventListener('click', event => {
      const anchor = event.target.closest && event.target.closest('a[data-course-term]');
      if (anchor && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && event.button === 0) {
        event.preventDefault(); open(anchor); return;
      }
      if (popup && !popup.contains(event.target)) close(false);
    });
    document.addEventListener('keydown', event => {
      if (!popup) return;
      if (event.key === 'Escape') { event.preventDefault(); close(true); return; }
      if (event.key === 'Tab' && ((event.shiftKey && document.activeElement === popup.querySelector('button')) ||
          (!event.shiftKey && document.activeElement === popup.querySelector('a')))) {
        // Close at the boundary instead of jumping from the body-level card to the page top.
        // The following Tab advances normally from the term in the reading flow.
        event.preventDefault(); close(true);
      }
    });
    document.addEventListener('focusin', event => { if (popup && event.target !== opener && !popup.contains(event.target)) close(false); });
    window.addEventListener('resize', position);
    window.addEventListener('scroll', position, true);
    window.addEventListener('hashchange', () => close(false));
    window.addEventListener('pagehide', () => close(false));
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
