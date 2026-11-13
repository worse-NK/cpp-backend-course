// GJS component checks: no browser, no network and no real learner storage.
const GLib = imports.gi.GLib;
const ByteArray = imports.byteArray;
function read(path) { return ByteArray.toString(GLib.file_get_contents(path)[1]); }
function assert(ok, message) { if (!ok) throw new Error(message); }
function nodes(value) {
    if (!value || typeof value !== 'object') return [];
    return [value, ...(value.children || []).flatMap(nodes)];
}
function text(value) {
    if (value == null || typeof value === 'boolean') return '';
    if (typeof value !== 'object') return String(value);
    return (value.children || []).map(text).join(' ');
}

const source = read('roadmap/assets/station-app.js');
const helper = source.slice(source.indexOf('  function assessmentPriorityRefs('), source.indexOf('  function VisualBlock('));
const sidebar = source.slice(source.indexOf('  function SubstationNav('), source.indexOf('  function Theory('));
const app = source.slice(source.indexOf('  function App()'), source.indexOf('\n  ReactDOM.createRoot(root)'));
const workbook = source.slice(source.indexOf('  function isWorkbook('), source.indexOf('\n  var pageParams'));
const stationNumber = source.slice(source.indexOf('  function stationDisplayNumber('), source.indexOf('  function CodeBlock('));
const labIcon = source.slice(source.indexOf('  function LabFlask('), source.indexOf('  function LabBlock('));
assert(helper && sidebar && app && workbook && stationNumber && labIcon.includes('function LabFlask'), 'Shared component extraction boundaries changed');

const cases = [
    [11, 'cpp_station11_messaging.html', 'messaging-local-lab', 'messaging-final-workbook'],
    [12, 'cpp_station12_redis.html', 'redis-lab-guide', 'cache-race-final-workbook'],
    [13, 'cpp_station13_kubernetes.html', 'lab-route', 'kubernetes-final-workbook'],
    [14, 'cpp_station14_observability.html', 'lab-map', 'observability-final-workbook'],
    [15, 'cpp_station15_security.html', 'security-lab-map', 'security-final-workbook']
];
// An explicit schema catches lost/extra modules as well as changed question
// counts. Two chapters now include the new end-to-end production-path checks.
const checkpointCounts = {
    station11: {'async-contract':5, 'delivery-contract':5, 'kafka-log':5,
        'kafka-producer':5, 'kafka-consumer':5, rabbitmq:5,
        'cpp-integration':5, 'messaging-labs':7},
    station12: {'redis-model':5, 'cache-correctness':5, 'memory-latency':5,
        'atomic-operations':5, 'durability-topology':5,
        'operational-contract':5, 'redis-integration':5},
    station13: {'cluster-model':5, 'workload-contract':5, 'cluster-network':5,
        'health-lifecycle':5, 'stateful-work':5, 'release-capacity':5,
        'cluster-security':5, 'kubernetes-labs':5},
    station14: {'observation-model':5, 'logs-context':5, 'metrics-prometheus':5,
        'tracing-otel':5, 'reliability-signals':5, 'observability-lab':5,
        'incident-workbook':5},
    station15: {'security-model':5, 'resource-abuse':5, 'security-review':5,
        'identity-lifecycle':7, 'authorization-policy':5, 'untrusted-input':5,
        'cpp-security':5, 'network-trust':5, 'secure-delivery':5}
};

