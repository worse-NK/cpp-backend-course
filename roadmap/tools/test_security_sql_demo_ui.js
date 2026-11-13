// Standalone prototype controller against a small DOM/Worker model.
// This executes the real model/controller, not a browser layout or real SQL.
// Real SQLite and worker-protocol checks live in test_security_sql_model.js.
const isNode = typeof require === 'function';
const read = isNode
  ? path => require('fs').readFileSync(path, 'utf8')
  : path => imports.byteArray.toString(imports.gi.GLib.file_get_contents(path)[1]);
const log = isNode ? value => console.log(value) : value => print(value);
const assert = (value, message) => { if (!value) throw new Error(message); };
const helper = read('roadmap/tools/test_visual_labs_ui.js');
const createDOM = new Function('read', helper.slice(helper.indexOf('function createDOM('),
  helper.indexOf('const doc=createDOM()')) + '; return createDOM;')(read);
const controller = read('roadmap/assets/security-sql-demo.js');
const modelSource = read('roadmap/assets/security-sql-model.js');

function environment(options = {}) {
  const doc = createDOM('roadmap/security_sql_demo.html');
  const proto = Object.getPrototypeOf(doc.body);
  const windowListeners = {}, timers = new Map(), workers = [], blobs = [];
  const activeURLs = new Set(), revokedURLs = [];
  let sequence = 0;
  class Text {
    constructor(value) { this.nodeType = 3; this.nodeValue = String(value); this.parentElement = null; }
    get textContent() { return this.nodeValue; }
    get children() { return []; }
    querySelectorAll() { return []; }
    matches() { return false; }
    clear() {}
  }
  Object.defineProperty(proto, 'children', {configurable:true,
    get() { return this.nodes.filter(node => typeof node !== 'string' && node.nodeType !== 3); }});
  Object.defineProperty(proto, 'className', {configurable:true,
    get() { return this.attrs.class || ''; }, set(value) { this.attrs.class = String(value); }});
  proto.clear = function () {
    this.nodes.forEach(node => { if (typeof node !== 'string') node.parentElement = null; });
    this.nodes = [];
  };
  proto.append = function (...nodes) {
    nodes.forEach(node => {
      if (typeof node === 'string' || typeof node === 'number') node = new Text(node);
      node.parentElement = this; this.nodes.push(node);
    });
  };
  proto.replaceChildren = function (...nodes) { this.clear(); this.append(...nodes); };
  proto.matches = function (selector) {
    const simple = (element, part) => {
      const attributes = [...part.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g)];
      const head = part.replace(/\[[^\]]+\]/g, ''), tag = head.match(/^[\w-]+/);
      if (tag && element.tagName !== tag[0].toUpperCase()) return false;
      const id = head.match(/#([\w-]+)/);
      if (id && element.id !== id[1]) return false;
      if ([...head.matchAll(/\.([\w-]+)/g)].some(match => !element.className.split(' ').includes(match[1]))) return false;
      return attributes.every(([, name, value]) => name in element.attrs &&
        (value === undefined || element.attrs[name] === value));
    };
    return selector.split(',').some(selectorPart => {
      const parts = selectorPart.trim().split(/\s+/); let node = this;
      if (!simple(node, parts.pop())) return false;
      while (parts.length) {
        const part = parts.pop(); node = node.parentElement;
        while (node && !simple(node, part)) node = node.parentElement;
        if (!node) return false;
      }
      return true;
    });
  };
  proto.focus = function () { doc.activeElement = this; };
  proto.scrollIntoView = function () { this.scrolled = true; };
  doc.querySelector = selector => doc.querySelectorAll(selector)[0] || null;
  doc.getElementById = id => doc.querySelectorAll('[id]').find(node => node.id === id) || null;
  doc.createElement = tag => new proto.constructor(tag);
  doc.createTextNode = value => new Text(value);
  doc.querySelectorAll('details').forEach(node => { node.open = node.getAttribute('open') !== null; });
  doc.querySelectorAll('button,input').forEach(node => { node.disabled = node.getAttribute('disabled') !== null; });
  class FakeBlob {
    constructor(parts, settings) { this.parts = parts; this.settings = settings; blobs.push(this); }
  }
  class FakeWorker {
    constructor(url) {
      if (options.constructorFailure) throw new Error('Worker constructor unavailable');
      this.url = url; this.terminated = false; workers.push(this);
    }
    postMessage(message) {
      if (options.postFailure) throw new Error('postMessage failed');
      this.message = message;
    }
    terminate() { this.terminated = true; }
    emit(type, fields = {}) { this.onmessage({data:{id:this.message.id, type, ...fields}}); }
  }
  const URL = {
    createObjectURL() { const url = 'blob:security-ui-' + (++sequence); activeURLs.add(url); return url; },
    revokeObjectURL(url) {
      assert(activeURLs.has(url), 'Object URL must be released exactly once');
      activeURLs.delete(url); revokedURLs.push(url);
    }
  };
  const win = {location:{hash:options.hash || ''}, addEventListener:(name, callback) => { windowListeners[name] = callback; },
    SECURITY_SQL_WORKER_SOURCE:'trusted bundled worker placeholder'};
  new Function('window', read('roadmap/generated/visual-labs.data.js'))(win);
  if (!options.missingModel) new Function('globalThis', 'module', modelSource)(win, undefined);
  if (options.missingBundle) delete win.SECURITY_SQL_WORKER_SOURCE;
  const setTimeout = (callback, milliseconds) => {
    const id = ++sequence; timers.set(id, {callback, milliseconds}); return id;
  };
  const clearTimeout = id => timers.delete(id);
  new Function('window', 'document', 'URL', 'Blob', 'Worker', 'setTimeout', 'clearTimeout',
    controller)(win, doc, URL, FakeBlob, FakeWorker, setTimeout, clearTimeout);
  function get(id) { const node = doc.getElementById(id); assert(node, 'Missing DOM id: ' + id); return node; }
  // Structural visibility only: no CSS layout, viewport or rendering is simulated.
  function visible(node) {
    for (let current = node; current; current = current.parentElement) {
      if (current.hidden) return false;
      const parent = current.parentElement;
      if (parent && parent.tagName === 'DETAILS' && !parent.open && current.tagName !== 'SUMMARY') return false;
    }
    return true;
  }
  function visibleText(node) {
    if (!visible(node)) return '';
    if (node.nodeType === 3) return node.textContent;
    return node.nodes.map(child => typeof child === 'string' ? child : visibleText(child)).join(' ');
  }
  function event(id, type = 'click', fields = {}) {
    const node = typeof id === 'string' ? get(id) : id;
    const action = {target:node, currentTarget:node, prevented:false,
      preventDefault() { this.prevented = true; }, ...fields};
    assert(typeof node.listeners[type] === 'function', 'Missing listener: ' + node.id + '/' + type);
    node.listeners[type](action); return action;
  }
  function input(value) { get('search-term').value = value; event('search-term', 'input'); }
  function submit() { event('search-form', 'submit'); return workers.at(-1); }
  function result(worker, rows = [], error = null, extra = {}) {
    worker.emit('result', {result:{query:win.SecuritySQLDemo.buildQuery(worker.message.term, worker.message.mode),
      rows, error, truncated:false, allRows:win.SecuritySQLDemo.fixture, engineVersion:'3.49.1', ...extra}});
  }
  function clean() {
    assert(activeURLs.size === 0, 'Blob URL leaked');
    assert(timers.size === 0, 'Worker timer leaked');
    assert(workers.every(worker => worker.terminated), 'Worker leaked');
    assert(!get('run').disabled && !get('check').disabled && get('stop').hidden, 'Busy controls were not restored');
    assert(get('experiment').getAttribute('aria-busy') === 'false', 'Busy ARIA state was not restored');
  }
  return {doc, win, get, visible, visibleText, event, input, submit, result, clean, workers, timers,
    activeURLs, revokedURLs, blobs, windowListeners};
}

