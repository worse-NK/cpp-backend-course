// Structural component checks: no browser and no real user storage.
const GLib = imports.gi.GLib;
const ByteArray = imports.byteArray;
const page = ByteArray.toString(GLib.file_get_contents('roadmap/cpp_backend_roadmap.html')[1]);
const DATA = JSON.parse(page.match(/<script id="roadmap-data" type="application\/json">([\s\S]*?)<\/script>/)[1]);
const script = [...page.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1];
new Function(script);
const appSource = script.slice(script.indexOf('function App()'), script.indexOf('\nconst S ='));
function assert(value, message) { if (!value) throw new Error(message); }
const React = {createElement: (type, props, ...children) => ({type, props:props || {}, children:children.flat(Infinity)})};
function Stage() {}
function render(saved, progressStore = {}) {
    let call = 0;
    const useState = initial => [call++ === 0 ? saved : typeof initial === 'function' ? initial() : initial, () => {}];
    return new Function('React','DATA','Stage','useState','useEffect','useCallback','loadStore',
        appSource + ';return App();')(React, DATA, Stage, useState, () => {}, fn => fn, () => progressStore);
}
function nodes(tree) {
    if (!tree || typeof tree !== 'object') return [];
    return [tree, ...(tree.children || []).flatMap(nodes)];
}
const tree = nodes(render(null));
function textOf(node) {
    if (node == null || typeof node === 'boolean') return '';
    if (typeof node !== 'object') return String(node);
    return (node.children || []).map(textOf).join(' ');
}
const preview = tree.find(n => n.props.className === 'home-preview-steps');
assert(preview.children.length === 5, 'Preview must show all five course groups');
assert(textOf(tree.find(n => n.props.className === 'home-preview-top')).includes('01 — 05'), 'Preview range must match group count');
preview.children.forEach(item => {
    const label = item.children[0].children[1];
    assert(typeof label.children[0] === 'string' && label.children[0].trim(), 'No empty preview label');
    assert(textOf(label.children[1]).trim(), 'No empty station status');
});
const databasePreview = preview.children.find(n => n.children[0].props.href === '#databases-group');
assert(textOf(databasePreview).includes('SQL и PostgreSQL') && textOf(databasePreview).includes('9A, 9B'), 'Database preview must name both available stations');
assert(databasePreview.props.className !== 'is-planned', 'Available databases must not be marked planned');
assert(preview.children.filter(n => n.props.className === 'is-planned').length === 0, 'Production station is available');
const facts = tree.find(n => n.props.className === 'home-course-facts');
assert(facts.children.length === 3, 'Course facts must contain exactly three metrics');
assert(textOf(facts.children[0]).includes(String(DATA.stages.filter(stage => stage.station).length)), 'Available station count');
assert(textOf(facts.children[0]).includes('готовых станций'), 'Available station label');
const actualSections = DATA.stages.filter(stage => stage.station).reduce((total, stage) => {
    const id = stage.station.file === 'cpp_station9_sql.html' ? 'station9-sql' : stage.station.file === 'cpp_station5_linux_systems.html' ? 'station5-linux' : stage.station.file === 'cpp_station7_linux_networks.html' ? 'station7-netlab' : stage.station.file === 'cpp_station7_traffic_analysis.html' ? 'station7-traffic' : stage.station.file.match(/^cpp_(station\d+)_/)[1];
    const content = JSON.parse(ByteArray.toString(GLib.file_get_contents('roadmap/content/' + id + '.json')[1]));
    assert(stage.station.totalSections === content.theory.length, 'Stale home metadata: ' + id);
    return total + content.theory.length;
}, 0);
assert(textOf(facts.children[1]).includes(String(actualSections)), 'Theory section count must match current sources');
assert(textOf(facts.children[1]).includes('разделов теории'), 'Theory section label');
assert(textOf(facts.children[2]).includes('C++20') && textOf(facts.children[2]).includes('основная версия языка'), 'Language version metric');
assert(!/в плане/i.test(textOf(facts)), 'Course facts must not include a planned-stage metric');
const planned = DATA.stages.find(stage => stage.id === 'production');
const savedStation = planned.station;
planned.station = null;
const updated = nodes(render(null));
const updatedFacts = updated.find(n => n.props.className === 'home-course-facts');
assert(updatedFacts.children.length === 3 && !/в плане/i.test(textOf(updatedFacts)), 'Planned-stage metric must stay hidden when availability changes');
assert(textOf(updatedFacts.children[0]).includes(String(DATA.stages.filter(stage => stage.station).length)), 'Available station count must follow availability');
const plannedPreview = updated.find(n => n.props.className === 'home-preview-steps').children.find(n => n.props.className === 'is-planned');
assert(plannedPreview && textOf(plannedPreview).includes('В плане'), 'Preview status must follow availability');
planned.station = savedStation;
const stages = tree.filter(n => n.type === Stage);
assert(stages.length === DATA.stages.length, 'Every stage must appear once');
assert(new Set(stages.map(n => n.props.stage.id)).size === DATA.stages.length, 'No duplicated stage');
const ids = new Set(tree.map(n => n.props.id).filter(Boolean));
tree.filter(n => n.type === 'a' && n.props.href.startsWith('#')).forEach(n => assert(ids.has(n.props.href.slice(1)), 'Broken page anchor'));
assert(tree.some(n => n.type === 'a' && n.props.href === 'cpp_station0_oop_basics.html'), 'Start link missing');
DATA.bonusFiles.forEach(item => assert(tree.some(n => n.type === 'a' && n.props.href === item.file), 'Missing library material'));
const resumed = nodes(render({file:DATA.stages[0].station.file, section:'struct-to-class', title:'От struct к классу'}));
assert(resumed.some(n => n.type === 'a' && n.props.href === DATA.stages[0].station.file + '#section=struct-to-class'), 'Resume must keep exact section');
print('PASS: '+DATA.stages.length+' unique stages, valid anchors, start/resume links, all library materials');
const optional = DATA.stages.filter(stage => stage.optional);
assert(optional.length === 1 && optional[0].id === 'traffic-analysis', 'Only 7В is optional');
const required = DATA.stages.filter(stage => !stage.optional);
const marks = Object.fromEntries(required.map(stage => [stage.id, true]));
function progressText(store) { return textOf(nodes(render(null, store)).find(n => n.props.className === 'home-route-tools')); }
assert(progressText(marks).includes(required.length + ' / ' + required.length), 'Optional station must not prevent full main-route completion');
marks[optional[0].id] = true;
assert(progressText(marks).includes(required.length + ' / ' + required.length), 'Optional mark must not inflate the main counter');
assert(progressText({[optional[0].id]:true}).includes('0 / ' + required.length), 'Optional station is tracked separately');

