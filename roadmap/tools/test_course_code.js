// Run: gjs roadmap/tools/test_course_code.js
// The actual local highlighter, shared helper and production React components.
// Isolated hooks/storage; no browser, HTML execution, real clipboard or network.
const GLib = imports.gi.GLib, BA = imports.byteArray;
const read = path => BA.toString(GLib.file_get_contents(path)[1]);
function assert(ok, message) { if (!ok) throw new Error(message); }
function replaceOnce(source, from, to) {
    assert(source.split(from).length === 2, 'Harness boundary changed: ' + from);
    return source.replace(from, to);
}
const library = new Function(read('roadmap/vendor/highlightjs/highlight.min.js') + '\n;return hljs;')();
assert(library.versionString === '11.12.0', 'Real locally pinned Highlight.js version');
const origin = JSON.parse(read('roadmap/vendor/highlightjs/ORIGIN.json'));
for (const name of Object.keys(origin.files)) {
    if (/\.js$/.test(name) && name !== 'highlight.min.js')
        new Function('hljs', read('roadmap/vendor/highlightjs/' + name))(library);
}
const helper = read('roadmap/tools/test_station_reading_ui.js');
const boundary = helper.indexOf('let sectionLists = 0');
assert(boundary >= 0, 'Production reading helper boundary changed');
let model = helper.slice(0, boundary);
model = replaceOnce(model, '    win.React = React; win.ReactDOM = {};',
    '    win.hljs = options.highlighter; win.React = React; win.ReactDOM = {};\n' +
    '    new Function("window", read("roadmap/assets/course-code.js"))(win);');
model = replaceOnce(model, 'window.testApi = {App,Theory,SubstationNav,LabBlock};',
    'window.testApi = {App,Theory,SubstationNav,LabBlock,CodeBlock,Quiz,Tasks,AssemblyAnswer,codeElement,codeLanguage};');
model = replaceOnce(model, "'URLSearchParams', 'history', exported)(",
    "'URLSearchParams', 'history', 'navigator', exported)(");
model = replaceOnce(model, 'win, doc, React, {}, storage, win.location, Params, history);',
    'win, doc, React, {}, storage, win.location, Params, history, options.navigator || {});');
const api = new Function(model + ';return {environment,loadStation,nodes,text,button};')();
const {environment,loadStation,nodes,text,button} = api;
const hasClass = (node, name) => String(node.props.className || '').split(/\s+/).includes(name);
function sourceFromMarkup(markup) {
    const raw = markup.replace(/<\/?span(?: class="[a-zA-Z0-9_ -]+")?>/g, '');
    assert(!raw.includes('<'), 'Only token spans may be emitted; authored HTML stays escaped');
    return raw.replace(/&(?:amp|lt|gt|quot|#x27|#39|#\d+|#x[a-fA-F0-9]+);/g, entity => {
        const named = {'&amp;':'&','&lt;':'<','&gt;':'>','&quot;':'"','&#x27;':"'",'&#39;':"'"};
        if (Object.prototype.hasOwnProperty.call(named, entity)) return named[entity];
        const value = entity.slice(2,-1);
        return String.fromCodePoint(value[0].toLowerCase() === 'x' ? parseInt(value.slice(1),16) : Number(value));
    });
}
function source(node) {
    return node.props.dangerouslySetInnerHTML ? sourceFromMarkup(node.props.dangerouslySetInnerHTML.__html) : text(node);
}
function codeNode(tree) {
    const codes = nodes(tree).filter(node => node.type === 'code');
    assert(codes.length === 1, 'One semantic code element, without duplicate nested source');
    return codes[0];
}
function plain(node, raw, description) {
    assert(node.type === 'code' && !node.props.dangerouslySetInnerHTML && !hasClass(node,'hljs') && text(node) === raw,
        description + ': plain literal source');
}
function highlighted(node, raw, language, description) {
    assert(node.type === 'code' && hasClass(node,'hljs') && hasClass(node,'language-' + language),
        description + ': explicit language and highlighter classes');
    assert(node.props.translate === 'no' && !!node.props.dangerouslySetInnerHTML && !node.children.length,
        description + ': one escaped declarative token payload with translation disabled');
    assert(source(node) === raw, description + ': every authored character and whitespace is retained');
}
const fixtures = [
    '#include <iostream>\nclass Counter {\npublic:\n    explicit Counter(int n) : n_{n} {}\n    int get() const { return n_; }\nprivate:\n    int n_;\n};\n',
    'const char* html = "<img src=x onerror=alert(1)> & </script>";\n// </code><script>never()</script>\n',
    'auto text = R"tag(<strong title="x">Русский текст & α</strong>)tag";\n',
    '/* Незакрытый комментарий <script> & " \n\tещё одна строка\n',
    'std::vector<std::pair<int, int>> values{{1, 2}};\n\t// tab\n\n',
    'const char* escaped = "&lt; &amp; &#39;";\r\nint main() {}\r\n',
    '', '\n\n\t  '
];
let escaping = 0, blocks = 0, outputs = 0, readers = 0, consumers = 0;
const e = environment(loadStation('station0'), '#section=why-oop', {highlighter:library});
assert(e.win.CourseCode && typeof e.win.CourseCode.element === 'function' && typeof e.win.CourseCode.languageFor === 'function',
    'Production helper exports its explicit element and language-classification APIs');
