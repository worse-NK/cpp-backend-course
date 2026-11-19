// Controller contracts using the repository's deliberately small DOM model.
// This verifies state/content/control wiring, not layout, contrast or pixels.
const GLib = imports.gi.GLib, BA = imports.byteArray;
const read = path => BA.toString(GLib.file_get_contents(path)[1]);
const exists = path => GLib.file_test(path, GLib.FileTest.IS_REGULAR);
const assert = (value, message) => { if (!value) throw Error(message); };
const pendingAllowed = typeof ARGV !== 'undefined' && ARGV.includes('--available');
const helper = read('roadmap/tools/test_visual_labs_ui.js');
const createDOM = new Function('read', helper.slice(helper.indexOf('function createDOM('),
  helper.indexOf('const doc=createDOM()')) + ';return createDOM;')(read);
const LABS = [
  {id:'tcp-delivery', model:'network-tcp-model.js', page:'tcp_delivery_lab.html', back:'cpp_station7_networking.html#section=tcp-loss-retransmission'},
  {id:'network-setup', model:'network-config-model.js', page:'network_setup_lab.html', back:'cpp_station7_networking.html#section=dhcp-network-config'},
  {id:'packetpath', model:'network-routing-model.js', page:'packet_path_lab.html', back:'cpp_station7_linux_networks.html#section=netlab-packet-walk'},
  {id:'vpn-tunnels', model:'network-vpn-model.js', page:'vpn_tunnels_lab.html', back:'cpp_station7_networking.html#section=vpn-network-context'}
];
const available = LABS.filter(lab => exists('roadmap/assets/' + lab.model));
assert(pendingAllowed || available.length === LABS.length, 'All four network models must exist; --available is only a temporary development smoke run');

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

