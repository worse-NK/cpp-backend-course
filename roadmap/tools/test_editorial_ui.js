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
const library = new Function(read('roadmap/vendor/highlightjs/highlight.min.js') + '\n;return hljs;')();
assert(library.versionString === '11.12.0', 'Use the real locally pinned highlighter');
const origin = JSON.parse(read('roadmap/vendor/highlightjs/ORIGIN.json'));
for (const name of Object.keys(origin.files))
    if (/\.js$/.test(name) && name !== 'highlight.min.js')
        new Function('hljs', read('roadmap/vendor/highlightjs/' + name))(library);
fakeWindow.hljs = library;
new Function('window', read('roadmap/assets/course-code.js'))(fakeWindow);
assert(typeof fakeWindow.CourseCode.element === 'function', 'Load the actual shared code renderer');
const fragments = source.slice(source.indexOf('  function backendLabEntry('), source.indexOf('  function PracticeLinks('))
    + source.slice(source.indexOf('  function LabFlask('), source.indexOf('  function LabBlock('))
    + source.slice(source.indexOf('  function codeElement('), source.indexOf('  function splitQuestion('))
    + source.slice(source.indexOf('  function Theory('), source.indexOf('  function QuizPicker('));
const components = new Function('React', 'window', 'document', 'navigator', 'localStorage',
    'var h=React.createElement, useState=React.useState, data=window.STATION_DATA, meta=data.meta, theory=data.theory, noteLabels={tip:"СОВЕТ",key:"ГЛАВНОЕ"}; function isWorkbook(s){return /(?:-final-workbook|clock-worked-example)$/.test(s.id);}'
    + fragments + ';return {CodeBlock,Theory};')(
        globalThis.React, fakeWindow, globalThis.document, globalThis.navigator, globalThis.localStorage);
function find(node, predicate) {
    if (!node || typeof node !== 'object') return null;
    if (predicate(node)) return node;
    for (const child of node.children || []) { const result = find(child, predicate); if (result) return result; }
    return null;
}
const code = components.CodeBlock({ block: { caption: 'Пример', code: 'int main() {}' } });
assert(find(code, n => n.type === 'pre').props.tabIndex === 0, 'Code must be keyboard focusable');
const highlighted = find(code, n => n.type === 'code');
assert(highlighted.props.className.includes('hljs') && highlighted.props.translate === 'no' &&
       highlighted.props.dangerouslySetInnerHTML.__html.includes('hljs-type'),
       'The actual production code helper emits highlighted source, not an empty stub');
