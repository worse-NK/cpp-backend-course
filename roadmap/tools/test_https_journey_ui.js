// Controller contracts with the repository's small DOM model, not pixel/browser QA.
const read = path => imports.byteArray.toString(imports.gi.GLib.file_get_contents(path)[1]);
const assert = (value, message) => { if (!value) throw Error(message); };
const helper = read('roadmap/tools/test_visual_labs_ui.js');
const createDOM = new Function('read', helper.slice(helper.indexOf('function createDOM('),
  helper.indexOf('const doc=createDOM()')) + ';return createDOM;')(read);

class Params {
  constructor(text = '') {
    const decode = value => { try { return decodeURIComponent(value.replace(/\+/g, ' ')); } catch (_) { return value; } };
    this.values = new Map();
    for (const part of text.split('&').filter(Boolean)) {
      const [key, ...tail] = part.split('=');
      const name = decode(key);
      if (!this.values.has(name)) this.values.set(name, decode(tail.join('=')));
    }
  }
  get(key) { return this.values.get(key) ?? null; }
  has(key) { return this.values.has(key); }
}

function environment(hash = '', options = {}) {
  const document = createDOM('roadmap/templates/https_journey_lab.html');
  const proto = Object.getPrototypeOf(document.body);
  const matches = proto.matches;
  proto.matches = function (selector) {
    if (/^#[\w-]+$/.test(selector)) return this.id === selector.slice(1);
    return matches.call(this, selector);
  };
  proto.scrollIntoView = function (value) { this.lastScroll = value; };
  document.querySelector = selector => document.body.querySelector(selector);
  document.getElementById('experiment').style.setProperty = function (name, value) { this[name] = value; };
  const listeners = {}, timers = new Map(), history = [hash];
  let cursor = 0, nextTimer = 0;
  const window = {
    location: {hash}, matchMedia: () => ({matches: !!options.reduced}),
    addEventListener: (name, callback) => { listeners[name] = callback; },
    setInterval: (callback, delay) => { timers.set(++nextTimer, {callback, delay}); return nextTimer; },
    clearInterval: id => { timers.delete(id); }
  };
  window.history = {
    replaceState: (_data, _title, value) => { window.location.hash = value; history[cursor] = value; },
    pushState: (_data, _title, value) => {
      window.location.hash = value; history.splice(cursor + 1); history.push(value); cursor++;
    },
    back: () => { if (cursor > 0) { window.location.hash = history[--cursor]; listeners.popstate(); } },
    forward: () => { if (cursor + 1 < history.length) { window.location.hash = history[++cursor]; listeners.popstate(); } }
  };
  new Function('window', read('roadmap/generated/visual-labs.data.js'))(window);
  new Function('window', 'globalThis', read('roadmap/assets/https-journey-model.js'))(window, window);
  if (options.changeModel) window.HttpsJourney = options.changeModel(window.HttpsJourney);
  new Function('window', 'document', 'URLSearchParams', read('roadmap/assets/https-journey-lab.js'))(window, document, Params);
  const get = id => {
    const node = document.getElementById(id); assert(node, 'Missing control: ' + id); return node;
  };
  const dispatch = (node, type, values = {}) => {
    assert(node && node.listeners[type], 'Missing event handler: ' + type);
    assert(!node.disabled, 'Dispatching disabled control: ' + (node.id || node.tagName));
    const event = Object.assign({target: node, currentTarget: node, preventDefault() {}}, values);
    node.listeners[type].call(node, event);
  };
  const click = id => dispatch(get(id), 'click');
  const choose = (selector, value) => {
    const node = document.querySelector(selector); assert(node, 'Missing selector ' + selector);
    node.focus(); dispatch(node, 'click');
    return node;
  };
  const range = value => { get('step-range').value = String(value); dispatch(get('step-range'), 'input'); };
  const scenario = value => { get('scenario').value = value; dispatch(get('scenario'), 'change'); };
  const route = value => { window.location.hash = value; listeners.hashchange(); };
  const tick = () => { assert(timers.size === 1, 'Exactly one running timer'); [...timers.values()][0].callback(); };
  return {document, window, listeners, timers, history, get, click, dispatch, choose, range, scenario, route, tick};
}

let views = 0;
for (const id of ['normal', 'cached', 'bad-cert']) {
  const e = environment('#scenario=' + id + '&step=0&view=network&panel=explain');
  const list = e.window.HttpsJourney.getSteps(id);
  assert(e.get('previous').disabled && e.get('reset').disabled, 'Start bounds: ' + id);
  assert(e.get('scenario').value === id, 'Selected scenario: ' + id);
  for (let index = 0; index < list.length; index++) {
    e.range(index);
    const step = list[index], state = e.window.HttpsJourney.getState(id, index);
    assert(e.get('step-title').textContent === step.title, 'Title: ' + id + '/' + index);
    assert(e.get('step-range').getAttribute('aria-valuetext') === step.title, 'Accessible range title');
    assert(e.get('step-counter').textContent === 'Шаг ' + (index + 1) + ' из ' + list.length, 'Step counter');
    assert(e.get('explanation').textContent.includes(step.summary) &&
      step.paragraphs.every(text => e.get('explanation').textContent.includes(text)), 'Full authored explanation');
    assert(e.get('explanation').textContent.includes(step.changed) && e.get('explanation').textContent.includes(step.visible), 'Causality/visibility');
    assert(e.get('participant-state').textContent.includes(state.address) &&
      e.get('participant-state').textContent.includes(state.transport) &&
      e.get('participant-state').textContent.includes(state.security), 'Current browser state');
    assert(e.get('scene').querySelector('svg'), 'Real SVG scene present');
    assert(e.get('scene').querySelector('title').textContent.length > 5, 'SVG accessible title');
    assert(e.get('scene').querySelector('desc').textContent.includes('логические пути'), 'SVG topology boundary');
    assert(e.get('announcement').textContent.includes(step.title), 'Live current-event announcement');
    const messages = list.slice(0, index + 1).filter(s => s.from && s.to);
    assert(e.get('journal').querySelectorAll('[data-journal-step]').length === messages.length, 'No future/stale journal messages');
    assert(e.get('inspect-message').disabled === !step.fields.length, 'Fields availability');
    assert(e.get('previous').disabled === (index === 0), 'Previous bound');
    assert(e.get('next').disabled === (index === list.length - 1), 'Next bound');
    assert(e.window.location.hash.includes('scenario=' + id + '&step=' + index), 'Deep link current step');
    views++;
  }
  assert(e.get('play').disabled, 'Autoplay end bound');
  e.click('reset');
  assert(e.get('step-range').value === '0' && e.get('previous').disabled, 'Reset bound');
  e.click('next'); e.click('previous');
  assert(e.get('step-range').value === '0', 'Next/back round trip');
}

const e = environment('#scenario=normal&step=9&view=network&panel=explain');
e.click('inspect-message');
assert(!e.get('fields').hidden && e.get('explanation').hidden, 'Fields shown');
assert(e.get('fields').textContent.includes('49152 → 443'), 'Selected SYN ports');
assert(e.get('fields').textContent.includes('1000'), 'Selected SYN number');
e.choose('[data-panel="explain"]');
assert(!e.get('explanation').hidden && e.get('fields').hidden, 'Explanation restored');
e.choose('[data-view="sequence"]');
assert(e.get('scene').querySelector('.sequence-wrap') && !e.get('scene').querySelector('svg'), 'Sequence/network exclusive');
assert(e.get('scene').querySelectorAll('[data-sequence-step]').length === 9, 'Sequence contains only past messages');
e.choose('[data-sequence-step="1"]');
assert(e.get('step-range').value === '1', 'Sequence selects exact source step');
assert(e.document.activeElement === e.get('step-title'), 'Sequence activation keeps focus in current explanation');
e.choose('[data-phase="tls"]');
assert(e.get('step-title').textContent === e.window.HttpsJourney.getSteps('normal').find(s => s.phase === 'tls').title, 'Phase selects first relevant event');
assert(e.document.activeElement === e.get('step-title'), 'Phase activation does not leave detached focus');
e.choose('[data-journal-step="9"]');
assert(e.get('step-range').value === '9' && !e.get('fields').hidden, 'Journal returns to message fields');
assert(e.document.activeElement === e.get('step-title'), 'Journal activation keeps stable focus');
e.choose('[data-view="network"]');
e.choose('[data-panel="explain"]');
e.choose('[data-inspect="true"]');
assert(!e.get('fields').hidden, 'Scene envelope opens fields');
assert(e.document.activeElement === e.document.querySelector('[data-panel="fields"]') ||
  e.document.activeElement === e.get('step-title'), 'Scene inspector does not strand focus on removed button');

e.click('next');
const titleAfter = e.get('step-title').textContent;
e.window.history.back();
assert(e.get('step-range').value === '9' && !e.get('fields').hidden, 'Browser back restores exact view/fields/step');
e.window.history.forward();
assert(e.get('step-title').textContent === titleAfter, 'Browser forward restores event');
e.scenario('cached');
assert(e.get('step-range').value === '0' && !e.get('explanation').hidden, 'Scenario switch resets event and explanation');
e.range(1);
assert(e.get('scene').querySelectorAll('[data-inspect]').length === 0 && e.get('journal').querySelectorAll('button').length === 0, 'Cache does not invent packets');
assert(e.get('journal').textContent.includes('сетевых сообщений пока не было') &&
  !e.get('journal').textContent.includes('адрес только появился'), 'Cache-hit empty journal does not claim the address is still unknown');
e.scenario('bad-cert'); e.range(1000);
assert(e.get('next').disabled && e.get('next').textContent.includes('остановлена'), 'Bad certificate stops UI before HTTP');
assert(!e.get('journal').textContent.includes('GET /hello'), 'Bad certificate has no hidden HTTP request');

const t = environment();
t.click('play');
assert(t.timers.size === 1 && t.get('play').getAttribute('aria-pressed') === 'true', 'Autoplay opt-in');
assert([...t.timers.values()][0].delay === 5000, 'Approved autoplay pacing is exactly five seconds per step');
t.tick(); assert(t.get('step-range').value === '1', 'Autoplay advances');
t.click('next'); assert(t.timers.size === 0, 'Manual navigation cancels timer');
t.click('play'); t.click('play'); assert(t.timers.size === 0, 'Pause cancels timer');
t.click('play'); t.scenario('cached'); assert(t.timers.size === 0, 'Scenario cancels timer');
t.click('play'); t.choose('[data-view="sequence"]'); assert(t.timers.size === 0, 'View cancels timer');
t.click('play'); t.route('#scenario=normal&step=9'); assert(t.timers.size === 0, 'Route cancels timer');
t.click('play'); t.click('inspect-message'); assert(t.timers.size === 0, 'Inspection cancels timer');
t.click('play'); t.document.hidden = true; t.document.listeners.visibilitychange();
assert(t.timers.size === 0, 'Hidden tab cancels timer');
t.document.hidden = false;
t.range(18); t.click('play'); t.tick();
assert(t.timers.size === 0 && t.get('play').disabled, 'Last auto event stops timer');

const keys = environment();
let prevented = false;
keys.document.listeners.keydown({target:keys.document.body,key:'ArrowRight',preventDefault(){prevented=true;}});
assert(prevented && keys.get('step-range').value === '1', 'Body right-arrow navigation');
for (const id of ['next', 'scenario', 'step-range', 'scene']) {
  prevented = false;
  keys.document.listeners.keydown({target:keys.get(id),key:'ArrowRight',preventDefault(){prevented=true;}});
  assert(!prevented && keys.get('step-range').value === '1', 'Native control keys retained: ' + id);
}
assert(keys.get('scene').getAttribute('tabindex') === '0', 'Wide mobile scene is keyboard-focusable');
prevented = false;
keys.document.listeners.keydown({target:keys.get('scene').querySelector('svg'),key:'ArrowLeft',preventDefault(){prevented=true;}});
assert(!prevented && keys.get('step-range').value === '1', 'Keys inside the scene retain native horizontal scrolling');
keys.document.listeners.keydown({target:keys.document.body,key:'ArrowRight',altKey:true,preventDefault(){throw Error('Modified key intercepted');}});
assert(keys.get('step-range').value === '1', 'Modified shortcuts preserved');
keys.choose('.start-button');
assert(keys.document.activeElement === keys.get('experiment') && keys.get('step-range').value === '0', 'Start moves to experiment with stable focus');
keys.scenario('cached'); keys.range(5);
keys.choose('[data-view="sequence"]'); keys.choose('[data-panel="fields"]');
const skipRoute = keys.window.location.hash, skipHistory = keys.history.length, skipTitle = keys.get('step-title').textContent;
keys.choose('.skip-link');
assert(keys.window.location.hash === skipRoute && keys.history.length === skipHistory &&
  keys.get('scenario').value === 'cached' && keys.get('step-range').value === '5' &&
  keys.get('step-title').textContent === skipTitle && !keys.get('fields').hidden,
  'Skip link preserves selected scenario, step, view, fields and browser history');
assert(keys.document.activeElement === keys.get('experiment') && keys.get('experiment').lastScroll.behavior === 'auto',
  'Skip link focuses experiment without restarting the lesson');

const invalid = environment('#scenario=%ZZ&step=NaN&view=other&panel=other');
assert(invalid.get('scenario').value === 'normal' && invalid.get('step-range').value === '0', 'Invalid route fallback');
const bounded = environment('#scenario=bad-cert&step=999999');
assert(bounded.get('next').disabled && bounded.get('next').textContent.includes('остановлена'), 'Route upper bound');

// Course entry metadata, not arbitrary URL parameters, controls return navigation.
const course = environment();
const journey = course.window.COURSE_LABS.find(lab => lab.id === 'https-journey');
assert(journey && journey.file === 'https_journey_lab.html', 'HTTPS journey is present in the generated course catalog');
assert(journey.entries.length === 4, 'One coherent lab has four relevant course entry points');
const hrefOf = element => element.href || element.getAttribute('href');
const contextOf = instance => new Params(instance.window.location.hash.slice(1));
const assertReturn = (instance, entry, message) => {
  const expected = entry.file + '#section=' + entry.section;
  assert(hrefOf(instance.get('return-to-section')) === expected &&
    hrefOf(instance.get('return-to-theory')) === expected, 'Exact authored return route: ' + message);
};
const assertContext = (instance, entry, message) => {
  const params = contextOf(instance);
  assert(params.get('from') === entry.station && params.get('section') === entry.section,
    'Course context retained in URL: ' + message);
  assertReturn(instance, entry, message);
};
for (const entry of journey.entries) {
  const href = course.window.courseLabHref(journey.id, entry.scenario, entry.station, entry.section);
  assert(href.startsWith('https_journey_lab.html#'), 'Catalog link targets the standalone HTTPS lab');
  const opened = environment(href.slice(href.indexOf('#')));
  const expected = opened.window.HttpsJourney.getSteps(entry.scenario).findIndex(step => step.phase === entry.phase);
  assert(expected >= 0 && Number(opened.get('step-range').value) === expected,
    'Course entry starts at the correct existing phase: ' + entry.section);
  assert(opened.get('scenario').value === entry.scenario, 'Course entry selects authored scenario: ' + entry.section);
  assertReturn(opened, entry, entry.section + ' initial');
  opened.click('next'); assertContext(opened, entry, entry.section + ' next');
  opened.choose('[data-view="sequence"]'); assertContext(opened, entry, entry.section + ' sequence');
  opened.choose('[data-panel="fields"]'); assertContext(opened, entry, entry.section + ' fields');
  opened.scenario('normal'); assertContext(opened, entry, entry.section + ' scenario change');
  opened.range(9); assertContext(opened, entry, entry.section + ' range');
  opened.click('play'); opened.tick(); assertContext(opened, entry, entry.section + ' autoplay');
  opened.click('play');
  const before = opened.window.location.hash;
  opened.click('next');
  const after = opened.window.location.hash;
  opened.window.history.back();
  assert(opened.window.location.hash === before, 'Course route back restores exact state');
  assertReturn(opened, entry, entry.section + ' history back');
  opened.window.history.forward();
  assert(opened.window.location.hash === after, 'Course route forward restores exact state');
  assertReturn(opened, entry, entry.section + ' history forward');
  opened.choose('.start-button'); assertContext(opened, entry, entry.section + ' full restart');
  assert(opened.get('step-range').value === '0', 'Full lesson restart remains available from a phase entry');
}
for (const badRoute of [
  '#scenario=normal&phase=tcp&from=station99&section=url-to-service',
  '#scenario=normal&phase=tcp&from=station7&section=not-a-section',
  '#scenario=normal&from=https%3A%2F%2Fevil.example&section=url-to-service',
  '#scenario=normal&from=station7&section=javascript%3Aalert(1)',
  '#scenario=normal&from=station7&section=url-to-service%22%20onclick%3Dbad()'
]) {
  const rejected = environment(badRoute);
  for (const id of ['return-to-section', 'return-to-theory']) {
    const href = hrefOf(rejected.get(id));
    assert(/^cpp_station7_networking\.html#section=[\w-]+$/.test(href), 'Invalid context uses a known local fallback');
    assert(!href.includes('evil') && !href.includes('javascript') && !href.includes('onclick'), 'Invalid context is never reflected into a link');
  }
  rejected.click('next');
  assert(contextOf(rejected).get('from') === null && contextOf(rejected).get('section') === null,
    'Unrecognised return context is discarded from the canonical route');
}
const unrelatedReturn = environment('#scenario=normal&phase=tcp&from=station7&section=tcp-stream-handshake&return=https%3A%2F%2Fevil.example');
assertReturn(unrelatedReturn, journey.entries.find(entry => entry.section === 'tcp-stream-handshake'), 'Unrelated return parameter ignored');
const explicitStep = environment('#scenario=cached&phase=tls&step=1');
assert(explicitStep.get('step-range').value === '1', 'Explicit step takes precedence over entry phase');
const invalidPhase = environment('#scenario=normal&phase=__proto__');
assert(invalidPhase.get('step-range').value === '0', 'Unknown phase safely starts at the first event');
const phaseAbsentFromScenario = environment('#scenario=bad-cert&phase=http');
assert(phaseAbsentFromScenario.get('step-range').value === '0', 'Unavailable scenario phase cannot create an out-of-range event');

const reduced = environment('#scenario=normal&step=0', {reduced:true}); reduced.click('next');
assert(!reduced.get('scene').querySelector('animateMotion'), 'Reduced motion suppresses traveling envelope');
assert(reduced.get('scene').querySelector('.journey-direction').dataset.to==='resolver', 'Route has a permanent direction without movement');
const reply = environment('#scenario=normal&step=18', {reduced:true});
const reverseSignal = reply.get('scene').querySelector('.journey-direction');
assert(reverseSignal.dataset.from==='server' && reverseSignal.dataset.to==='client' && reverseSignal.getAttribute('transform').includes('rotate(180)'), 'Return path arrow faces browser even on a static deep link');
assert(reply.get('scene').querySelector('.journey-transit-label').textContent.includes('данные зашифрованы') && !reply.get('scene').querySelector('.journey-transit-label').textContent.includes('200 OK'), 'Wire label does not expose the HTTP status as plaintext');
assert(reply.get('scene').querySelector('[data-screen-state="received"]') && !reply.get('scene').querySelector('[data-screen-state="rendered"]'), 'Received HTML is not a rendered page');
reply.click('next');
assert(reply.get('scene').querySelector('[data-screen-state="rendered"]') && !reply.get('scene').querySelector('.journey-direction'), 'A local render uses the received document and sends no packet');
const motion = environment(); motion.click('next');
assert(motion.get('scene').querySelector('animateMotion'), 'User step can show a one-shot message animation');

const attack = '<img src=x onerror="window.bad=1"> & <script>bad()</script>';
const literal = environment('#scenario=normal&step=9', {changeModel(base) {
  const modified = JSON.parse(JSON.stringify(base.getSteps('normal')));
  modified[9].title = attack; modified[9].summary = attack;
  modified[9].paragraphs = [attack]; modified[9].label = attack;
  modified[9].fields = [{layer:attack,title:attack,items:[[attack,attack,attack]]}];
  return Object.assign({},base,{getSteps:() => modified});
}});
literal.click('inspect-message');
assert(literal.get('step-title').textContent === attack && literal.get('fields').textContent.includes(attack), 'Field/title values remain literal');
for (const id of ['scene', 'explanation', 'fields', 'journal']) {
  assert(literal.get(id).querySelectorAll('img').length === 0 && literal.get(id).querySelectorAll('script').length === 0, 'No markup execution path: ' + id);
}
const source = read('roadmap/assets/https-journey-lab.js');
assert(!/\bfetch\s*\(|XMLHttpRequest|\bWebSocket\s*\(|\beval\s*\(|localStorage|sessionStorage/.test(source), 'No network/eval/progress writes');
assert(read('roadmap/templates/https_journey_lab.html').includes('aria-live="polite"'), 'Live announcement markup');
print('PASS: HTTPS controller — ' + views + ' event views, exact model/explanations, scenario boundaries, fields escaping, focus, keyboard, hash/history, timer cancellation and reduced motion. DOM model only; real rendering not verified.');
