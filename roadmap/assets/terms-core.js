/* Matching only. UI and DOM edits live in terms.js; no code execution or fetch. */
(function (global) {
  'use strict';
  function normalize(text) { return String(text).replace(/\s+/g, ' ').trim(); }
  function escapeRegex(text) { return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  function create(entries) {
    const index = new Map(), forms = new Map();
    entries.forEach(entry => {
      index.set(entry.id, entry);
      entry.forms.forEach(form => forms.set(form.toLocaleLowerCase('ru'), entry.id));
    });
    const aliases = Array.from(forms.keys()).sort((a, b) => b.length - a.length);
    const word = /[\p{L}\p{N}_]/u;
    const pattern = new RegExp(aliases.map(escapeRegex).join('|'), 'giu');
    function scan(text) {
      if (!aliases.length) return [];
      const matches = [];
      pattern.lastIndex = 0;
      let found;
      while ((found = pattern.exec(text))) {
        const start = found.index, end = start + found[0].length;
        if ((start && word.test(text[start - 1])) || (end < text.length && word.test(text[end]))) continue;
        const id = forms.get(found[0].toLocaleLowerCase('ru')), entry = index.get(id);
        let definitionEnd = end;
        const opening = /^\s*\(/.exec(text.slice(end));
        if (opening) {
          const from = end + opening[0].length;
          let depth = 1;
          for (let at = from; at < text.length; at++) {
            if (text[at] === '(') depth++;
            if (text[at] === ')' && !--depth) {
              const definition = normalize(text.slice(from, at));
              if ((entry.inlineDefinitions || []).some(value => normalize(value) === definition)) definitionEnd = at + 1;
              break;
            }
          }
        }
        matches.push({ id, start, end, definitionEnd, label: found[0] });
      }
      return matches;
    }
    return { entries: index, scan };
  }
  global.CourseTermsCore = { create, normalize };
})(globalThis);