// Exercise real stage components, not only the App's list of component props.
const effects = [];
const testReact = Object.assign({}, React, {
    useState: initial => [typeof initial === 'function' ? initial() : initial, () => {}],
    useEffect: effect => effects.push(effect),
    useCallback: fn => fn
});
let reads = 0;
const realComponents = new Function('React', 'ReactDOM', 'document', 'localStorage', 'window',
    script + ';return {Stage,OpenStationBtn};')(
        testReact, {createRoot: () => ({render: () => {}})},
        {getElementById: id => id === 'roadmap-data' ? {textContent:JSON.stringify(DATA)} : {}},
        {getItem: () => { reads++; return null; }},
        {addEventListener: () => {}, removeEventListener: () => {}});
let toggled = false;
const closedStage = nodes(realComponents.Stage({stage:DATA.stages[0], index:0, done:false, expanded:false,
    onToggleDone: () => {toggled = true;}, onToggleExpand: () => {}, isLast:false}));
const mark = closedStage.find(n => n.type === 'button' && n.props['aria-pressed'] === false);
assert(mark && mark.props['aria-label'].includes(DATA.stages[0].title), 'Progress button needs a descriptive accessible name');
mark.props.onClick({currentTarget:{blur: () => {throw new Error('Keyboard focus must not be discarded');}}});
assert(toggled, 'Completion toggle must still work');
effects.forEach(effect => effect());
assert(reads > 0, 'Collapsed stages must load saved progress');
const openLink = realComponents.OpenStationBtn({station:DATA.stages[0].station,accent:'#386789'});
assert(openLink.type === 'a' && openLink.props.href === DATA.stages[0].station.file, 'Open action must be a normal link');
print('PASS: keyboard focus retained, accessible completion state, collapsed progress, native station links');

