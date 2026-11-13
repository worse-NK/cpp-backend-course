// Run: gjs roadmap/tools/test_design_syntax.js
// Real vendored Highlight.js and derived React components in an isolated model.
// No browser, DOM post-processing, learner storage, clipboard, server or network.
const GLib = imports.gi.GLib, BA = imports.byteArray;
const read = path => BA.toString(GLib.file_get_contents(path)[1]);
function assert(ok, message) { if (!ok) throw new Error(message); }
function replaceOnce(source, from, to) {
    assert(source.split(from).length === 2, 'Harness boundary changed: ' + from);
    return source.replace(from, to);
}

// Reuse the actual preview/history/storage model, but not its test executions.
// Export internal components only inside this test evaluation of the renderer.
const previewTests = read('roadmap/tools/test_design_previews.js');
const boundary = previewTests.indexOf("const canonical = loadStation('station0');");
assert(boundary >= 0, 'Preview model boundary changed');
let harness = previewTests.slice(0, boundary);
harness = replaceOnce(harness,
    "'window.testApi = {App,Theory,SubstationNav,LabBlock,previewStorage,loadStore};'",
    "'window.testApi = {App,Theory,SubstationNav,LabBlock,previewStorage,loadStore,CodeBlock,Quiz,Tasks,Training,AssemblyAnswer,designCode,designCodeLanguage};'");
harness = replaceOnce(harness, 'const api = new Function(model +', `
model = replaceOnce(model, '    win.React = React; win.ReactDOM = {};',
    '    win.hljs = options.highlighter; win.React = React; win.ReactDOM = {};');
model = replaceOnce(model, "'URLSearchParams', 'history', 'confirm', exported)(",
    "'URLSearchParams', 'history', 'confirm', 'navigator', exported)(");
model = replaceOnce(model,
    'win, doc, React, {}, storage, win.location, Params, history, () => true);',
    'win, doc, React, {}, storage, win.location, Params, history, () => true, options.navigator || {});');
const api = new Function(model +`);
const model = new Function(harness + ';return {environment,previewData,nodes,text,button,classHas,findClass,assertIsolated};')();
const {environment,previewData,nodes,text,button,classHas,findClass,assertIsolated} = model;

const library = new Function(read('roadmap/vendor/highlightjs/highlight.min.js') + '\n;return hljs;')();
assert(library.versionString === '11.12.0', 'Pinned real Highlight.js version');
assert(library.getLanguage('cpp') && library.getLanguage('bash'), 'Both explicit local grammars exist');

// Strip only the library's own span markup, then decode HTML entities once.
// This deliberately does not use an HTML parser, live DOM or innerHTML setter.
function sourceFromMarkup(markup) {
    const raw = markup.replace(/<\/?span(?: class="[a-zA-Z0-9_ -]+")?>/g, '');
    assert(!raw.includes('<'), 'Source HTML is escaped; no tags other than token spans');
    return raw.replace(/&(?:amp|lt|gt|quot|#x27|#39|#\d+|#x[a-fA-F0-9]+);/g, entity => {
        const named = {'&amp;':'&','&lt;':'<','&gt;':'>','&quot;':'"','&#x27;':"'",'&#39;':"'"};
        if (Object.prototype.hasOwnProperty.call(named, entity)) return named[entity];
        const value = entity.slice(2,-1);
        return String.fromCodePoint(value[0].toLowerCase() === 'x' ? parseInt(value.slice(1),16) : Number(value));
    });
}
function codeNode(tree) {
    const code = nodes(tree).filter(node => node.type === 'code');
    assert(code.length === 1, 'Expected one code element, not a nested duplicate');
    return code[0];
}
function highlighted(node, source, language, description) {
    assert(node.type === 'code' && classHas(node,'hljs') && classHas(node,'language-' + (language || 'cpp')),
        description + ': explicit semantic language classes');
    assert(node.props.translate === 'no', description + ': source identifiers are not translated');
    assert(node.props.dangerouslySetInnerHTML && !node.children.length,
        description + ': one declaratively owned escaped markup payload');
    assert(sourceFromMarkup(node.props.dangerouslySetInnerHTML.__html) === source,
        description + ': all original characters and whitespace retained');
}
function plain(node, source, description) {
    assert(node.type === 'code' && !node.props.dangerouslySetInnerHTML && !classHas(node,'hljs') && text(node) === source,
        description + ': literal text fallback, not hidden or HTML-interpreted source');
}
function makeEnvironment(variant, options) {
    return environment(previewData(variant), '#section=why-oop', Object.assign({variant,highlighter:library},options || {}));
}