const failures = []; let completed = 0;
function test(name, run) {
  try { run(); completed++; log('PASS: ' + name); }
  catch (error) { failures.push({name, error:String(error.stack || error)}); log('FAIL: ' + name + ': ' + error); }
}
function checksFor(mode) {
  return [
    {id:'ordinary', label:'Обычное название', term:'RAII', expectedRows:[{id:1}], actualRows:[{id:1}], passed:true, error:null, rejected:false, unexpectedPrivate:false},
    {id:'apostrophe', label:'Название с апострофом', term:"O'Reilly", expectedRows:[{id:3}], actualRows:mode === 'bind' ? [{id:3}] : [], passed:mode === 'bind', error:mode === 'concat' ? 'syntax error' : null, rejected:mode === 'filter', unexpectedPrivate:false},
    {id:'injection', label:'Ввод с SQL-словами', term:"' OR 1=1 --", expectedRows:[], actualRows:mode === 'concat' ? [{id:5}] : [], passed:mode === 'bind', error:null, rejected:mode === 'filter', unexpectedPrivate:mode === 'concat'},
    {id:'missing', label:'Несуществующее название', term:'Нет такого урока', expectedRows:[], actualRows:[], passed:true, error:null, rejected:false, unexpectedPrivate:false}
  ];
}