const progressHelper = script.slice(script.indexOf('function loadStationProgress('), script.indexOf('\nconst Icon'));
const loadProgress = new Function('localStorage', progressHelper + ';return loadStationProgress;')({
    getItem: key => JSON.stringify(key === 'cpp_station7_progress_v1'
        ? {'station-final:editorial-20261029:v1:basic':{score:23,total:25},'station-final:architecture-20261025:v1:basic':{score:2,total:25},'station-final:v3:basic':{score:1,total:25}}
        : {'station-final:editorial-20261029:v1:basic':{score:21,total:25},'station-final:netlab-20261021:v1:basic':{score:2,total:25}})
});
assert(loadProgress('cpp_station7_progress_v1',101).quiz.score === 23, 'Networking home score must match current assessment epoch');
assert(loadProgress('cpp_station7_netlab_progress_v1',25).quiz.score === 21, '7Б home score must use its own assessment key');
const trafficProgress = new Function('localStorage', progressHelper + ';return loadStationProgress;')({
    getItem: () => JSON.stringify({'sec:learning-route':true,'station-final:editorial-20261029:v1:basic':{score:24,total:25},'station-final:traffic-20261026:v1:basic':{score:1,total:25}})
});
assert(trafficProgress('cpp_station7_traffic_progress_v1',25).quiz.score === 24, '7В must not reuse the 7Б exam score');
assert(trafficProgress('cpp_station7_traffic_progress_v1',25).secDone === 1, '7В theory progress must survive score loading');
const stationApp = ByteArray.toString(GLib.file_get_contents('roadmap/assets/station-app.js')[1]);
assert(stationApp.includes('station-final:netlab-20261021:v1:'), 'New station must save the key read by home');
print('PASS: networking and 7Б assessment keys are isolated and match home progress');
const stationKeyHelper = stationApp.slice(stationApp.indexOf('    function quizStoreKey('), stationApp.indexOf('    var quizResults ='));
const stationQuizKey = meta => new Function('meta', stationKeyHelper + ';return quizStoreKey;')(meta)('basic');
for (const [key,id,number,epoch] of [
    ['cpp_station2_progress_v1','station2',2,'v1'],
    ['cpp_station3_progress_v1','station3',3,'v2'],
    ['cpp_station4_progress_v1','station4',4,'v1'],
    ['cpp_station5_progress_v1','station5',5,'v1'],
    ['cpp_station5_linux_progress_v1','station5-linux',5,'v1'],
    ['cpp_station6_progress_v1','station6',6,'v1'],
    ['cpp_station7_progress_v1','station7',7,'v1'],
    ['cpp_station7_netlab_progress_v1','station7-netlab',7,'v1'],
    ['cpp_station7_traffic_progress_v1','station7-traffic',7,'v1'],
    ['cpp_station8_progress_v1','station8',8,'v1'],
    ['cpp_station9_sql_progress_v1','station9-sql',9,'v1'],
    ['cpp_station9_progress_v1','station9',9,'v1'],
    ['cpp_station10_progress_v1','station10',10,'v1']
]) {
    const currentKey = 'station-final:editorial-20261029:' + epoch + ':basic';
    assert(stationQuizKey({id,number}) === currentKey, 'Home and station must agree on the editorial score key: ' + key);
    const oldStore = {'sec:existing-section':true, 'sec:unread-section':false,
        'station-final:coverage:v1:basic':{score:25,total:25},
        'station-final:systems-depth-20261025:v1:basic':{score:25,total:25},
        'station-final:architecture-20261025:v1:basic':{score:25,total:25},
        'station-final:netlab-20261021:v1:basic':{score:25,total:25},
        'station-final:traffic-20261026:v1:basic':{score:25,total:25},
        'station-final:database-split:v1:basic':{score:25,total:25},
        'station-final:v3:basic':{score:25,total:25},
        'station-final:v2:basic':{score:25,total:25},
        'quiz:module:basic':{score:5,total:5}, quiz:{score:25,total:25}};
    const otherEpoch = number === 3 ? 'v1' : 'v2';
    oldStore['station-final:editorial-20261029:'+otherEpoch+':basic'] = {score:25,total:25};
    const before = JSON.stringify(oldStore);
    const loadOld = new Function('localStorage', progressHelper + ';return loadStationProgress;')({getItem: () => JSON.stringify(oldStore)});
    const oldProgress = loadOld(key,40);
    assert(!oldProgress.quiz, 'Old scores must not complete the editorial assessment: ' + key);
    assert(oldProgress.secDone === 1 && oldProgress.totalSections === 40, 'Editorial reset must retain theory progress: ' + key);
    assert(JSON.stringify(oldStore) === before, 'Loading editorial progress must not alter saved records');
    for (const legacy of [{quizAdvanced:{score:19,total:20}}, {'quiz:module:advanced':{score:4,total:5}}]) {
        const legacyStore = Object.assign({}, oldStore, legacy);
        const raw = JSON.stringify(legacyStore);
        const loadLegacy = new Function('localStorage', progressHelper + ';return loadStationProgress;')({getItem: () => raw});
        const legacyProgress = loadLegacy(key,40);
        assert(legacyProgress.quizAdvanced === null, 'Home must not show an old advanced-bank result after editing: ' + key);
        assert(legacyProgress.secDone === 1, 'Ignoring a stale advanced score must retain theory marks: ' + key);
        assert(JSON.stringify(legacyStore) === raw, 'Ignoring a stale advanced score must not delete the saved record');
    }
    const currentStore = Object.assign({},oldStore, {[currentKey]:{score:21,total:25}});
    const loadCurrent = new Function('localStorage', progressHelper + ';return loadStationProgress;')({getItem: () => JSON.stringify(currentStore)});
    assert(loadCurrent(key,40).quiz.score === 21 && loadCurrent(key,40).secDone === 1, 'Home must show the editorial score and retain theory marks: ' + key);
}
const untouchedCpp = new Function('localStorage', progressHelper + ';return loadStationProgress;')({getItem: () => JSON.stringify({'sec:existing-section':true,'station-final:coverage:v1:basic':{score:23,total:25},'station-final:editorial-20261029:v1:basic':{score:1,total:25},'station-final:systems-depth-20261025:v1:basic':{score:2,total:25}})});
for (const key of ['cpp_station0_progress_v1','cpp_station1_progress_v1']) {
    assert(untouchedCpp(key,25).quiz.score === 23 && untouchedCpp(key,25).secDone === 1, 'Unchanged C++ station must retain its existing score epoch: ' + key);
}
print('PASS: editorial score versions agree with home, ignore stale scores and preserve section progress');
print('PASS: architecture and systems exam epochs isolated; prior theory marks retained; unchanged stations unaffected');