const rawCases = [
    '#include <iostream>\nclass Counter {\npublic:\n    explicit Counter(int n) : n_{n} {}\n    int get() const { return n_; }\nprivate:\n    int n_;\n};\n',
    'const char* html = "<img src=x onerror=alert(1)> & </script>";\n// </code><script>not_executed()</script>\n',
    'auto text = R"tag(<strong title="x">Русский текст & α</strong>)tag";\n',
    '/* Незакрытый комментарий: <script> & " \n\tещё одна строка\n',
    'std::vector<std::pair<int, int>> items{{1, 2}};\n\t// табуляция\n\n',
    'const char* escaped = "&lt; &amp; &#39;";\r\nint main() {}\r\n',
    '',
    '\n\n\t  '
];
let rawChecks = 0, blockChecks = 0, consumerChecks = 0;
const env = makeEnvironment('studio'), original = JSON.stringify(env.data);
for (const source of rawCases) {
    const ref = {current:null}, attributes = {ref,className:'custom-source','aria-label':'Test source'};
    const before = Object.assign({},attributes);
    const node = env.api.designCode(source,attributes,true);
    highlighted(node,source,'cpp','Escaped/raw C++ fixture ' + rawChecks);
    assert(node.props.ref === ref && node.props['aria-label'] === attributes['aria-label'] && classHas(node,'custom-source'),
        'Original ref, accessible label and caller class survive highlighting');
    assert(Object.keys(attributes).every(key => attributes[key] === before[key]) && Object.keys(attributes).length === Object.keys(before).length,
        'Caller attributes are not mutated');
    ++rawChecks;
}
const shell = 'c++ -std=c++20 main.cpp -o main\n./main\n';
highlighted(env.api.designCode(shell,null,true,'bash'),shell,'bash','Explicit shell grammar');
plain(env.api.designCode(rawCases[0],null,false),rawCases[0],'Disabled/output highlighting');
plain(env.api.designCode(rawCases[0],null,true,'javascript'),rawCases[0],'Non-allowlisted language');
assert(env.api.designCodeLanguage('Команды для запуска примера') === 'bash' &&
    env.api.designCodeLanguage('Запуск вне учебника') === 'bash' &&
    env.api.designCodeLanguage('Полная программа') === 'cpp', 'Only explicit invocation captions choose Bash');

// Each real station0 CodeBlock is rendered, not just its unchanged opaque props.
// Its current output classification remains authoritative for the test.
for (const section of env.data.theory) {
    for (const block of section.blocks.filter(block => block.type === 'code')) {
        const component = env.mount(env.api.CodeBlock,{block}), tree = component.render();
        const code = codeNode(tree), isOutput = /^(?:Точный вывод|Ожидаемый вывод|Вывод программы)/.test(block.caption || '');
        if (isOutput) plain(code,block.code,'Program output ' + section.id);
        else highlighted(code,block.code,env.api.designCodeLanguage(block.caption),'Actual theory CodeBlock ' + section.id);
        const pre = nodes(tree).find(node => node.type === 'pre');
        assert(pre.props.tabIndex === 0 && pre.props['aria-label'] === (block.caption || 'Фрагмент кода'),
            'Scrollable source preserves its keyboard stop and accessible caption');
        component.dispose(); ++blockChecks;
    }
}
assert(blockChecks > 20, 'The real theory corpus, including its worked program, was covered');