find(code, n => n.type === 'button').props.onClick();
assert(selected, 'Without clipboard permission the code must be selectable');
const output = components.CodeBlock({ block: { caption: 'Ожидаемый вывод полной программы', code: '42' } });
assert(output.props.className.includes('output-wrap'), 'Output must be visually distinct from source');
const literalOutput = find(output, n => n.type === 'code');
assert(!literalOutput.props.dangerouslySetInnerHTML && literalOutput.children.join('') === '42', 'Output remains exact literal text rather than highlighted C++');
const ordinaryCode = components.CodeBlock({ block: { caption: 'Полная программа: сначала предскажи вывод', code: 'int main() {}' } });
assert(!ordinaryCode.props.className.includes('output-wrap'), 'Code mentioning output must remain a source listing');
const section = { id: 'example', title: 'Пример', blocks: [{type: 'note', html: '<b>Источники.</b> Правило', kind: 'tip'}] };
const theory = components.Theory({ sections: [section], store: {}, onNavigate: () => {} });
assert(find(theory, n => n.props.className === 'note source-note'), 'Sources must not appear as tips');
const comparison = components.Theory({ sections: [{id:'comparison', title:'Сравнение', blocks:[{type:'text',html:'<table><tbody><tr><td>Случай</td></tr></tbody></table>'}]}], store:{} });
assert(find(comparison, n => n.props.className === 'theory-text').type === 'div', 'A comparison table must not be nested in a paragraph');
const paragraph = components.Theory({ sections: [{id:'paragraph', title:'Текст', blocks:[{type:'text',html:'Обычное объяснение с <code>int</code>.'}]}], store:{} });
assert(find(paragraph, n => n.props.className === 'theory-text').type === 'p', 'Ordinary prose must remain a paragraph');
// Each Theory render schedules a reading-position effect; check the last one.
effects.forEach(effect => effect());
assert(JSON.parse(writes.cpp_course_last_read_v1).section === 'paragraph', 'Last reading position must be stored');
assert(Object.keys(writes).length === 1, 'Reading must not mark the lesson completed');
const data = fakeWindow.STATION_DATA;
const mapApi = new Function(read('roadmap/tools/test_map_harness.js') + ';return {mapFixture,mapEnvironment,mapNodes,mapText};')();
const mapEnv = mapApi.mapEnvironment(mapApi.mapFixture('station0'), {wide:false});
let nav = mapEnv.render();
assert(nav.type === 'details' && nav.props.open === false, 'Small-screen contents must start collapsed');
assert(find(nav, n => n.props['aria-current'] === 'location'), 'Current chapter remains accessible while its list is collapsed');
const initialLinks = mapApi.mapNodes(nav).filter(n => n.type === 'a' && n.props.href === '#view=final');
assert(initialLinks.length === 1, 'Map has one station-ending destination, not scattered assessment buttons');
mapEnv.props.view = 'final'; nav = mapEnv.render();
const ending = find(nav, n => (n.props.className || '').split(' ').includes('map-finish'));
assert(ending.type === 'a' && ending.props.href === '#view=final', 'Finale keeps its exact native URL');
assert(mapApi.mapText(ending).includes('Завершение станции') && ending.props['aria-current'] === 'page', 'Finale has a clear label and current-page state');
ending.props.onClick();
assert(mapEnv.actions.at(-1)[1] === 'final', 'Finale entry opens the overview, not a quiz');
mapEnv.props.view = 'analysis'; nav = mapEnv.render();
assert(find(nav, n => (n.props.className || '').split(' ').includes('map-finish') && n.props.className.includes('is-current')), 'Analysis stays inside the clearly highlighted station-ending scope');
assert(!mapApi.mapNodes(nav).some(n => n.type === 'a' && /#view=(quiz|interview|analysis)/.test(n.props.href)), 'Assessment choices live in the completion hub instead of competing sidebar buttons');
const selfCheck = components.Theory({ sections: [{id:'check', title:'Проверка', blocks:[{type:'self-check',prompt:'Объясни правило',answer:'<p>Разбор правила</p>'}]}], store:{} });
const reveal = find(selfCheck, n => n.type === 'details');
assert(reveal && !reveal.props.open, 'Self-check answer must be closed initially');
assert(find(reveal, n => n.type === 'summary' && n.children.includes('Сверить с разбором')), 'Self-check must have a native keyboard-accessible reveal');
mapEnv.open(mapEnv.props.active); nav = mapEnv.tree;
assert(find(nav, n => (n.props.className || '').split(' ').includes('map-checkpoint')), 'Expanded chapter exposes its exact checkpoint');
const lastPage = components.Theory({ sections: [section], store: {}, onNavigate: () => {}, onComplete: () => {} });
assert(find(lastPage, n => n.type === 'button' && n.children.includes('Далее: закрепление подглавы →')), 'Last theory page must lead to checkpoint');
data.meta.number = 9;
const sqlPage = components.Theory({ sections: [{id:'sql-null-basics', substation:'queries', title:'NULL', blocks:[]}], store:{} });
const sqlLink = find(sqlPage, n => n.type === 'a' && n.props.href === 'sql_trainer.html#null');
assert(sqlLink && sqlLink.props.target === '_blank', 'SQL lessons must link to matching exercise without replacing reading');
const sqlMap = mapApi.mapEnvironment(mapApi.mapFixture('station9-sql'));
const sqlNav = sqlMap.render();
assert(find(sqlNav, n => n.type === 'a' && n.props.href === 'sql_trainer.html'), 'Database contents must provide persistent trainer access');
mapEnv.dispose(); sqlMap.dispose();
print('PASS: code fallback, keyboard access, source styling, reading position, progress isolation, mobile contents, SQL links');
