// Component checks without a browser or access to the user's stored progress.
const GLib = imports.gi.GLib;
const ByteArray = imports.byteArray;
function read(path) { return ByteArray.toString(GLib.file_get_contents(path)[1]); }
function assert(value, message) { if (!value) throw new Error(message); }
const writes = {};
const effects = [];
let selected = false;
globalThis.localStorage = { getItem: () => null, setItem: (k, v) => { writes[k] = v; } };
globalThis.location = { hash: '', protocol: 'file:' };
globalThis.document = {
    getElementById: () => ({}),
    createRange: () => ({ selectNodeContents: () => { selected = true; } })
};
globalThis.navigator = {};
globalThis.React = {
    createElement: (type, props, ...children) => ({ type, props: props || {}, children: children.flat(Infinity) }),
    useState: initial => [typeof initial === 'function' ? initial() : initial, () => {}],
    useRef: () => ({ current: {} }),
    useEffect: effect => effects.push(effect)
};
globalThis.ReactDOM = { createRoot: () => ({ render: () => {} }) };
const fakeWindow = {
    React: globalThis.React, ReactDOM: globalThis.ReactDOM,
    STATION_DATA: JSON.parse(read('roadmap/content/station0.json')),
    matchMedia: () => ({ matches: false }),
    getSelection: () => ({ removeAllRanges: () => {}, addRange: () => {} })
};
const source = read('roadmap/assets/station-app.js');
const fragments = source.slice(source.indexOf('  function CodeBlock('), source.indexOf('  function splitQuestion('))
    + source.slice(source.indexOf('  function SubstationNav('), source.indexOf('  function QuizPicker('));
const components = new Function('React', 'window', 'document', 'navigator', 'localStorage',
    'var h=React.createElement, useState=React.useState, data=window.STATION_DATA, meta=data.meta, theory=data.theory, noteLabels={tip:"СОВЕТ",key:"ГЛАВНОЕ"}; function isWorkbook(s){return /(?:-final-workbook|clock-worked-example)$/.test(s.id);}'
    + fragments + ';return {CodeBlock,Theory,SubstationNav};')(
        globalThis.React, fakeWindow, globalThis.document, globalThis.navigator, globalThis.localStorage);
function find(node, predicate) {
    if (!node || typeof node !== 'object') return null;
    if (predicate(node)) return node;
    for (const child of node.children || []) { const result = find(child, predicate); if (result) return result; }
    return null;
}
const code = components.CodeBlock({ block: { caption: 'Пример', code: 'int main() {}' } });
assert(find(code, n => n.type === 'pre').props.tabIndex === 0, 'Code must be keyboard focusable');
find(code, n => n.type === 'button').props.onClick();
assert(selected, 'Without clipboard permission the code must be selectable');
const output = components.CodeBlock({ block: { caption: 'Ожидаемый вывод полной программы', code: '42' } });
assert(output.props.className.includes('output-wrap'), 'Output must be visually distinct from source');
const ordinaryCode = components.CodeBlock({ block: { caption: 'Полная программа: сначала предскажи вывод', code: 'int main() {}' } });
assert(!ordinaryCode.props.className.includes('output-wrap'), 'Code mentioning output must remain a source listing');
const section = { id: 'example', title: 'Пример', blocks: [{type: 'note', html: '<b>Источники.</b> Правило', kind: 'tip'}] };
const theory = components.Theory({ sections: [section], store: {}, onNavigate: () => {} });
assert(find(theory, n => n.props.className === 'note source-note'), 'Sources must not appear as tips');
effects.forEach(effect => effect());
assert(JSON.parse(writes.cpp_course_last_read_v1).section === 'example', 'Last reading position must be stored');
assert(Object.keys(writes).length === 1, 'Reading must not mark the lesson completed');
const data = fakeWindow.STATION_DATA;
const nav = components.SubstationNav({ items: data.substations, active: data.substations[0].id, view: 'theory', store: {}, onChoose: () => {}, onNavigate: () => {} });
assert(nav.type === 'details' && nav.props.open === false, 'Small-screen contents must start collapsed');
assert(find(nav, n => n.props['aria-current'] === 'page'), 'Current section must be accessible');
assert(!find(nav, n => n.props.className === 'contents-finale'), 'No permanent top-level finale button');
assert(find(nav, n => n.props.className === 'contents-ending'), 'Final activities must follow the chapters');
let destination = '';
const endingNav = components.SubstationNav({ items: data.substations, active: data.substations[0].id, view: 'final', store: {}, onPage: page => { destination = page; } });
const ending = find(endingNav, n => n.props.className === 'contents-ending');
assert(ending.children.filter(Boolean).length === 1 && ending.children[0].type === 'button', 'Without analysis tasks finale must have a single sidebar entry');
assert(ending.children[0].children.includes('Завершение станции'), 'Finale entry must use the page name');
assert(ending.children[0].props['aria-current'] === 'page', 'Finale must indicate the current page');
ending.children[0].props.onClick();
assert(destination === 'final', 'Finale entry must open the overview, not a quiz');
const analysisNav = components.SubstationNav({ items: data.substations, active: data.substations[0].id, view: 'analysis', store: {}, analysisCount: 8, onPage: page => { destination = page; } });
const analysis = find(analysisNav, n => n.props.className === 'contents-analysis');
assert(analysis && analysis.props['aria-current'] === 'page', 'Open-answer analysis must be discoverable in ending contents');
analysis.props.onClick();
assert(destination === 'analysis', 'Analysis entry must lead directly to open answers');
const selfCheck = components.Theory({ sections: [{id:'check', title:'Проверка', blocks:[{type:'self-check',prompt:'Объясни правило',answer:'<p>Разбор правила</p>'}]}], store:{} });
const reveal = find(selfCheck, n => n.type === 'details');
assert(reveal && !reveal.props.open, 'Self-check answer must be closed initially');
assert(find(reveal, n => n.type === 'summary' && n.children.includes('Сверить с разбором')), 'Self-check must have a native keyboard-accessible reveal');
assert(find(nav, n => n.props.className === 'contents-checkpoint'), 'Chapter checkpoint must appear in the contents');
const lastPage = components.Theory({ sections: [section], store: {}, onNavigate: () => {}, onComplete: () => {} });
assert(find(lastPage, n => n.type === 'button' && n.children.includes('Далее: закрепление подглавы →')), 'Last theory page must lead to checkpoint');
data.meta.number = 9;
const sqlPage = components.Theory({ sections: [{id:'sql-null-basics', substation:'queries', title:'NULL', blocks:[]}], store:{} });
const sqlLink = find(sqlPage, n => n.type === 'a' && n.props.href === 'sql_trainer.html#null');
assert(sqlLink && sqlLink.props.target === '_blank', 'SQL lessons must link to matching exercise without replacing reading');
const sqlNav = components.SubstationNav({items:data.substations, active:data.substations[0].id, view:'theory', store:{}});
assert(find(sqlNav, n => n.type === 'a' && n.props.href === 'sql_trainer.html'), 'Database contents must provide persistent trainer access');
print('PASS: code fallback, keyboard access, source styling, reading position, progress isolation, mobile contents, SQL links');