for (const raw of fixtures) {
    const ref = {current:null}, attrs = {ref,className:'custom-source','aria-label':'Source fixture'};
    const before = {...attrs};
    highlighted(e.api.codeElement(raw,attrs,'cpp'),raw,'cpp','C++ escaping fixture ' + escaping);
    assert(Object.keys(attrs).length === Object.keys(before).length && Object.keys(attrs).every(key => attrs[key] === before[key]),
        'Highlighting does not mutate caller attributes');
    const node = e.api.codeElement(raw,attrs,'cpp');
    assert(node.props.ref === ref && node.props['aria-label'] === attrs['aria-label'] && hasClass(node,'custom-source'),
        'Caller refs, labels and classes survive highlighting');
    ++escaping;
}
for (const [language,raw] of [
    ['bash','c++ -std=c++20 main.cpp -o main\n./main\n'],
    ['sql','SELECT id, title FROM tasks WHERE owner_id = $1;\n'],
    ['json','{"name":"counter", "enabled":true}\n'],
    ['yaml','apiVersion: v1\nkind: Service\nmetadata:\n  name: example\n'],
    ['http','GET /tasks HTTP/1.1\nHost: example.test\n\n'],
    ['cmake','cmake_minimum_required(VERSION 3.20)\nproject(example LANGUAGES CXX)\n'],
    ['dockerfile','FROM alpine:3\nWORKDIR /app\nCMD ["/app/service"]\n'],
    ['nginx','events {}\nhttp { server { listen 8080; } }\n']
]) highlighted(e.api.codeElement(raw,null,language),raw,language,'Explicit ' + language + ' grammar');
plain(e.api.codeElement(fixtures[1],null,'plaintext'),fixtures[1],'Program output');
plain(e.api.codeElement(fixtures[1],null,'not-a-language'),fixtures[1],'Unknown grammar');
assert(e.api.codeLanguage(fixtures[0], 'Полная программа') === 'cpp', 'Full C++ example is classified as C++');
assert(e.api.codeLanguage('#include <string>\nstd::string query = R"SQL(\nSELECT id FROM tasks;\n)SQL";\n',
    'Полная программа') === 'cpp', 'A SQL string inside a C++ program does not replace the surrounding language');
assert(e.api.codeLanguage('def load_tasks(db):\n    query = """\nSELECT id FROM tasks;\n"""\n    return db.execute(query)\n',
    'Программа') === 'python', 'An embedded SQL string does not replace the surrounding Python language');