test('initialization, no automatic query and honest model boundaries', () => {
  const env = environment(), $ = env.get;
  assert(env.workers.length === 0 && env.timers.size === 0, 'Page load must not execute SQL automatically');
  assert($('search-term').value === 'RAII', 'Initial lesson input');
  assert($('previous').disabled && !$('next').hidden, 'Initial lesson boundaries');
  assert($('fix-panel').hidden && $('checks-panel').hidden, 'Advanced controls must not overload the first stage');
  assert($('fixture-table').querySelectorAll('tbody tr').length === 6, 'Six source rows must be inspectable');
  const copy = env.doc.body.textContent;
  assert(copy.includes('не PostgreSQL') && copy.includes('не запускает C++') && copy.includes('HTTP-запрос не отправляется'), 'Real engine and model boundaries');
  assert(copy.includes('если разработчик вообще уберёт') && copy.toLocaleLowerCase('ru').includes('права пользователя'), 'Parameter binding must not promise authorization');
});

test('ordinary request, worker protocol, id guards and resource lifetime', () => {
  const env = environment(), $ = env.get, worker = env.submit();
  assert(worker.message.type === 'run' && worker.message.term === 'RAII' && worker.message.mode === 'concat', 'Run protocol');
  assert($('run').disabled && $('check').disabled && !$('stop').hidden, 'Running controls');
  assert([...env.timers.values()][0].milliseconds === 10000, 'Initialization time budget');
  worker.emit('result', {id:worker.message.id + 1, result:null});
  assert(!worker.terminated && $('run').disabled, 'Ignore mismatched worker id');
  worker.emit('unknown'); assert(!worker.terminated, 'Unknown message must not complete the active run');
  worker.emit('ready');
  assert(env.timers.size === 1 && [...env.timers.values()][0].milliseconds === 3000, 'Execution time budget replaces initialization budget');
  env.result(worker, [{id:1, title:'RAII', is_public:1}]);
  assert($('results').textContent.includes('RAII') && $('response-count').textContent === 'Строк: 1', 'Actual returned rows');
  assert($('engine-version').textContent.includes('3.49.1'), 'Engine version from response');
  env.clean();
});

test('free input and returned cells are literal text, never markup', () => {
  const env = environment(), $ = env.get;
  // A decorative catalog flask is part of the static shell. Any media node
  // introduced by input/results is still a failure, wherever it is inserted.
  const shellMedia = new Set(env.doc.querySelectorAll('img,svg'));
  const hostile = '<img src=x onerror="globalThis.bad=1">';
  env.input(hostile);
  assert($('sql-code').textContent.includes(hostile), 'Free input must remain visible verbatim');
  assert($('http-code').textContent.includes(encodeURIComponent(hostile)), 'HTTP preview must encode the field as data');
  assert(env.doc.querySelectorAll('img').length === 0, 'Input became a DOM image');
  let worker = env.submit();
  env.result(worker, [{id:'<svg onload="bad()">', title:hostile, is_public:0}]);
  assert($('results').textContent.includes(hostile) && $('results').textContent.includes('<svg'), 'Returned cells were not rendered literally');
  assert($('results').querySelectorAll('img,svg').length === 0, 'Returned cells became DOM nodes');
  assert(env.doc.querySelectorAll('img,svg').every(node => shellMedia.has(node)), 'Input or returned cells introduced a media DOM node outside the static shell');
  env.event('stage-4'); env.input(hostile);
  assert(!$('parameter-box').hidden && $('parameter-value').textContent === JSON.stringify(hostile), 'Bound parameter is a separate literal value');
  assert(!$('sql-code').textContent.includes(hostile) && $('sql-code').textContent.includes('$term'), 'Input must not be substituted into bound SQL');
  worker = env.submit(); env.result(worker, []); env.clean();
});