// CodeBlock's copy action receives the authored bytes, never span markup or
// a reconstructed string with lost indentation. This fake clipboard is local.
const copied = [];
const copyEnv = makeEnvironment('studio',{navigator:{clipboard:{writeText(value) {
    copied.push(value); return {then(resolve) { resolve(); }};
}}}});
const copyBlock = {type:'code',caption:'Код для проверки копирования',code:rawCases[1] + '\n\t// конец\n'};
const copyComponent = copyEnv.mount(copyEnv.api.CodeBlock,{block:copyBlock});
let copyTree = copyComponent.render();
button(copyTree,'Копировать').props.onClick(); copyTree = copyComponent.render();
assert(copied.length === 1 && copied[0] === copyBlock.code && findClass(copyTree,'copy-status').props.role === 'status' &&
    text(findClass(copyTree,'copy-status')) === 'Скопировано', 'Copy retains exact raw bytes and announced feedback');
copyComponent.dispose(); assertIsolated(copyEnv); copyEnv.dispose();

// Exercise actual question, task, solution, assembly and training-review
// consumers without touching or replacing their correctness/scoring logic.
const question = {q:'Какой результат?\n\n' + rawCases[0],level:'easy',options:['A','B'],answer:0,why:'Model feedback',
    substation:env.data.substations[0].id,theoryRefs:['why-oop']};
const questionBytes = JSON.stringify(question);
const quiz = env.mount(env.api.Quiz,{kind:'basic',questions:[question],onBack() {},onSave() {}});
highlighted(codeNode(quiz.render()),rawCases[0],'cpp','Actual quiz question'); ++consumerChecks; quiz.dispose();
const task = {title:'Test task',level:'Test level',brief:'Test brief',code:rawCases[1],
    substation:question.substation,theoryRefs:['why-oop'],hints:[],solutionFormat:'code',solution:rawCases[2],notes:'Test notes'};
const taskBytes = JSON.stringify(task);
const taskComponent = env.mount(env.api.Tasks,{tasks:[task]});
let taskTree = taskComponent.render();
highlighted(codeNode(taskTree),task.code,'cpp','Actual task source'); ++consumerChecks;
button(taskTree,'Показать решение').props.onClick(); taskTree = taskComponent.render();
const solution = findClass(taskTree,'solution-code');
highlighted(codeNode(solution),task.solution,'cpp','Actual task solution'); ++consumerChecks;
taskComponent.dispose();

const assemblyQuestion = {type:'assemble',before:'class Counter {\npublic:\n',after:'\n};',
    tokens:['int','get()','const',';'],tokenOrder:[0,1,2,3],answer:[0,1,2,3]};
const assembly = env.mount(env.api.AssemblyAnswer,{question:assemblyQuestion,locked:true,onCheck() {}});
const assemblyTree = assembly.render();
const contexts = nodes(assemblyTree).filter(node => node.type === 'pre' && classHas(node,'assembly-context'));
assert(contexts.length === 2, 'Both assembly contexts remain available');
highlighted(codeNode(contexts[0]),assemblyQuestion.before,'cpp','Assembly before context');
highlighted(codeNode(contexts[1]),assemblyQuestion.after,'cpp','Assembly after context');
const assemblySolution = nodes(assemblyTree).filter(node => node.type === 'pre' && !classHas(node,'assembly-context'));
assert(assemblySolution.length === 1,'Assembly retains one full solution');
highlighted(codeNode(assemblySolution[0]),assemblyQuestion.before + 'int get() const ;' + assemblyQuestion.after,
    'cpp','Assembled full solution');
assert(nodes(assemblyTree).filter(node => node.type === 'button').every(node =>
    nodes(node).filter(child => child.type === 'code').every(child => !child.props.dangerouslySetInnerHTML)),
    'Individual syntax-builder tokens are not painted out of context');
consumerChecks += 3; assembly.dispose();