for (const [number, file, labSection, workedId] of cases) {
    const id = 'station' + number;
    const data = JSON.parse(read('roadmap/content/' + id + '.json'));
    const plan = JSON.parse(read('roadmap/content/checkpoints/' + id + '.json'));
    const expectedCounts = checkpointCounts[id];
    assert(JSON.stringify(Object.keys(plan.modules).sort()) === JSON.stringify(Object.keys(expectedCounts).sort()),
           id + ': canonical checkpoint modules changed; review the explicit schema');
    assert(JSON.stringify(data.substations.map(module => module.id).sort()) === JSON.stringify(Object.keys(expectedCounts).sort()),
           id + ': checkpoint schema does not cover exactly the current subchapters');
    for (const [module, count] of Object.entries(expectedCounts))
        assert(plan.modules[module].length === count, id + ': authored checkpoint count changed: ' + module);
    data.checkpoints = Object.fromEntries(Object.entries(plan.modules).map(([module, entries]) => [
        module, entries.map(entry => entry.bank ? data.quizzes[entry.bank][entry.index] : entry)
    ]));
    const before = JSON.stringify(data);
    const urls = [];
    const writes = [];
    const React = {
        createElement: (type, props, ...children) => ({type, props: props || {}, children: children.flat(Infinity)}),
        useState: initial => [typeof initial === 'function' ? initial() : initial, value => writes.push(value)],
        useEffect: () => {}
    };
    const window = {matchMedia: () => ({matches: true}), COURSE_LABS: []};
    const history = {replaceState: (_state, _title, url) => urls.push(url)};
    const body = `
        var h=React.createElement, useState=React.useState;
        var meta=data.meta, theory=data.theory, quizzes=data.quizzes,
            tasks=data.tasks, substations=data.substations;
        var requestedSection=null, requestedModule='', requestedSectionId='', requestedView='final';
        var localStorage={getItem:function(){return null;},setItem:function(){}};
        var location={protocol:'https:'};
        function loadStore(){return {};}
        function persist(value){}
        function scrollTop(){}
        ${stationNumber}
        ${labIcon}
        ${workbook}
        ${helper}
        ${sidebar}
        ${app}
        return {App,SubstationNav,PracticeLinks,backendLabEntry,finalQuestions,
                chapterQuestions,isPracticeTask,assessmentCheckpointRefs,
                assessmentPriorityRefs,assessmentFinalBudgets};
    `;
    const api = new Function('React', 'data', 'window', 'history', body)(React, data, window, history);
    const lab = api.backendLabEntry(id);
    assert(lab && lab.file === file && lab.section === labSection, id + ': wrong preparation route');
    const expectedHref = file + '#section=' + labSection;
    const labPage = data.theory.find(s => s.id === labSection);
    const workedPage = data.theory.find(s => s.id === workedId);
    assert(labPage && workedPage, id + ': missing canonical destinations');

    const practiceTree = nodes(api.PracticeLinks());
    assert(practiceTree.some(n => n.type === 'a' && n.props.href === expectedHref), id + ': missing own practice link');
    assert(!practiceTree.some(n => n.type === 'a' && /leetcode\.com/i.test(n.props.href || '')), id + ': backend lab must not be wrapped in LeetCode URL');
    assert(data.tasks.some(api.isPracticeTask), id + ': no real practice task selected');

    let sidebarPage = null, selectedTheory = null;
    const sidebarTree = nodes(api.SubstationNav({
        items: data.substations, active: labPage.substation, selected: labSection,
        view: 'theory', store: {}, analysisCount: data.tasks.filter(t => !api.isPracticeTask(t)).length,
        onChoose: () => {}, onNavigate: value => { selectedTheory=value; },
        onCheckpoint: () => {}, onPage: value => { sidebarPage=value; }
    }));
    assert(sidebarTree.some(n => n.type === 'a' && n.props.href === expectedHref), id + ': missing sidebar preparation link');
    const tocLab = sidebarTree.find(n => n.type === 'a' && text(n).trim() === labPage.title);
    assert(tocLab, id + ': lab theory page absent from its active subchapter TOC');
    assert(tocLab.props.href === '#section=' + labSection, id + ': TOC has its exact native link');
    tocLab.props.onClick();
    assert(selectedTheory === labSection, id + ': TOC lab click opens the wrong section');
    const ending = sidebarTree.find(n => n.type === 'a' && text(n).trim() === 'Завершение станции');
    assert(ending, id + ': no single station-ending entry in sidebar');
    assert(ending.props.href === '#view=final', id + ': ending entry has its exact native link');
    ending.props.onClick();
    assert(sidebarPage === 'final', id + ': ending entry routes elsewhere');

    const tree = nodes(api.App());
    const grid = tree.find(n => n.props.className === 'finale-grid');
    assert(grid && grid.children.filter(n => n && n.props && n.props.className === 'finale-item').length === 4,
           id + ': completion hub must expose four destinations');
    const destinations = [
        ['Открыть итоговый тест →', '#view=quiz'],
        ['Открыть интервью-тренажёр →', '#view=interview'],
        ['Перейти к заданиям →', '#view=tasks']
    ];
    for (const [label, target] of destinations) {
        const button = tree.find(n => n.type === 'button' && text(n).trim() === label);
        assert(button, id + ': missing ending action ' + label);
        button.props.onClick();
        assert(urls[urls.length-1] === target, id + ': action has wrong destination ' + label);
    }
    const workedButton = tree.find(n => n.type === 'button' && n.props.key === workedId);
    assert(workedButton, id + ': worked example absent from ending hub');
    workedButton.props.onClick();
    assert(urls[urls.length-1] === '#section=' + workedId, id + ': worked example click has wrong section');

    const final = api.finalQuestions(data.quizzes, data.substations, 25, false,
        api.assessmentPriorityRefs(id), api.assessmentFinalBudgets(id), data.checkpoints);
    assert(final.length === 25, id + ': final assessment is not 25 questions');
    assert(new Set(final.map(q => q.substation)).size === data.substations.length, id + ': final omits a subchapter');
    const stems = new Set(Object.values(data.checkpoints).flat().map(q => q.q.trim().replace(/\s+/g,' ').toLowerCase()));
    assert(final.every(q => !stems.has(q.q.trim().replace(/\s+/g,' ').toLowerCase())), id + ': checkpoint leaked into final');
    for (const module of data.substations) {
        const check = api.chapterQuestions(data.quizzes, module.id, api.assessmentCheckpointRefs(id), data.checkpoints);
        assert(check.length === expectedCounts[module.id], id + ': chapter resolves to the wrong explicit count: ' + module.id);
        assert(JSON.stringify(check) === JSON.stringify(data.checkpoints[module.id]),
               id + ': chapter selection lost, reordered or replaced an authored checkpoint');
    }
    assert(JSON.stringify(data) === before, id + ': rendering or selection mutated canonical data');
}
print('PASS: backend extension UI — five hubs, own lab routes, sidebar TOCs, 25-question finals covering every subchapter, exact authored 5/7-question checkpoint schemas');