test('SQL error is a result, blacklist rejection is before the engine', () => {
  const env = environment(), $ = env.get;
  env.input("O'Reilly"); let worker = env.submit();
  env.result(worker, [], 'near "Reilly": syntax error');
  assert($('response-count').textContent === 'Ошибка SQL' && $('results').textContent.includes('syntax error'), 'Structured SQL result.error');
  assert($('query-state').textContent === 'Ошибка выполнения', 'SQL error inspection state');
  env.event('stage-3'); env.event('preset-quote');
  const before = env.workers.length; env.submit();
  assert(env.workers.length === before, 'Rejected blacklist input must not start SQLite');
  assert($('response-count').textContent === 'Отказ до базы' && $('results').textContent.includes("O'Reilly"), 'Rejection must explain the legitimate apostrophe counterexample');
  assert($('path-handler').className.includes('blocked'), 'Rejected request stops at the handler');
  env.clean();
});

test('input edits, strategy and stage navigation invalidate pending work', () => {
  const env = environment(), $ = env.get;
  let worker = env.submit(); env.input('TCP');
  assert(worker.terminated && !$('results').textContent.includes('RAII'), 'Typing must cancel and invalidate old results');
  env.result(worker, [{id:1, title:'STALE_INPUT', is_public:1}]);
  assert(!$('results').textContent.includes('STALE_INPUT'), 'Cancelled input result leaked');
  env.event('stage-4'); env.event('check'); worker = env.workers.at(-1);
  env.event('mode-filter'); worker.emit('checks', {checks:checksFor('bind')});
  assert($('checks-results').querySelectorAll('.check-row').length === 0 && !$('status').textContent.includes('пройдено 4'), 'Cancelled checks leaked after mode change');
  worker = env.submit(); // filter rejects the current apostrophe before creating a new worker.
  env.event('mode-concat'); worker = env.submit(); env.event('stage-0');
  env.result(worker, [{id:5, title:'STALE_STAGE', is_public:0}]);
  assert(!$('results').textContent.includes('STALE_STAGE') && $('search-term').value === 'RAII', 'Stage changed while old result remained active');
  env.clean();
});

test('four checks preserve contract failures and mode-specific scope', () => {
  const env = environment(), $ = env.get; env.event('stage-4');
  for (const [mode, passed] of [['concat',2], ['filter',2], ['bind',4]]) {
    env.event('mode-' + mode); env.event('check'); const worker = env.workers.at(-1);
    assert(worker.message.type === 'checks' && worker.message.mode === mode, 'Checks protocol snapshot');
    worker.emit('checks', {checks:checksFor(mode)});
    assert($('checks-results').querySelectorAll('.check-row').length === 4, 'Four distinct checks must be visible');
    assert($('checks-summary').textContent.includes('пройдено ' + passed + ' из 4'), 'Mode-specific contract count');
    assert($('checks-summary').textContent.includes('не полный аудит'), 'Do not advertise four cases as a security proof');
    assert($('checks-results').querySelectorAll('.failed').length === 4 - passed, 'Rejected attack is not a passing exact-search contract');
  }
  env.input('TCP');
  assert($('checks-results').querySelectorAll('.check-row').length === 0, 'Editing must clear the old acceptance evidence');
  env.clean();
});

test('UTF-8 byte limits, NUL rejection and emoji byte counts', () => {
  const env = environment(), $ = env.get;
  for (const [value, count] of [['Я'.repeat(61),122], ['😀'.repeat(31),124], ['\0',1]]) {
    env.input(value); const before = env.workers.length; env.submit();
    assert($('input-count').textContent === count + ' / 120 байт', 'UTF-8 count must not be value.length');
    assert($('search-term').getAttribute('aria-invalid') === 'true', 'Rejected input ARIA state');
    assert(env.workers.length === before && $('response-count').textContent === 'Отказ до базы', 'Invalid bytes/NUL started a worker');
  }
  env.input('😀'.repeat(30));
  assert($('input-count').textContent === '120 / 120 байт' && $('search-term').getAttribute('aria-invalid') === 'false', 'Exactly120UTF-8bytes must remain valid');
  const worker = env.submit(); env.result(worker, []); env.clean();
});

test('ill-formed UTF-16 gets a readable refusal, not URIError', () => {
  const env = environment(), $ = env.get;
  env.input('\uD800'); const before = env.workers.length; env.submit();
  assert(env.workers.length === before && $('response-count').textContent === 'Отказ до базы', 'Malformed text must fail before SQLite');
  assert($('search-term').getAttribute('aria-invalid') === 'true' && $('status').className === 'error', 'Malformed text refusal must remain visible');
  env.clean();
});