assert(e.api.codeLanguage('apiVersion: v1\nkind: ConfigMap\ndata:\n  query: |\n    SELECT id FROM tasks;\n',
    'Конфигурация') === 'yaml', 'A multiline query remains part of the surrounding YAML configuration');
assert(e.api.codeLanguage('SELECT id FROM tasks;', 'SQL-запрос') === 'sql', 'SQL is not coloured as C++');
assert(e.api.codeLanguage('cmake -S . -B build\ncmake --build build', 'Команды для запуска') === 'bash',
    'Build/run commands use explicit shell syntax, not C++');
e.dispose();

// Edition metadata is visible, but is not inserted into source/copy output.
const editions = environment(loadStation('station0'), '', {highlighter:library});
for (const [standard,label] of [['20','C++20'],['23','C++23'],['20/23','C++20 / C++23']]) {
    const raw = 'int main() {}\n';
    const owner = editions.mount(editions.api.CodeBlock,{block:{type:'code',code:raw,caption:'Полная программа',exampleId:'edition-fixture',standard}});
    const tree = owner.render(), badges = nodes(tree).filter(n => hasClass(n,'code-standard'));
    assert(badges.length === 1 && text(badges[0]) === label, 'Visible edition badge: ' + standard);
    assert(badges[0].props.title.includes('не отметка') || badges[0].props.title.includes('проверяется отдельно'), 'Edition badge does not pretend to certify the current compiler');
    assert(tree.props['data-example-id'] === 'edition-fixture' && source(codeNode(tree)) === raw, 'Stable ID and exact authored source survive edition rendering');
    owner.dispose();
}
editions.dispose();

const directory = GLib.Dir.open('roadmap/content', 0);
for (let name; (name = directory.read_name()) !== null;) {
    if (!/^station\d+(?:-[a-z]+)?\.json$/.test(name)) continue;
    const data = loadStation(name.replace(/\.json$/,'')), original = JSON.stringify(data);
    const env = environment(data, '', {highlighter:library});
    for (const section of data.theory) for (const block of section.blocks.filter(block => block.type === 'code')) {
        const owner = env.mount(env.api.CodeBlock,{block}), tree = owner.render(), code = codeNode(tree);
        assert(source(code) === block.code, data.meta.id + '/' + section.id + ': authored bytes preserved');
        const pre = nodes(tree).find(node => node.type === 'pre');
        assert(pre && pre.props.tabIndex === 0 && pre.props['aria-label'] === (block.caption || 'Фрагмент кода'),
            'Scrollable code keeps its keyboard stop and accessible caption');
        if (/^(?:Точный вывод|Ожидаемый вывод|Вывод программы)/.test(block.caption || '')) {
            plain(code,block.code,data.meta.id + '/' + section.id + ' program output'); ++outputs;
        }
        owner.dispose(); ++blocks;
    }
    assert(JSON.stringify(data) === original, data.meta.id + ': no lesson/question mutation');
    env.preserved(); env.dispose(); ++readers;
}
assert(readers === 21 && blocks > 100 && outputs > 0, 'Entire current theory CodeBlock corpus, including literal outputs, covered');

const copied = [], data = loadStation('station0');
const copyEnv = environment(data, '', {highlighter:library,navigator:{clipboard:{writeText(raw) {
    copied.push(raw); return {then(resolve) { resolve(); }};
}}}});
const raw = fixtures[1] + '\n\t// exact final bytes\n';
const owner = copyEnv.mount(copyEnv.api.CodeBlock,{block:{type:'code',caption:'C++ example',code:raw}});
let tree = owner.render(); button(tree,'Копировать').props.onClick(); tree = owner.render();
assert(copied.length === 1 && copied[0] === raw, 'Copy uses authored bytes, never token markup or reconstructed text');
const status = nodes(tree).find(node => hasClass(node,'copy-status'));
assert(status && status.props.role === 'status' && text(status) === 'Скопировано', 'Copy success has live semantic feedback');
owner.dispose(); copyEnv.preserved(); copyEnv.dispose();

