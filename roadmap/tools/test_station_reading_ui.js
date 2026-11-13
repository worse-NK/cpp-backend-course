// Run: gjs roadmap/tools/test_station_reading_ui.js
// Real shared components, isolated React hooks/storage and canonical fixtures.
// No browser, real learner storage, server, network, or generated-file writes.
// These are component contracts, not a visual/accessibility/browser-history audit.
const GLib = imports.gi.GLib, BA = imports.byteArray;
const read = path => BA.toString(GLib.file_get_contents(path)[1]);
function assert(ok, message) { if (!ok) throw new Error(message); }
function nodes(value) {
    if (!value || typeof value !== 'object') return [];
    return [value, ...(value.children || []).flatMap(nodes)];
}
function text(value) {
    if (value == null || typeof value === 'boolean') return '';
    return typeof value === 'object' ? (value.children || []).map(text).join('') : String(value);
}
const button = (tree, label) => nodes(tree).find(n => n.type === 'button' && text(n) === label);
const isWorkbook = section => /(?:-final-workbook|clock-worked-example)$/.test(section.id);
const appSource = read('roadmap/assets/station-app.js');
new Function(appSource);
class Params {
    constructor(query) {
        this.values = String(query || '').split('&').map(pair => {
            const cut = pair.indexOf('='), decode = s => decodeURIComponent(s.replace(/\+/g, ' '));
            return cut < 0 ? [decode(pair), ''] : [decode(pair.slice(0, cut)), decode(pair.slice(cut + 1))];
        });
    }
    get(key) { const entry = this.values.find(pair => pair[0] === key); return entry ? entry[1] : null; }
}
function loadStation(id) {
    const data = JSON.parse(read('roadmap/content/' + id + '.json'));
    const plan = JSON.parse(read('roadmap/content/checkpoints/' + id + '.json'));
    data.checkpoints = Object.fromEntries(Object.entries(plan.modules).map(([module, questions]) => [
        module, questions.map(q => q.bank ? data.quizzes[q.bank][q.index] : q)
    ]));
    return data;
}
function orderedSections(data, module) {
    const sections = data.theory.filter(s => s.substation === module && !isWorkbook(s));
    if (data.readingOrder) sections.sort((a, b) => data.readingOrder.indexOf(a.id) - data.readingOrder.indexOf(b.id));
    return sections;
}
function environment(data, hash, options = {}) {
    let active;
    const normal = data.theory.filter(s => !isWorkbook(s));
    const original = {
        readingRoute: false, activeSubstation: data.substations[0].id,
        ['sec:' + normal[0].id]: false,
        ['sec:' + normal[1].id]: false,
        ['sec:' + normal[normal.length - 1].id]: true,
        'station-final:coverage:v1:basic': {score:21, total:25},
        'station-final:editorial-20261029:v1:interview': {score:7, total:12},
        'checkpoint:v2:legacy-module': {score:2, total:3},
        'station-training:v1:legacy': {score:3, total:5},
        learnerNote: 'Keep this unknown field too'
    };
    const backing = {[data.meta.storeKey]:JSON.stringify(original)}, writes = [], listeners = {};
    const scrolls = [], focuses = [], animationFrames = [];
    const elements = Object.fromEntries(['root', 'lesson-content'].map(id => [id, {
        id, focus:settings => { doc.activeElement = elements[id]; focuses.push({id, settings}); },
        scrollIntoView:settings => scrolls.push({id, settings})
    }]));
    const doc = {activeElement:null, getElementById:id => elements[id] || null};
    const win = {
        STATION_DATA:data, COURSE_LABS:[], location:{hash:hash || '', protocol:'file:'},
        scrollTo:settings => scrolls.push({id:'window', settings}),
        matchMedia:() => ({matches:!!options.reducedMotion}),
        requestAnimationFrame:callback => { animationFrames.push(callback); return animationFrames.length; },
        addEventListener:(name, fn) => { (listeners[name] ||= new Set()).add(fn); },
        removeEventListener:(name, fn) => { if (listeners[name]) listeners[name].delete(fn); }
    };
    const React = {
        createElement:(type, props, ...children) => ({type, props:props || {}, children:children.flat(Infinity)}),
        useState:initial => {
            const owner = active, index = owner.cursor++;
            if (!(index in owner.cells)) owner.cells[index] = typeof initial === 'function' ? initial() : initial;
            return [owner.cells[index], value => {
                owner.cells[index] = typeof value === 'function' ? value(owner.cells[index]) : value;
            }];
        },
        useRef:initial => {
            const owner = active, index = owner.cursor++;
            if (!(index in owner.cells)) owner.cells[index] = {current:initial};
            return owner.cells[index];
        },
        useEffect:(effect, deps) => {
            const owner = active, index = owner.cursor++, previous = owner.effects[index];
            if (previous && deps && previous.deps && deps.length === previous.deps.length &&
                deps.every((value, i) => value === previous.deps[i])) return;
            if (previous && previous.cleanup) previous.cleanup();
            owner.effects[index] = {deps, pending:effect};
        }
    };
    const storage = {
        getItem:key => backing[key] || null,
        setItem:(key, value) => { backing[key] = value; writes.push({key, value}); }
    };
    const historyEntries = [win.location.hash], historyCalls = [];
    let historyIndex = 0;
    function emit(name) { for (const listener of listeners[name] || []) listener({type:name}); }
    const history = {
        replaceState:(_state, _title, next) => {
            win.location.hash = next; historyEntries[historyIndex] = next;
            historyCalls.push({method:'replace', hash:next});
        },
        pushState:(_state, _title, next) => {
            win.location.hash = next;
            historyEntries.splice(historyIndex + 1);
            historyEntries.push(next); ++historyIndex;
            historyCalls.push({method:'push', hash:next});
        },
        back:() => {
            if (!historyIndex) return;
            win.location.hash = historyEntries[--historyIndex]; emit('popstate'); emit('hashchange');
        },
        forward:() => {
            if (historyIndex + 1 >= historyEntries.length) return;
            win.location.hash = historyEntries[++historyIndex]; emit('popstate'); emit('hashchange');
        }
    };
    win.history = history;
    win.React = React; win.ReactDOM = {};
    const exported = appSource.replace('  ReactDOM.createRoot(root).render(h(App));',
        '  window.testApi = {App,Theory,SubstationNav,LabBlock};');
    assert(exported !== appSource, 'Renderer entry point changed: update the harness explicitly');
    new Function('window', 'document', 'React', 'ReactDOM', 'localStorage', 'location', 'URLSearchParams', 'history', exported)(
        win, doc, React, {}, storage, win.location, Params, history);
    function mount(component, props) {
        const owner = {cursor:0, cells:[], effects:[], props:props || {}};
        owner.render = () => {
            owner.cursor = 0; active = owner;
            let tree;
            try { tree = component(owner.props); } finally { active = null; }
            owner.effects.forEach(effect => {
                if (effect.pending) { effect.cleanup = effect.pending(); delete effect.pending; }
            });
            return tree;
        };
        owner.dispose = () => owner.effects.forEach(effect => { if (effect.cleanup) effect.cleanup(); });
        return owner;
    }
    const app = mount(win.testApi.App);
    let currentTheory, currentKey, appTree;
    function render() {
        appTree = app.render();
        assert(!nodes(appTree).some(n => n.type === 'button' &&
            ['Первое чтение', 'По темам'].includes(text(n))), data.meta.id + ': obsolete mode buttons');
        assert(!nodes(appTree).some(n => n.props['aria-label'] === 'Порядок чтения'),
               data.meta.id + ': obsolete mode controls');
        const node = nodes(appTree).find(n => n.type === win.testApi.Theory);
        if (!node) return {appTree, node:null, tree:null};
        if (!currentTheory || currentKey !== node.props.key) {
            if (currentTheory) currentTheory.dispose();
            currentKey = node.props.key; currentTheory = mount(win.testApi.Theory, node.props);
        } else currentTheory.props = node.props;
        const tree = currentTheory.render();
        return {appTree, node, tree};
    }
    function nav() { return nodes(appTree).find(n => n.type === win.testApi.SubstationNav); }
    function stored() { return JSON.parse(backing[data.meta.storeKey]); }
    function preserved(except) {
        const saved = stored();
        Object.keys(original).filter(k => k !== 'activeSubstation' && k !== except).forEach(key =>
            assert(JSON.stringify(saved[key]) === JSON.stringify(original[key]), data.meta.id + ': progress lost: ' + key));
        const allowed = new Set([...Object.keys(original), ...(except ? [except] : [])]);
        assert(Object.keys(saved).every(key => allowed.has(key)), data.meta.id + ': reading created completion/results');
        assert(writes.every(w => w.key === data.meta.storeKey || w.key === 'cpp_course_last_read_v1'),
               data.meta.id + ': unrelated storage namespace modified');
    }
    function flushAnimationFrames() {
        while (animationFrames.length) animationFrames.shift()(0);
    }
    return {data, original, win, doc, backing, writes, render, nav, stored, preserved,
        api:win.testApi, mount,
        scrolls, focuses, history, historyEntries, historyCalls, emit, flushAnimationFrames,
        dispose:() => { if (currentTheory) currentTheory.dispose(); app.dispose();
            assert(Object.values(listeners).every(set => set.size === 0), 'Navigation listeners leaked'); }};
}
let sectionLists = 0, transitions = 0, checkpoints = 0, workbooks = 0;
function expectSection(view, expected, index, count) {
    assert(view.node && view.tree, 'Expected a theory page');
    const title = nodes(view.tree).find(n => n.props.className === 'section-title');
    assert(title && text(title) === expected.title, 'Wrong current section: ' + expected.id);
    const counter = nodes(view.tree).find(n => n.props.className === 'kicker' && /^РАЗДЕЛ /.test(text(n)));
    assert(counter && text(counter) === 'РАЗДЕЛ ' + (index + 1) + ' / ' + count,
           'Counter must describe the current chapter, not a global route: ' + expected.id);
    assert(!nodes(view.tree).some(n => n.props.className === 'kicker' && /^ПЕРВОЕ ЧТЕНИЕ/.test(text(n))),
           'Obsolete global reading counter');
}
const directory = GLib.Dir.open('roadmap/content', 0), ids = [];
for (let name; (name = directory.read_name()) !== null;) {
    if (/^station\d+(?:-[a-z]+)?\.json$/.test(name)) ids.push(name.replace(/\.json$/, ''));
}
ids.sort((a, b) => Number(a.match(/\d+/)[0]) - Number(b.match(/\d+/)[0]) || a.localeCompare(b));
assert(ids.length === 21, 'Expected all twenty-one current station fixtures');
for (const id of ids) {
    const data = loadStation(id), before = JSON.stringify(data), env = environment(data);
    let view = env.render();
    for (const module of data.substations) {
        const expected = orderedSections(data, module.id);
        assert(expected.length, id + ': chapter has no normal theory');
        env.nav().props.onChoose(module.id); view = env.render();
        assert(JSON.stringify(view.node.props.sections.map(s => s.id)) === JSON.stringify(expected.map(s => s.id)),
               id + ': wrong chapter order: ' + module.id);
        ++sectionLists;
        expectSection(view, expected[0], 0, expected.length);
        assert(!button(view.tree, '← Назад'), 'First chapter section must not go back to another chapter');
        if (expected.length > 1) {
            const next = button(view.tree, 'Далее: ' + expected[1].title + ' →');
            assert(next, 'Missing next section action: ' + id + '/' + module.id);
            next.props.onClick(); view = env.render(); expectSection(view, expected[1], 1, expected.length);
            assert(env.win.location.hash === '#section=' + encodeURIComponent(expected[1].id), 'Next hash mismatch');
            const back = button(view.tree, '← Назад'); assert(back, 'Missing previous action');
            back.props.onClick(); view = env.render(); expectSection(view, expected[0], 0, expected.length);
            transitions += 2;
        }
        const last = expected[expected.length - 1];
        env.nav().props.onNavigate(last.id); view = env.render();
        expectSection(view, last, expected.length - 1, expected.length);
        const finish = button(view.tree, 'Далее: закрепление подглавы →');
        assert(finish, 'The chapter ending must open its checkpoint: ' + id + '/' + module.id);
        finish.props.onClick(); view = env.render();
        assert(!view.node && env.nav().props.view === 'checkpoint', 'Checkpoint still renders theory');
        assert(env.win.location.hash === '#view=checkpoint&module=' + encodeURIComponent(module.id), 'Wrong checkpoint module');
        env.preserved(); ++checkpoints;
    }
    const first = orderedSections(data, data.substations[0].id)[0], markKey = 'sec:' + first.id;
    env.nav().props.onNavigate(first.id); view = env.render();
    const mark = button(view.tree, 'Отметить раздел изученным'); assert(mark, 'Expected an unmarked first page');
    mark.props.onClick(); view = env.render();
    assert(env.stored()[markKey] === true && button(view.tree, '✓ Раздел изучен'), 'Mark was not persisted');
    env.preserved(markKey);
    button(view.tree, '✓ Раздел изучен').props.onClick(); view = env.render();
    assert(env.stored()[markKey] === false, 'Unmark was not persisted'); env.preserved();
    const lastRead = JSON.parse(env.backing.cpp_course_last_read_v1);
    assert(lastRead.file === data.meta.sourceFile && lastRead.section === first.id, 'Reading-position record changed meaning');
    const workbook = data.theory.find(isWorkbook);
    if (workbook) {
        env.nav().props.onNavigate(workbook.id); view = env.render();
        expectSection(view, workbook, 0, 1);
        assert(view.node.props.sections.length === 1, 'Workbook leaked back into chapter theory');
        const finish = button(view.tree, 'Далее: итоговый тест →'); assert(finish, 'Workbook ending must lead to final test');
        finish.props.onClick(); view = env.render();
        assert(!view.node && env.win.location.hash === '#view=quiz', 'Workbook completion has wrong destination');
        env.preserved(); ++workbooks;
    }
    assert(JSON.stringify(data) === before, id + ': navigation mutated canonical content');
    env.dispose();
}
// Real routes currently have the same within-chapter order as theory. A small
// synthetic permutation makes dropping the readingOrder sort detectable.
const synthetic = loadStation('station0'), module = synthetic.substations[0].id;
const ordinary = orderedSections(synthetic, module);
synthetic.readingOrder = synthetic.theory.map(s => s.id);
const a = synthetic.readingOrder.indexOf(ordinary[0].id), b = synthetic.readingOrder.indexOf(ordinary[1].id);
[synthetic.readingOrder[a], synthetic.readingOrder[b]] = [synthetic.readingOrder[b], synthetic.readingOrder[a]];
const reversed = orderedSections(synthetic, module), env = environment(synthetic, '#section=' + reversed[0].id);
let view = env.render();
assert(env.stored().readingRoute === false, 'Fixture must start with the legacy false preference');
assert(JSON.stringify(view.node.props.sections.map(s => s.id)) === JSON.stringify(reversed.map(s => s.id)),
       'A saved readingRoute:false must not disable the single readingOrder');
expectSection(view, reversed[0], 0, reversed.length);
button(view.tree, 'Далее: ' + reversed[1].title + ' →').props.onClick();
view = env.render(); expectSection(view, reversed[1], 1, reversed.length);
button(view.tree, '← Назад').props.onClick(); view = env.render(); expectSection(view, reversed[0], 0, reversed.length);
env.preserved(); env.dispose();
print('PASS: single-route component contracts; ' + ids.length + ' stations, ' + sectionLists +
      ' chapter orders, ' + transitions + ' next/back transitions, ' + checkpoints +
      ' checkpoint destinations, ' + workbooks + ' separate workbooks; legacy progress retained. No browser/network audit.');