test('guided stages, keyboard tabs, focus and restart', () => {
  const env = environment(), $ = env.get;
  env.event('next');
  assert($('search-term').value === "' OR 1=1 --" && $('stage-1').getAttribute('aria-current') === 'step', 'Second guided stage');
  assert(env.doc.activeElement === $('guide-title'), 'Stage navigation focus');
  env.event('stage-3'); assert(!$('fix-panel').hidden && $('checks-panel').hidden, 'Fix stage scope');
  env.event('stage-4'); assert(!$('checks-panel').hidden && $('next').hidden && !$('restart').hidden, 'Final stage boundary');
  $('technical-details').open = true; env.event('technical-details','toggle');
  let key = env.event('tab-sql','keydown',{key:'ArrowRight'});
  assert(key.prevented && $('tab-cpp').getAttribute('aria-selected') === 'true' && env.doc.activeElement === $('tab-cpp'), 'Keyboard tab change/focus');
  assert($('view-sql').hidden && !$('view-cpp').hidden && $('tab-sql').getAttribute('tabindex') === '-1', 'Tab/panel ARIA agreement');
  env.event('tab-cpp','keydown',{key:'End'}); assert(!$('view-http').hidden, 'End tab shortcut');
  env.event('tab-http','keydown',{key:'Home'}); assert(!$('view-sql').hidden, 'Home tab shortcut');
  key = env.event('tab-sql','keydown',{key:'x'}); assert(!key.prevented, 'Do not consume unrelated typing');
  env.event('restart');
  assert($('search-term').value === 'RAII' && $('mode-concat').getAttribute('aria-pressed') === 'true', 'Restart defaults');
  assert($('previous').disabled && !$('next').hidden && $('restart').hidden && $('fix-panel').hidden, 'Restart restores boundaries');
  assert(env.workers.length === 0, 'Stage and tab navigation must never query automatically');
});

test('stop, timeout and worker failures clear run/checks and permit fresh retry', () => {
  for (const kind of ['run','checks']) for (const failure of ['stop','timeout','onerror','protocol','unexpected']) {
    const env = environment(), $ = env.get;
    if (kind === 'checks') { env.event('stage-4'); env.event('check'); }
    else env.submit();
    const worker = env.workers.at(-1);
    if (failure === 'stop') env.event('stop');
    if (failure === 'timeout') [...env.timers.values()][0].callback();
    if (failure === 'onerror') worker.onerror({});
    if (failure === 'protocol') worker.emit('error', {message:'<img src=x> engine error'});
    if (failure === 'unexpected') worker.emit(kind === 'run' ? 'checks' : 'result', {});
    assert(!$('results').textContent.includes('Выполняем именно этот запрос'), 'Pending result survived ' + kind + '/' + failure);
    if (kind === 'run') assert($('response-count').textContent === 'Запуск не завершён', 'Run needs a non-pending terminal state');
    else assert($('checks-results').querySelectorAll('.check-row').length === 0, 'Failed checks must not invent acceptance results');
    env.result(worker, [{id:1,title:'STALE_TERMINAL',is_public:1}]);
    worker.emit('checks', {checks:checksFor('bind')});
    assert(!$('results').textContent.includes('STALE_TERMINAL'), 'Terminal late result survived ' + kind + '/' + failure);
    assert($('checks-results').querySelectorAll('.check-row').length === 0, 'Terminal late checks survived ' + kind + '/' + failure);
    assert(env.doc.querySelectorAll('img').length === 0, 'Protocol error was parsed as HTML');
    env.clean();
    const retry = env.submit();
    assert(retry !== worker && retry.message.id !== worker.message.id, 'Retry must own a new worker and operation id');
    env.result(retry, []); env.clean();
  }
});

test('worker creation/post failures and absent bundle release resources', () => {
  for (const options of [{constructorFailure:true}, {postFailure:true}, {missingBundle:true}]) {
    const env = environment(options); env.submit();
    assert(env.get('status').className === 'error', 'Unavailable worker must be explained');
    env.clean();
  }
  const missing = environment({missingModel:true});
  assert(missing.get('run').disabled && missing.get('status').textContent.includes('Не загрузилась модель'), 'Missing model fallback');
});