function environment(lab, hash = '', options = {}) {
  const document = createDOM('roadmap/' + lab.page);
  const proto = Object.getPrototypeOf(document.body), originalMatches = proto.matches;
  proto.matches = function (selector) {
    if (/^#[\w-]+$/.test(selector)) return this.id === selector.slice(1);
    return originalMatches.call(this, selector);
  };
  proto.scrollIntoView = function (value) { this.lastScroll = value; };
  document.querySelector = selector => document.body.querySelector(selector);
  const config = new proto.constructor('script', {id:'network-lab-config', type:'application/json'});
  config.textContent = JSON.stringify({id:lab.id}); document.body.append(config);
  for (const id of ['return-to-section', 'return-to-theory']) document.getElementById(id).setAttribute('href', lab.back);
  document.getElementById('experiment').style.setProperty = function (name, value) { this[name] = value; };
  const listeners = {}, timers = new Map(), history = [hash];
  let cursor = 0, nextTimer = 0;
  const window = {
    location:{hash}, matchMedia:() => ({matches:!!options.reduced}),
    addEventListener:(name, callback) => { listeners[name] = callback; },
    setInterval:(callback, delay) => { timers.set(++nextTimer, {callback, delay}); return nextTimer; },
    clearInterval:id => { timers.delete(id); }
  };
  window.history = {
    replaceState:(_data, _title, value) => { window.location.hash = value; history[cursor] = value; },
    pushState:(_data, _title, value) => { window.location.hash = value; history.splice(cursor + 1); history.push(value); cursor++; },
    back:() => { if (cursor > 0) { window.location.hash = history[--cursor]; listeners.popstate(); } },
    forward:() => { if (cursor + 1 < history.length) { window.location.hash = history[++cursor]; listeners.popstate(); } }
  };
  new Function('window', read('roadmap/generated/visual-labs.data.js'))(window);
  for (const item of available) new Function('window', 'globalThis', read('roadmap/assets/' + item.model))(window, window);
  if (options.changeModel) window.NetworkLabModels[lab.id] = options.changeModel(window.NetworkLabModels[lab.id]);
  new Function('window', 'document', 'URLSearchParams', read('roadmap/assets/network-labs.js'))(window, document, Params);
  const get = id => { const node = document.getElementById(id); assert(node, 'Missing control: ' + id); return node; };
  const dispatch = (node, type, values = {}) => {
    assert(node && node.listeners[type], 'Missing handler: ' + type);
    assert(!node.disabled, 'Dispatch on disabled control: ' + (node.id || node.tagName));
    node.listeners[type].call(node, Object.assign({target:node, currentTarget:node, preventDefault() {}}, values));
  };
  const click = id => dispatch(get(id), 'click');
  const choose = selector => { const node = document.querySelector(selector); assert(node, 'Missing selector: ' + selector); node.focus(); dispatch(node, 'click'); return node; };
  const range = value => { get('step-range').value = String(value); dispatch(get('step-range'), 'input'); };
  const scenario = value => { get('scenario').value = value; dispatch(get('scenario'), 'change'); };
  const route = value => { window.location.hash = value; listeners.hashchange(); };
  const tick = () => { assert(timers.size === 1, 'Exactly one active autoplay timer'); [...timers.values()][0].callback(); };
  return {document, window, listeners, timers, history, get, dispatch, click, choose, range, scenario, route, tick, model:window.NetworkLabModels[lab.id]};
}

const message = step => !!(step.from && step.to);
let states = 0, viewChecks = 0, entries = 0, losses = 0, phaseChecks = 0, rangeDescriptions = 0;
for (const lab of available) {
  const initial = environment(lab), model = initial.model;
  if (lab.id === 'tcp-delivery') {
    initial.click('play');
    initial.click('try-tcp-order');
    assert(!initial.timers.size && initial.document.activeElement === initial.get('tcp-order-title'), 'Enter independent TCP experiment: pause playback and move focus');
    initial.document.listeners.keydown({target:initial.document.activeElement,key:'ArrowRight',preventDefault(){throw Error('Workbench focus must not advance the guided scenario');}});
    const control = initial.get('tcp-deliver-2'); control.focus();
    initial.click('tcp-deliver-2');
    assert(initial.document.activeElement === control && initial.get('tcp-order-ack').textContent === 'ACK 1001', 'Final segment arriving first keeps focus and ACK at the gap');
    assert(initial.get('tcp-order-state-2').textContent === 'За пропуском', 'Buffer state is visible as text, not just a color');
    assert(initial.get('tcp-byte-1001').dataset.arrival==='gap' && initial.get('tcp-byte-1009').dataset.arrival==='buffered' && initial.get('tcp-order-tape').dataset.edge==='0', 'Byte ribbon shows the hole and buffered suffix separately');
    initial.click('tcp-deliver-0'); initial.click('tcp-deliver-1');
    assert(initial.get('tcp-order-ack').textContent === 'ACK 1013' && initial.get('tcp-order-reason').textContent.includes('буфере'), 'Middle arrival releases last part');
    assert(initial.get('tcp-order-tape').dataset.edge==='12' && initial.get('tcp-byte-1012').dataset.arrival==='continuous', 'Marker reaches far edge only when gap is closed');
    initial.click('tcp-deliver-2');
    assert(initial.get('tcp-order-reason').textContent.includes('Копия') && initial.get('tcp-order-ack').textContent === 'ACK 1013', 'Copy suppressed');
    const firstStep = initial.get('step-counter').textContent;
    initial.click('tcp-order-reset');
    assert(firstStep === initial.get('step-counter').textContent && initial.get('tcp-order-ack').textContent === '—' && initial.get('tcp-order-state-2').textContent === 'Нет на сервере', 'Reset only independent receiver');
  } else {
    assert(!initial.document.getElementById('try-tcp-order'), 'No irrelevant TCP workbench on ' + lab.id);
  }
  if(lab.id==='packetpath'){
    const panel=initial.get('mtu-probe');
    assert(panel.hidden, 'MTU controls are scoped to IPv6 PMTU');
    initial.scenario('pmtu6'); assert(!panel.hidden, 'Bound IPv6 scenario reveals probe');
    initial.click('play'); initial.click('mtu-send-1399');
    assert(!initial.timers.size && initial.get('mtu-math').textContent.includes('1351') && initial.get('mtu-wan').dataset.verdict==='fits', '1399 passes; pause playback for the probe');
    initial.click('mtu-send-1400');
    assert(initial.get('mtu-math').textContent.includes('1352') && initial.get('mtu-wan').dataset.verdict==='fits', 'Boundary is inclusive');
    initial.click('mtu-deliver-ptb'); assert(initial.get('mtu-estimate').textContent==='1500 байт', 'No PTB exists for a packet that fits');
    initial.click('mtu-send-1401');
    assert(initial.get('mtu-wan').dataset.verdict==='overflow' && initial.get('mtu-ruler').querySelector('[data-cut="1401"]').dataset.fill==='overflow', 'Overflow on byte 1401, whole packet dropped');
    assert(initial.get('mtu-estimate').textContent==='1500 байт' && initial.get('mtu-deliver-ptb').getAttribute('aria-disabled')==='false', 'Sender cannot see remote decision until feedback arrives');
    initial.get('mtu-deliver-ptb').focus(); initial.click('mtu-deliver-ptb');
    assert(initial.get('mtu-estimate').textContent==='1400 байт' && initial.get('mtu-wan').dataset.verdict==='overflow' && initial.document.activeElement===initial.get('mtu-deliver-ptb'), 'PTB updates sender only, no repair and no lost focus');
    initial.click('mtu-reset'); assert(initial.get('mtu-wan').textContent==='—' && initial.get('mtu-estimate').textContent==='1500 байт', 'Reset independent probe');
    initial.click('mtu-send-1401'); initial.scenario('snat'); initial.scenario('pmtu6');
    assert(initial.get('mtu-wan').textContent==='—' && !panel.open, 'Fresh probe after leaving the relevant scenario');
  }
  if(lab.id==='network-setup'){
    const e=environment(lab);
    const snapshot=()=>e.get('observation-picture').textContent;
    assert(snapshot().includes('Адреса ещё нет') && !snapshot().includes('192.0.2.20'),'Do not invent a lease before the offer');
    e.click('play');
    const button=e.choose('[data-observe="dhcp-ack"]');
    assert(!e.timers.size && e.document.activeElement===button && button.getAttribute('aria-current')==='step','A snapshot stops autoplay and keeps keyboard focus');
    assert(snapshot().includes('Аренда подтверждена') && !snapshot().includes('Адрес используется'),'ACK is not yet use of the IPv4 address');
    e.choose('[data-observe="dhcp-announce"]'); assert(snapshot().includes('Адрес используется'),'First announcement enables use in this example');
    e.window.history.back(); assert(snapshot().includes('Аренда подтверждена'),'Back restores previous snapshot');
    e.scenario('arp'); assert(e.get('network-observation').hidden,'No lease experiment in the ARP lesson');
  }
  if(lab.id==='vpn-tunnels'){
    const e=environment(lab), picture=()=>e.get('observation-picture').textContent;
    for(const mode of ['split','full']){
      e.scenario(mode); e.choose('[data-observe="inner-office"]');
      assert(picture().includes('172.19.115.180') && !picture().includes('203.0.113.5'),'Inner view shows service, not tunnel endpoint');
      e.choose('[data-observe="outer-office"]');
      assert(picture().includes('198.51.100.10') && picture().includes('40000 → 51820') && !picture().includes('172.19.115.180'),'Internet observation excludes inner addresses; NAT already happened');
      e.choose('[data-observe="gateway-decrypt"]'); assert(picture().includes('10.7.0.2') && picture().includes('172.19.115.180'),'Recovered addresses are the ones in the original packet');
    }
    e.scenario('missing-route'); assert(e.get('network-observation').hidden,'Do not depict delivery on broken route');
  }
  assert(initial.get('page-title').textContent === model.title, lab.id + ': page title');
  assert(model.introduction.paragraphs.every(p => initial.get('intro-paragraphs').textContent.includes(p)), lab.id + ': complete visible introduction');
  assert(initial.get('intro-goal').textContent === model.introduction.goal && initial.get('intro-action').textContent === model.introduction.action, lab.id + ': goal/action');
  assert(model.assumptions.every(p => initial.get('assumptions').textContent.includes(p)), lab.id + ': all assumptions');
  assert(model.sources.every(s => initial.get('sources').textContent.includes(s.title) && initial.get('sources').textContent.includes(s.description)), lab.id + ': source descriptions');
  for (const scenario of model.scenarios) {
    const e = environment(lab, '#scenario=' + scenario.id + '&step=0');
    const list = model.getSteps(scenario.id);
    assert(e.get('scenario').value === scenario.id && e.get('previous').disabled && e.get('reset').disabled, 'Start bounds: ' + lab.id + '/' + scenario.id);
    for (let index = 0; index < list.length; index++) {
      e.range(index);
      const step = list[index], state = model.getState(scenario.id, index), label = lab.id + '/' + scenario.id + '/' + step.id;
      assert(e.get('step-title').textContent === step.title && e.get('step-range').getAttribute('aria-valuetext') === step.title, label + ': current accessible title');
      assert(e.get('step-counter').textContent === 'Шаг ' + (index + 1) + ' из ' + list.length, label + ': counter');
      for (const phase of model.phases) {
        const positions = list.map((s, i) => s.phase === phase.id ? i : -1).filter(i => i >= 0);
        const last = positions.length ? positions[positions.length - 1] : -1;
        const done = last >= 0 && last < index;
        const phaseButton = e.document.querySelector('[data-phase="' + phase.id + '"]');
        assert(phaseButton.getAttribute('class').split(/\s+/).includes('is-done') === done, label + ': topic complete only after its last actual event: ' + phase.id);
        assert((phaseButton.querySelector('.phase-number').textContent === '✓') === done, label + ': no premature completion tick: ' + phase.id);
        phaseChecks++;
      }
      assert([step.summary, ...step.paragraphs, step.changed, step.visible].every(p => e.get('explanation').textContent.includes(p)), label + ': no explanation omitted');
      for (const sourceId of step.sourceIds || []) {
        const source = model.sources.find(item => item.id === sourceId);
        assert(source && e.get('explanation').textContent.includes(source.title), label + ': exact supporting source exposed');
      }
      for (const fact of state.facts || []) assert(e.get('participant-state').textContent.includes(fact.label) && e.get('participant-state').textContent.includes(fact.value), label + ': participant fact');
      const panels = e.get('mechanism-panels');
      assert(panels.querySelectorAll('.mechanism-panel').length === (state.panels || []).length, label + ': all mechanism panels');
      for (const panel of state.panels || []) {
        assert(panels.textContent.includes(panel.title), label + ': panel title');
        if (panel.note) assert(panels.textContent.includes(panel.note), label + ': panel caveat');
        if (panel.type === 'note') assert(panels.textContent.includes(panel.text), label + ': note');
        if (panel.type === 'packet') for (const layer of panel.layers) assert([layer.name, layer.value, layer.detail].every(v => panels.textContent.includes(v)), label + ': complete packet layer');
        if (panel.type === 'table') for (const value of [...panel.columns, ...panel.rows.flat()]) assert(panels.textContent.includes(value), label + ': complete table');
        if (panel.type === 'ranges') for (const row of panel.rows) {
          assert(panels.textContent.includes(row.label), label + ': range row');
          for (const segment of row.segments) {
            assert(panels.textContent.includes(segment.label), label + ': range segment');
            if (segment.description) { assert(panels.textContent.includes(segment.description), label + ': authored range description retained'); rangeDescriptions++; }
          }
        }
      }
      const expectedMessages = list.slice(0, index + 1).filter(message).length;
      assert(e.get('journal').querySelectorAll('[data-journal-step]').length === expectedMessages, label + ': journal has only past transmissions');
      assert(e.get('previous').disabled === (index === 0) && e.get('next').disabled === (index === list.length - 1), label + ': navigation bounds');
      assert(e.get('inspect-message').disabled === !(step.fields && step.fields.length), label + ': inspector enabled only for available fields');
      assert(e.get('announcement').textContent.includes(step.title) && e.get('announcement').textContent.includes(step.changed), label + ': live current state');
      assert(e.get('scene').querySelector('svg') && e.get('scene').querySelector('title').textContent.length > 0 && e.get('scene').querySelector('desc').textContent.includes('логические пути'), label + ': accessible real SVG and abstraction boundary');
      if (step.lost) {
        losses++;
        assert(e.get('scene').querySelector('.loss-cross'), label + ': loss explicitly drawn');
        const target = model.getTopology(scenario.id).nodes.find(node => node.id === step.to);
        const groups = e.get('scene').querySelectorAll('g').filter(g => g.querySelector('use') && g.textContent.includes(target.title));
        assert(groups.length === 1 && !groups[0].querySelector('.node-halo'), label + ': lost packet must not activate receiver');
        assert(e.get('journal').textContent.includes('не доставлено'), label + ': loss journal wording');
      }
      states++;
      e.choose('[data-panel="fields"]');
      assert(!e.get('fields').hidden && e.get('explanation').hidden, label + ': fields exclusive');
      for (const f of step.fields || []) {
        assert(e.get('fields').textContent.includes(f.title || f.layer), label + ': field group');
        for (const value of f.items.flat()) assert(e.get('fields').textContent.includes(value), label + ': inspector contains authored value');
      }
      e.choose('[data-view="sequence"]');
      assert(!e.get('scene').querySelector('svg') && e.get('scene').querySelector('.network-sequence'), label + ': sequence/network exclusive');
      assert(e.get('scene').querySelectorAll('[data-sequence-step]').length === expectedMessages, label + ': no future sequence messages');
      e.choose('[data-view="network"]'); e.choose('[data-panel="explain"]'); viewChecks += 2;
    }
    assert(e.get('play').disabled, 'Autoplay disabled at end');
    e.click('reset'); e.click('next'); e.click('previous');
    assert(e.get('step-range').value === '0', 'Reset and next/previous round trip');
    for (const variant of model.scenarios) { e.scenario(variant.id); assert(e.get('scenario').value === variant.id && e.get('step-range').value === '0' && !e.get('explanation').hidden, 'Scenario switch resets event/explanation'); }
  }

  const e = environment(lab), firstScenario = model.scenarios[0].id, list = model.getSteps(firstScenario);
  const firstMessage = list.findIndex(message);
  assert(firstMessage >= 0, lab.id + ': has an actual exchange');
  e.range(firstMessage); e.choose('[data-inspect="true"]');
  assert(!e.get('fields').hidden && e.document.activeElement === e.document.querySelector('[data-panel="fields"]'), 'Scene inspection has stable focus');
  e.choose('[data-view="sequence"]'); e.choose('[data-sequence-step="' + firstMessage + '"]');
  assert(e.get('step-range').value === String(firstMessage) && e.document.activeElement === e.get('step-title'), 'Sequence goes to exact event with stable focus');
  e.choose('[data-journal-step="' + firstMessage + '"]');
  assert(!e.get('fields').hidden && e.document.activeElement === e.get('step-title'), 'Journal goes to fields with stable focus');
  for (const phase of model.phases) {
    const expected = list.findIndex(step => step.phase === phase.id), button = e.document.querySelector('[data-phase="' + phase.id + '"]');
    // The tiny DOM helper does not reflect HTML boolean attributes into JS
    // properties; check the emitted native disabled attribute for these nodes.
    assert((button.disabled || button.getAttribute('disabled') !== null) === (expected < 0), 'Unavailable phase disabled');
    if (expected >= 0) { e.choose('[data-phase="' + phase.id + '"]'); assert(e.get('step-range').value === String(expected) && e.document.activeElement === e.get('step-title'), 'Phase selects its first actual event'); }
  }
  e.range(1); e.choose('[data-panel="fields"]');
  const oldHash = e.window.location.hash; e.click('next'); const nextHash = e.window.location.hash;
  e.window.history.back(); assert(e.window.location.hash === oldHash && !e.get('fields').hidden, 'History back restores exact state');
  e.window.history.forward(); assert(e.window.location.hash === nextHash, 'History forward restores exact state');

  const t = environment(lab);
  t.click('play'); assert(t.timers.size === 1 && [...t.timers.values()][0].delay === 5000 && t.get('play').getAttribute('aria-pressed') === 'true', 'Five-second autoplay starts explicitly');
  t.tick(); assert(t.get('step-range').value === '1', 'Autoplay advances');
  t.click('next'); assert(t.timers.size === 0, 'Manual navigation cancels autoplay');
  t.click('play'); t.click('play'); assert(t.timers.size === 0 && t.get('play').getAttribute('aria-pressed') === 'false', 'Pause cancels timer');
  t.click('play'); t.scenario(firstScenario); assert(t.timers.size === 0, 'Scenario cancels timer');
  t.click('play'); t.choose('[data-view="sequence"]'); assert(t.timers.size === 0, 'View cancels timer');
  t.click('play'); t.choose('[data-panel="fields"]'); assert(t.timers.size === 0, 'Panel cancels timer');
  t.click('play'); t.route('#scenario=' + firstScenario + '&step=1'); assert(t.timers.size === 0, 'Hash navigation cancels timer');
  t.click('play'); t.click('inspect-message'); assert(t.timers.size === 0, 'Inspector cancels timer');
  t.click('play'); t.document.hidden = true; t.document.listeners.visibilitychange(); assert(t.timers.size === 0, 'Hidden tab cancels timer');
  t.document.hidden = false; t.range(list.length - 2); t.click('play'); t.tick();
  assert(t.timers.size === 0 && t.get('play').disabled, 'Autoplay stops at final event');

  const keys = environment(lab); let prevented = false;
  keys.document.listeners.keydown({target:keys.document.body,key:'ArrowRight',preventDefault(){prevented=true;}});
  assert(prevented && keys.get('step-range').value === '1', 'Body shortcut works');
  for (const id of ['next', 'scenario', 'step-range', 'scene']) {
    prevented = false; keys.document.listeners.keydown({target:keys.get(id),key:'ArrowRight',preventDefault(){prevented=true;}});
    assert(!prevented && keys.get('step-range').value === '1', 'Native keys retained on ' + id);
  }
  const tableIndex = list.findIndex((_, index) => (model.getState(firstScenario, index).panels || []).some(panel => panel.type === 'table'));
  if (tableIndex >= 0) {
    keys.range(tableIndex);
    const table = keys.get('mechanism-panels').querySelector('.mechanism-table-wrap');
    assert(table && table.getAttribute('tabindex') === '0', 'Wide mechanism table is keyboard-focusable');
    prevented = false;
    keys.document.listeners.keydown({target:table,key:'ArrowRight',preventDefault(){prevented=true;}});
    assert(!prevented && keys.get('step-range').value === String(tableIndex), 'Table arrow keys retain native horizontal scrolling');
    keys.range(1);
  }
  keys.document.listeners.keydown({target:keys.document.body,key:'ArrowRight',altKey:true,preventDefault(){throw Error('Modified shortcut intercepted');}});
  const preserved = keys.window.location.hash, historyLength = keys.history.length;
  keys.choose('.skip-link'); assert(keys.document.activeElement === keys.get('experiment') && keys.window.location.hash === preserved && keys.history.length === historyLength, 'Skip link focuses without restarting selected state');
  keys.choose('.start-button'); assert(keys.document.activeElement === keys.get('experiment') && keys.window.location.hash === preserved, 'Introduction button reveals existing experiment, not a hidden reset');

  const invalid = environment(lab, '#scenario=%ZZ&step=NaN&view=oops&panel=oops');
  assert(invalid.get('scenario').value === firstScenario && invalid.get('step-range').value === '0', 'Malformed route has safe defaults');
  const upper = environment(lab, '#scenario=' + firstScenario + '&step=999999'); assert(upper.get('next').disabled, 'Route upper bound');
  const precedence = environment(lab, '#scenario=' + firstScenario + '&phase=' + list[list.length - 1].phase + '&step=1'); assert(precedence.get('step-range').value === '1', 'Explicit step overrides phase');

  const entryLab = (initial.window.COURSE_LABS || []).find(item => item.id === lab.id && item.file === lab.page);
  assert(pendingAllowed || entryLab, 'Canonical catalog entry exists for ' + lab.id);
  if (entryLab) {
    for (const entry of entryLab.entries) {
      const href = initial.window.courseLabHref(lab.id, entry.scenario, entry.station, entry.section), opened = environment(lab, href.slice(href.indexOf('#')));
      const target = entry.file + '#section=' + encodeURIComponent(entry.section);
      const assertContext = () => { const p = new Params(opened.window.location.hash.slice(1)); assert(p.get('from') === entry.station && p.get('section') === entry.section, 'Return context retained'); assert(opened.get('return-to-section').href === target && opened.get('return-to-theory').href === target, 'Exact authored return URL'); };
      assert(href.startsWith(lab.page + '#'), 'Catalog opens standalone page');
      const first = model.getSteps(entry.scenario).findIndex(step => step.phase === entry.phase);
      assert(Number(opened.get('step-range').value) === Math.max(0, first), 'Catalog phase entry opens actual phase');
      opened.click('next'); assertContext(); opened.choose('[data-view="sequence"]'); assertContext(); opened.choose('[data-panel="fields"]'); assertContext(); opened.scenario(firstScenario); assertContext(); opened.range(1); assertContext();
      const before = opened.window.location.hash; opened.click('next'); opened.window.history.back(); assert(opened.window.location.hash === before, 'Context survives browser back'); assertContext(); entries++;
    }
  }
  for (const malicious of [
    '&from=https%3A%2F%2Fevil.example&section=topic',
    '&from=station7&section=javascript%3Aalert(1)',
    '&from=station7&section=topic%22%20onclick%3Dbad()',
    '&from=__proto__&section=constructor'
  ]) {
    const rejected = environment(lab, '#scenario=' + firstScenario + malicious);
    for (const id of ['return-to-section', 'return-to-theory']) assert((rejected.get(id).href || rejected.get(id).getAttribute('href')) === lab.back, 'Invalid context keeps exact authored local fallback');
    rejected.click('next'); const p = new Params(rejected.window.location.hash.slice(1)); assert(p.get('from') === null && p.get('section') === null, 'Invalid context discarded on navigation');
  }
  const reduced = environment(lab, '', {reduced:true}); reduced.range(firstMessage); assert(!reduced.get('scene').querySelector('animateMotion'), 'Reduced motion suppresses traveling envelope');
  const motion = environment(lab); motion.range(firstMessage); assert(motion.get('scene').querySelector('animateMotion'), 'User event allows bounded one-shot motion');
  const attack = '<img src=x onerror="bad()"> & <script>bad()</script>';
  const literal = environment(lab, '#scenario=' + firstScenario + '&step=' + firstMessage, {changeModel(base) {
    const modified = JSON.parse(JSON.stringify(base.getSteps(firstScenario)));
    Object.assign(modified[firstMessage], {title:attack,summary:attack,paragraphs:[attack],changed:attack,visible:attack,label:attack,fields:[{layer:attack,title:attack,items:[[attack,attack,attack]]}]});
    return Object.assign({}, base, {getSteps:() => modified, getState:() => ({facts:[{label:attack,value:attack}],panels:[{type:'packet',title:attack,layers:[{name:attack,value:attack,detail:attack}]},{type:'table',title:attack,columns:[attack],rows:[[attack]]},{type:'note',title:attack,text:attack}]})});
  }});
  literal.click('inspect-message');
  assert(literal.get('step-title').textContent === attack && literal.get('fields').textContent.includes(attack), 'Authored strings stay literal');
  for (const id of ['scene','explanation','fields','journal','participant-state','mechanism-panels']) assert(literal.get(id).querySelectorAll('img').length === 0 && literal.get(id).querySelectorAll('script').length === 0, 'No HTML injection in ' + id);
}
// Small synthetic renderer fixtures isolate display contracts from whichever
// packet examples happen to be present in a particular course model.
const fixtureLab = available[0];
assert(fixtureLab, 'At least one model is needed for the renderer fixtures');
function fixtureModel(base, patch = {}) {
  const original = base.getSteps(base.scenarios[0].id)[0];
  const step = Object.assign({}, original, {id:'fixture',phase:base.phases[0].id,
    from:'client',to:'a',broadcastTo:['a','b'],protocol:'ip',label:'Broadcast fixture'});
  const topology = {width:880,height:380,nodes:[
    {id:'client',title:'Клиент',address:'Учебный источник',kind:'laptop',x:90,y:180},
    {id:'switch',title:'Коммутатор',address:'Общий участок',kind:'switch',x:300,y:180},
    {id:'a',title:'Получатель A',address:'Учебная ветвь A',kind:'server',x:600,y:80},
    {id:'b',title:'Получатель B',address:'Учебная ветвь B',kind:'server',x:600,y:280}
  ],links:[
    {from:'client',to:'switch',label:'Короткий общий участок'},
    {from:'switch',to:'a',label:'Длинная ветвь A'},
    {from:'switch',to:'b',label:'Длинная ветвь B'}
  ]};
  return Object.assign({}, base, {getSteps:() => [step],getTopology:() => topology,
    getState:() => ({facts:[],panels:[]})}, patch);
}
const broadcast = environment(fixtureLab, '', {changeModel:base => fixtureModel(base)});
broadcast.range(0);
const flights = broadcast.get('scene').querySelectorAll('animateMotion');
assert(flights.length === 3, 'Broadcast emits one shared-prefix flight and two outgoing copies, not duplicated whole paths');
const shared = flights.filter(f => f.getAttribute('path') === 'M 90 180 L 300 180');
assert(shared.length === 1 && shared[0].getAttribute('begin') === '0s' && shared[0].getAttribute('dur') === '0.6s', 'Shared client→switch frame travels once');
for (const end of ['600 80','600 280']) {
  const branch = flights.filter(f => f.getAttribute('path') === 'M 300 180 L ' + end);
  assert(branch.length === 1 && branch[0].getAttribute('begin') === '0.6s' && branch[0].getAttribute('dur') === '0.6s', 'Fanout starts at switch only after shared-prefix flight: ' + end);
}
const routeLabels = broadcast.get('scene').querySelectorAll('.route-note').map(node => node.textContent);
assert(!routeLabels.includes('Короткий общий участок') && routeLabels.includes('Длинная ветвь A') && routeLabels.includes('Длинная ветвь B'), 'Links of 210 SVG units or less suppress decorative captions; long links keep them');
const reducedBroadcast = environment(fixtureLab, '', {reduced:true,changeModel:base => fixtureModel(base)});
reducedBroadcast.range(0);
assert(reducedBroadcast.get('scene').querySelectorAll('animateMotion').length === 0, 'Reduced motion suppresses the whole broadcast fanout');
const rangeAttack = '<img src=x onerror="bad()"> & описание диапазона';
const rangeFixture = environment(fixtureLab, '', {changeModel:base => fixtureModel(base, {
  getState:() => ({facts:[],panels:[{type:'ranges',title:'Fixture диапазонов',rows:[{label:'Результат',segments:[
    {label:'Описанный диапазон',status:'delivered',description:rangeAttack},
    {label:'Стандартная подпись',status:'buffered'},
    {label:'Неизвестный статус',status:'__proto__'}
  ]}]}]})
})});
const segments = rangeFixture.get('mechanism-panels').querySelectorAll('.range-segment');
assert(segments[0].querySelector('small').textContent === rangeAttack, 'Optional description replaces generic range status text');
assert(segments[1].querySelector('small').textContent === 'Ждёт в буфере', 'Range without description uses known status fallback');
assert(segments[2].getAttribute('class').includes('status-waiting') && segments[2].querySelector('small').textContent === 'Ещё не отправлено', 'Unknown range status has safe waiting fallback, not prototype lookup');
assert(rangeFixture.get('mechanism-panels').querySelectorAll('img').length === 0, 'Range descriptions remain escaped text');
const controller = read('roadmap/assets/network-labs.js');
assert(!/\bfetch\s*\(|XMLHttpRequest|\bWebSocket\s*\(|\beval\s*\(|localStorage|sessionStorage/.test(controller), 'Controller does not send requests/evaluate code/write progress');
assert(read('roadmap/templates/network_lab.html').includes('aria-live="polite"'), 'Template has live event announcement');
print('PASS: network controllers — ' + available.length + '/4 models, ' + states + ' states, ' + viewChecks + ' view checks, ' + phaseChecks + ' topic-completion checks, ' + rangeDescriptions + ' authored range descriptions, ' + losses + ' losses, ' + entries + ' catalog entries; fanout/short-link fixtures, explanations, fields, panels, keyboard/focus, hash/history, five-second autoplay and literal data. DOM model only; rendering not verified.' + (pendingAllowed ? ' DEVELOPMENT --available RUN.' : ''));
