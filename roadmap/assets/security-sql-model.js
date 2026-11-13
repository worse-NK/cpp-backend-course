/* Original standalone course prototype. Real SQLite via vendored sql.js 1.13.0.
 * API/lifetime: https://github.com/sql-js/sql.js/blob/v1.13.0/src/api.js
 * Binding: https://www.sqlite.org/lang_expr.html#varparam
 * Guards: https://www.sqlite.org/pragma.html#pragma_query_only
 *         https://www.sqlite.org/pragma.html#pragma_hard_heap_limit
 * This is an intentionally vulnerable, disposable fixture, not an application
 * authorization boundary or a general SQL sandbox. Never use real secrets here.
 */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.SecuritySQLDemo = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const limits = Object.freeze({maxInputLength:120, maxInputBytes:120, maxRows:20,
    maxDiagnosticLength:200, maxCellLength:200, sqliteHeapBytes:8*1024*1024});
  const fixture = Object.freeze([
    {id:1, title:'RAII', is_public:1},
    {id:2, title:'TCP', is_public:1},
    {id:3, title:"O'Reilly", is_public:1},
    {id:4, title:'Планирование', is_public:1},
    {id:5, title:'Черновик A', is_public:0},
    {id:6, title:'Черновик B', is_public:0}
  ].map(row => Object.freeze(row)));
  const prefix = 'SELECT id, title, is_public FROM lessons WHERE is_public = 1 AND title = ';
  const suffix = ' ORDER BY id;';
  const sqlTemplate = prefix + '$term' + suffix;
  const modes = Object.freeze(['concat','filter','bind']);

  // TextEncoder-compatible byte count, including replacement of lone UTF-16
  // surrogates by U+FFFD. No TextEncoder dependency is required in GJS.
  function byteLength(text) {
    if (typeof text !== 'string') throw new TypeError('Ожидается строка.');
    let bytes = 0;
    for (let i=0; i<text.length; i++) {
      const unit = text.charCodeAt(i);
      if (unit < 0x80) bytes++;
      else if (unit < 0x800) bytes += 2;
      else if (unit >= 0xD800 && unit <= 0xDBFF && i+1 < text.length &&
               text.charCodeAt(i+1) >= 0xDC00 && text.charCodeAt(i+1) <= 0xDFFF) {
        bytes += 4; i++;
      } else bytes += 3;
    }
    return bytes;
  }
  function wellFormed(text) {
    for (let i=0; i<text.length; i++) {
      const unit = text.charCodeAt(i);
      if (unit >= 0xD800 && unit <= 0xDBFF) {
        const next = text.charCodeAt(++i);
        if (!(next >= 0xDC00 && next <= 0xDFFF)) return false;
      } else if (unit >= 0xDC00 && unit <= 0xDFFF) return false;
    }
    return true;
  }
  function diagnostic(error) {
    let text;
    try { text = String(error && error.message ? error.message : error); }
    catch (_) { text = 'Ошибка SQLite.'; }
    text = text.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, '\uFFFD');
    return text.length > limits.maxDiagnosticLength
      ? text.slice(0, limits.maxDiagnosticLength-1) + '…' : text;
  }
  function buildQuery(term, mode) {
    const query = {sql:'', params:{}, rejected:false, message:'',
      mode:typeof mode === 'string' ? mode.slice(0,16) : '',
      term:typeof term === 'string' ? term.slice(0,limits.maxInputLength) : ''};
    function reject(message) { query.rejected=true; query.message=message; return query; }
    if (!modes.includes(mode)) return reject('Выбери один из трёх способов: concat, filter или bind.');
    if (typeof term !== 'string') return reject('Поисковое значение должно быть строкой.');
    if (term.length > limits.maxInputBytes || byteLength(term) > limits.maxInputBytes)
      return reject('В учебном примере разрешено не больше 120 байт UTF-8.');
    if (term.includes('\0')) return reject('Нулевой символ в этом учебном поле не допускается.');
    if (!wellFormed(term)) return reject('Строка содержит непарный суррогат UTF-16. Используй корректный текст.');
    query.term = term;
    if (mode === 'filter' && term.includes("'"))
      return reject('Учебный фильтр запретил апостроф. Он отвергает и обычное название O\'Reilly; это не универсальная защита.');
    query.sql = mode === 'bind' ? sqlTemplate : prefix + "'" + term + "'" + suffix;
    if (mode === 'bind') query.params = {$term:term};
    return query;
  }
  function fixtureCopy() { return fixture.map(row => ({...row})); }
  function seed(SQL) {
    const db = new SQL.Database();
    let statement;
    try {
      db.run('CREATE TABLE lessons (id INTEGER PRIMARY KEY, title TEXT NOT NULL, '+
        'is_public INTEGER NOT NULL CHECK (is_public IN (0,1)));');
      statement = db.prepare('INSERT INTO lessons(id,title,is_public) VALUES($id,$title,$public);');
      for (const row of fixture) {
        statement.bind({$id:row.id, $title:row.title, $public:row.is_public});
        statement.step();
      }
      statement.free(); statement = null;
      // Restricts SQLite allocations, not total Worker/browser memory. The
      // controller must still terminate its disposable worker on timeout/cancel.
      const heap = db.exec('PRAGMA hard_heap_limit = ' + limits.sqliteHeapBytes + ';');
      if (!heap[0] || !(heap[0].values[0][0] > 0) || heap[0].values[0][0] > limits.sqliteHeapBytes)
        throw new Error('SQLite не подтвердила учебный лимит своих выделений памяти.');
      db.run('PRAGMA query_only = ON;');
      const guard = db.exec('PRAGMA query_only;');
      if (!guard[0] || guard[0].values[0][0] !== 1)
        throw new Error('SQLite не подтвердила запрет изменения учебных таблиц.');
      return db;
    } catch (error) {
      try { if (statement) statement.free(); }
      finally { db.close(); }
      throw error;
    }
  }
  function cell(value, state) {
    if (value instanceof Uint8Array) {
      state.truncated = true;
      const bytes = Array.from(value.subarray(0,32), n => n.toString(16).padStart(2,'0')).join(' ');
      return ('BLOB · ' + value.length + ' байт: ' + bytes + (value.length>32?' …':''))
        .slice(0, limits.maxCellLength);
    }
    if (typeof value === 'string' && value.length > limits.maxCellLength) {
      state.truncated = true;
      return value.slice(0, limits.maxCellLength-1) + '…';
    }
    return value;
  }
  function readRows(db, sql, params) {
    let statement;
    const state = {rows:[], truncated:false};
    try {
      // prepare compiles ONE statement; unlike db.exec/iterateStatements, it
      // does not execute an injected second statement after a semicolon.
      statement = db.prepare(sql);
      if (Object.keys(params).length) statement.bind(params);
      while (statement.step()) {
        if (state.rows.length === limits.maxRows) { state.truncated=true; break; }
        const values = statement.get();
        state.rows.push({id:cell(values[0],state), title:cell(values[1],state),
                         is_public:cell(values[2],state)});
      }
      return state;
    } finally { if (statement) statement.free(); }
  }
  function execute(SQL, term, mode) {
    const query = buildQuery(term, mode);
    const result = {query, rows:[], error:null, truncated:false,
      allRows:fixtureCopy(), engineVersion:null};
    if (query.rejected) { result.error=query.message; return result; }
    let db;
    try {
      if (!SQL || typeof SQL.Database !== 'function') throw new Error('Движок SQLite ещё не загружен.');
      db = seed(SQL);
      result.engineVersion = String(db.exec('SELECT sqlite_version();')[0].values[0][0]);
      result.allRows = readRows(db,'SELECT id,title,is_public FROM lessons ORDER BY id;',{}).rows;
      const answer = readRows(db,query.sql,query.params);
      result.rows = answer.rows; result.truncated = answer.truncated;
    } catch (error) { result.rows=[]; result.error=diagnostic(error); }
    finally {
      if (db) {
        try { db.close(); }
        catch (error) { result.rows=[]; if (!result.error) result.error=diagnostic(error); }
      }
    }
    return result;
  }
  function runChecks(SQL, mode) {
    const cases = [
      {id:'ordinary', label:'Обычное название', term:'RAII'},
      {id:'apostrophe', label:'Название с апострофом', term:"O'Reilly"},
      {id:'injection', label:'Ввод, меняющий условие при склейке', term:"' OR 1=1 --"},
      {id:'missing', label:'Несуществующее название', term:'Нет такого урока'}
    ];
    return cases.map(test => {
      const expectedRows = fixture.filter(row => row.is_public===1 && row.title===test.term)
        .map(row => ({...row}));
      const result = execute(SQL,test.term,mode);
      return {id:test.id, label:test.label, term:test.term, expectedRows,
        actualRows:result.rows, passed:!result.error && !result.query.rejected && !result.truncated &&
          JSON.stringify(result.rows)===JSON.stringify(expectedRows),
        error:result.error, rejected:result.query.rejected,
        unexpectedPrivate:result.rows.some(row => row.is_public===0)};
    });
  }
  return Object.freeze({fixture, limits, modes, sqlTemplate, byteLength, buildQuery, execute, runChecks});
});