test('pagehide cancels pending work and ignores subsequent messages', () => {
  for (const kind of ['run','checks']) {
    const env = environment();
    if (kind === 'checks') { env.event('stage-4'); env.event('check'); }
    else env.submit();
    const worker = env.workers.at(-1); env.windowListeners.pagehide();
    env.result(worker, [{id:1,title:'AFTER_PAGEHIDE',is_public:1}]);
    worker.emit('checks', {checks:checksFor('bind')});
    assert(!env.get('results').textContent.includes('AFTER_PAGEHIDE'), 'Hidden page accepted a stale result');
    assert(env.get('checks-results').querySelectorAll('.check-row').length === 0, 'Hidden page accepted stale checks');
    env.clean();
  }
});

test('visible introduction explains the catalog, SQL and local execution before the task', () => {
  const env = environment(), $ = env.get;
  const intro = env.visibleText($('orientation')).toLocaleLowerCase('ru');
  for (const concept of ['каталог','опубликован','черновик','назван','таблиц','строк','столбц','sql','язык','обработчик'])
    assert(intro.includes(concept), 'Visible introduction omits the basic concept: ' + concept);
  assert(intro.includes('sqlite') && /библиотек|движок/.test(intro) && intro.includes('браузер'), 'SQLite/local execution must not be explained only in a collapsed note');
  assert(env.visible($('fixture-table')) && $('fixture-table').querySelectorAll('tbody tr').length === 6, 'The six source rows must be visible before exploration');
  const sections = env.doc.querySelectorAll('section');
  assert(sections.indexOf($('orientation')) < sections.indexOf($('experiment')), 'Introduce the scenario before presenting the controls');
  assert($('guide-hint').open === false && env.visibleText($('guide-context')).includes('WHERE'), 'First SQL explanation must not require opening a hint');
  assert($('explanation-panel').hidden && $('after-run-next').hidden, 'Do not present an observed outcome before any query ran');
});

test('five stages expose actions and comparison criteria without mandatory gates', () => {
  const env = environment(), $ = env.get;
  const actions = new Set(), expectations = new Set();
  for (let stage = 0; stage < 5; stage++) {
    assert(!$('stage-' + stage).disabled, 'A later stage must not depend on passing earlier queries');
    env.event('stage-' + stage);
    assert($('guide-hint').open === false, 'Hints should remain optional');
    for (const id of ['guide-copy','guide-context','guide-action','guide-expectation'])
      assert(env.visible($(id)) && env.visibleText($(id)).trim(), 'Missing visible learning orientation: ' + id + '/' + stage);
    actions.add(env.visibleText($('guide-action')));
    expectations.add(env.visibleText($('guide-expectation')));
    assert(env.workers.length === 0, 'Navigation must not silently execute the task');
  }
  assert(actions.size === 5 && expectations.size === 5, 'Each stage needs its own action and expected comparison, not a repeated slogan');
  env.event('stage-1');
  assert(/0\s+совпаден/.test(env.visibleText($('guide-expectation'))), 'Stage2 must retain the correct-search expectation of zero matches');
  env.event('stage-2');
  const cause = env.visibleText($('guide-context'));
  assert(cause.includes('кавыч') && cause.includes('OR') && cause.includes('1=1') && cause.includes('--') && cause.includes('SQL-инъек'), 'Explain the cause visibly, not only in the hint or bottom notes');
  assert(env.visibleText($('guide-expectation')).includes('6'), 'Separate the observed six-row result from the intended empty answer');
  env.event('stage-3');
  const fix = env.visibleText($('guide-context'));
  assert(fix.includes("O'Reilly") && fix.includes('$term') && fix.includes('отдельно'), 'Explain both the legitimate apostrophe and the separate parameter before asking for a fix');
  env.event('stage-4');
  assert(/не\s+процент\s+безопасности/.test(env.visibleText($('guide-context'))), 'Explain the meaning of the four-case score before running it');
  env.event('preset-quote'); env.input('Собственное название');
  assert($('search-term').value === 'Собственное название' && env.workers.length === 0, 'Presets and free input must stay exploratory, not execute or enforce a route');
});