const trainingEnv = environment(previewData('studio'),'#view=training&set=1',{variant:'studio',highlighter:library});
const training = trainingEnv.mount(trainingEnv.api.Training,{modules:trainingEnv.data.substations,
    bank:{basic:[question],advanced:[]},store:{},onSave() {}});
let trainingTree = training.render();
const trainingQuizNode = nodes(trainingTree).find(node => node.type === trainingEnv.api.Quiz);
assert(trainingQuizNode,'Actual training mounts the same question renderer');
const trainingQuiz = trainingEnv.mount(trainingQuizNode.type,trainingQuizNode.props);
let trainingQuizTree = trainingQuiz.render();
const correct = nodes(trainingQuizTree).find(node => node.type === 'button' && classHas(node,'option') && text(findClass(node,'option-text')) === 'A');
assert(correct,'Actual training keeps shuffled answer semantics');
correct.props.onClick(); trainingQuizTree = trainingQuiz.render();
button(trainingQuizTree,'Показать результат').props.onClick(); trainingQuizTree = trainingQuiz.render();
trainingTree = training.render();
const review = findClass(trainingTree,'training-review');
assert(review && text(review).includes(question.why),'Finished training retains its full answer review');
highlighted(codeNode(review),rawCases[0],'cpp','Actual finished-training review'); ++consumerChecks;
trainingQuiz.dispose(); training.dispose(); assertIsolated(trainingEnv); trainingEnv.dispose();

assert(JSON.stringify(question) === questionBytes && JSON.stringify(task) === taskBytes && JSON.stringify(env.data) === original,
    'Rendering, copy and assessment actions mutate no authored source or question data');
assertIsolated(env); env.dispose();

for (const variant of ['editorial','workbook','focus','ribbon','folio']) {
    const fallback = makeEnvironment(variant);
    plain(fallback.api.designCode(rawCases[1],null,true),rawCases[1],variant + ' keeps its existing plain code');
    const component = fallback.mount(fallback.api.CodeBlock,{block:{type:'code',code:rawCases[0]}});
    plain(codeNode(component.render()),rawCases[0],variant + ' actual CodeBlock stays unchanged');
    component.dispose(); assertIsolated(fallback); fallback.dispose();
}
for (const highlighter of [undefined,{}, {getLanguage:() => null,highlight:() => { throw new Error('Must not run'); }},
    {getLanguage:() => ({}),highlight:() => { throw new Error('Broken highlighter'); }},
    {getLanguage:() => ({}),highlight:() => ({value:null})}]) {
    const fallback = makeEnvironment('studio',{highlighter});
    plain(fallback.api.designCode(rawCases[1],null,true),rawCases[1],'Missing/broken library fallback');
    fallback.dispose();
}

for (const variant of ['editorial','workbook','focus','ribbon','studio','folio']) {
    const html = read('roadmap/design_station0_' + variant + '.html');
    const hasLibrary = html.includes('vendor/highlightjs/highlight.min.js?');
    const hasStyles = html.includes('assets/station-design-syntax.css?');
    assert(hasLibrary === (variant === 'studio') && hasStyles === (variant === 'studio'),
        variant + ': syntax library and token CSS are downloaded only by the dark preview');
    if (variant === 'studio') assert(html.indexOf('vendor/highlightjs/highlight.min.js?') <
        html.indexOf('generated/station-design-preview.app.js?'), 'Local grammar loads before the derived renderer');
}
assert(!read('roadmap/assets/station-app.js').includes('designCode(') &&
    read('roadmap/cpp_station0_oop_basics.html').includes('vendor/highlightjs/'),
    'Production uses its shared syntax helper, not the experimental designCode override');
print('PASS: real local Highlight.js 11.12.0; ' + rawChecks + ' escaping/Unicode/whitespace fixtures, ' + blockChecks +
    ' actual theory CodeBlocks and ' + consumerChecks + ' assessment consumers; raw copy, literal output, non-Studio/missing-library fallbacks and immutable source. No real-browser/layout audit.');