// The same helper is used by actual assessment components, rather than only
// the theory renderer. Neither token markup nor theme may alter their data.
const assessment = environment(loadStation('station0'), '', {highlighter:library});
const question = {q:'Что произойдёт?\n\n' + fixtures[0],level:'easy',options:['Первый вариант','Второй вариант'],
    answer:0,why:'Объяснение результата',substation:assessment.data.substations[0].id,theoryRefs:['why-oop']};
const questionBefore = JSON.stringify(question);
const quiz = assessment.mount(assessment.api.Quiz,{kind:'basic',questions:[question],onBack() {},onSave() {}});
highlighted(codeNode(quiz.render()),fixtures[0],'cpp','Actual production quiz source');
quiz.dispose(); ++consumers;
const task = {title:'Проверочный пример',level:'Средняя',brief:'Условие',code:fixtures[1],
    substation:question.substation,theoryRefs:['why-oop'],hints:[],solutionFormat:'code',solution:fixtures[2],notes:'Пояснение'};
const taskBefore = JSON.stringify(task), taskOwner = assessment.mount(assessment.api.Tasks,{tasks:[task]});
let taskTree = taskOwner.render(); highlighted(codeNode(taskTree),task.code,'cpp','Actual production task source'); ++consumers;
button(taskTree,'Показать решение').props.onClick(); taskTree = taskOwner.render();
const solution = nodes(taskTree).find(node => hasClass(node,'solution-code'));
highlighted(codeNode(solution),task.solution,'cpp','Actual production task solution'); ++consumers;
taskOwner.dispose();
const assemblyQuestion = {before:'class Counter {\npublic:\n',after:'\n};',tokens:['int','value',';'],
    tokenOrder:[0,1,2],answer:[0,1,2]};
const assembly = assessment.mount(assessment.api.AssemblyAnswer,{question:assemblyQuestion,locked:true,onCheck() {}});
const assemblyTree = assembly.render(), contexts = nodes(assemblyTree).filter(node => hasClass(node,'assembly-context'));
assert(contexts.length === 2, 'Both immutable syntax-assembly contexts remain visible');
highlighted(codeNode(contexts[0]),assemblyQuestion.before,'cpp','Actual assembly prefix');
highlighted(codeNode(contexts[1]),assemblyQuestion.after,'cpp','Actual assembly suffix');
const assembledSolution = nodes(assemblyTree).find(node => hasClass(node,'assembly-solution'));
highlighted(codeNode(assembledSolution),assemblyQuestion.before + 'int value ;' + assemblyQuestion.after,'cpp','Actual assembled solution');
assembly.dispose(); consumers += 3;
assert(JSON.stringify(question) === questionBefore && JSON.stringify(task) === taskBefore,
    'Assessment rendering never mutates source, answer options or explanations');
assessment.preserved(); assessment.dispose();

for (const highlighter of [undefined,{}, {getLanguage:() => null,highlight:() => { throw new Error('Must not execute'); }},
    {getLanguage:() => ({}),highlight:() => { throw new Error('Broken highlighter'); }},
    {getLanguage:() => ({}),highlight:() => ({value:null})}]) {
    const fallback = environment(loadStation('station0'), '', {highlighter});
    plain(fallback.api.codeElement(fixtures[1],null,'cpp'),fixtures[1],'Missing/broken highlighter');
    fallback.dispose();
}
assert(!/highlightAuto\s*\(/.test(read('roadmap/assets/course-code.js')), 'No language guessing through highlightAuto');
print('PASS: production syntax helper; ' + escaping + ' escaping fixtures, ' + blocks + ' actual theory CodeBlocks across ' +
    readers + ' stations, ' + outputs + ' literal output blocks and ' + consumers + ' assessment consumers; explicit grammar, exact copy and safe missing-library fallbacks. DOM/React model only.');