test('contextual next action follows results and preserves the observed cause', () => {
  const env = environment(), $ = env.get;
  let worker = env.submit(); env.result(worker, [{id:1,title:'RAII',is_public:1}]);
  assert(! $('after-run-next').hidden && ! $('explanation-panel').hidden, 'A completed result needs its nearby explanation and next action');
  const afterOrdinary = env.workers.length; env.event('after-run-next');
  assert($('stage-1').getAttribute('aria-current') === 'step' && env.workers.length === afterOrdinary, 'Follow-up navigates, not queries');
  worker = env.submit(); env.result(worker, env.win.SecuritySQLDemo.fixture.map(row => ({...row})));
  const observed = $('results').textContent, beforeCause = env.workers.length;
  assert($('response-count').textContent === 'Строк: 6' && $('results').querySelectorAll('.visibility.private').length === 2, 'Observe the two real fixture drafts before explaining them');
  env.event('after-run-next');
  assert($('stage-2').getAttribute('aria-current') === 'step', 'Result follow-up enters the cause');
  assert($('results').textContent === observed && $('response-count').textContent === 'Строк: 6', 'Do not erase the evidence when the completed query and strategy have not changed');
  assert(env.workers.length === beforeCause && env.visible($('explanation-panel')), 'Cause explanation must reuse the observation, not rerun it');
  env.input('Другое название');
  assert($('after-run-next').hidden && $('explanation-panel').hidden, 'Input edits must invalidate old outcome/follow-up claims');
  env.clean();
});

test('optional technical panels do not hide the lesson or strand a C++/HTTP view', () => {
  const env = environment(), $ = env.get;
  assert(!$('technical-details').open && env.visible($('view-sql')) && !env.visible($('tab-cpp')), 'Start with SQL and hide optional technical controls');
  for (const name of ['cpp','http']) {
    $('technical-details').open = true; env.event('technical-details','toggle');
    env.event('tab-' + name);
    assert(env.visible($('view-' + name)) && !env.visible($('view-sql')), 'Selected optional view must be available');
    $('technical-details').open = false; env.event('technical-details','toggle');
    assert(env.visible($('view-sql')) && !env.visible($('view-' + name)), 'Closing optional controls must restore the basic SQL view');
    assert($('tab-sql').getAttribute('aria-selected') === 'true', 'Restore matching tab semantics');
  }
  $('technical-details').open = true; env.event('tab-cpp'); env.event('stage-2');
  assert(!$('technical-details').open && env.visible($('view-sql')) && env.visibleText($('guide-context')).includes('SQL-инъек'), 'Changing stages must not require optional details to read the core explanation');
  assert(env.workers.length === 0, 'Opening technical explanations must not execute code or requests');
});

test('computed UNION-like output is not mislabeled as a stored draft', () => {
  const env = environment(), $ = env.get;
  env.input("' UNION SELECT 99,'x',0 --");
  const worker = env.submit();
  env.result(worker, [{id:99,title:'x',is_public:0}, {id:5,title:'Changed title',is_public:0}]);
  assert($('results').querySelectorAll('.visibility.unknown').length === 2, 'All three fields must match a fixture row before classifying it as a stored record');
  assert($('results').querySelectorAll('.visibility.private').length === 0, 'An arbitrary result flag does not prove a stored draft was disclosed');
  assert($('results').textContent.includes('Другая строка') && !$('results').textContent.includes('Черновик'), 'Use a neutral label for computed rows');
  assert(!$('explanation-body').textContent.includes('Движок действительно вернул черновики'), 'Do not invent a privacy observation from computed values');
  env.clean();
});

test('catalog context returns to the exact approved theory, never a supplied URL', () => {
  for (const [hash,expected] of [
    ['#lab=security-sql&scenario=sql&from=station9-sql&section=sql-backend-boundaries','cpp_station9_sql.html#section=sql-backend-boundaries'],
    ['#lab=security-sql&scenario=sql&from=station15&section=sql-injection-laboratory','cpp_station15_security.html#section=sql-injection-laboratory'],
    ['#from=javascript%3Aalert(1)&section=unknown','cpp_station15_security.html#section=sql-injection-laboratory'],
    ['#from=%ZZ&section=missing','cpp_station15_security.html#section=sql-injection-laboratory']
  ]) {
    const env=environment({hash});
    assert(env.get('sql-theory-link').href===expected,'Wrong or untrusted return target');
    env.clean();
  }
});

if (failures.length) {
  failures.forEach(failure => log(failure.name + '\n' + failure.error));
  if (isNode) process.exitCode = 1;
  else imports.system.exit(1);
} else log('PASS: ' + completed + ' standalone security SQL controller scenarios; DOM/Worker model only, not live browser/layout/SQLite coverage.');
