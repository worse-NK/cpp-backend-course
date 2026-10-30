// Run: gjs roadmap/tools/test_training_ui.js
// Exercises the production components with isolated hook state and fake storage.
// No browser, network, or user's progress is touched by this test.
const GLib = imports.gi.GLib, BA = imports.byteArray;
const read = path => BA.toString(GLib.file_get_contents(path)[1]);
function assert(ok, message) { if (!ok) throw new Error(message); }
const source = read('roadmap/assets/station-app.js');
const data = JSON.parse(read('roadmap/content/station0.json'));
class Params {
    constructor(query) {
        this.pairs = String(query || '').split('&').map(pair => {
            const index = pair.indexOf('=');
            const decode = value => decodeURIComponent(value.replace(/\+/g, ' '));
            return index < 0 ? [decode(pair), ''] : [decode(pair.slice(0,index)), decode(pair.slice(index+1))];
        });
    }
    get(key) { const pair = this.pairs.find(pair => pair[0] === key); return pair ? pair[1] : null; }
}
function findAll(node, predicate) {
    if (!node || typeof node !== 'object') return [];
    return (predicate(node) ? [node] : []).concat((node.children || []).flatMap(child => findAll(child,predicate)));
}
const find = (tree, predicate) => findAll(tree,predicate)[0];
function text(node) {
    if (node === null || node === undefined || node === false) return '';
    if (typeof node !== 'object') return String(node);
    return (node.children || []).map(text).join(' ');
}
function button(tree, label) { return find(tree,node => node.type === 'button' && text(node) === label); }
function environment(hash, initialStore) {
    let active;
    const listeners = {}, writes = [], backing = {[data.meta.storeKey]: JSON.stringify(initialStore || {})};
    const win = {
        STATION_DATA: data,
        location: {hash: hash || '', protocol:'file:'},
        matchMedia: () => ({matches:false}), scrollTo: () => {},
        addEventListener: (name,fn) => { if (!listeners[name]) listeners[name] = new Set(); listeners[name].add(fn); },
        removeEventListener: (name,fn) => { if (listeners[name]) listeners[name].delete(fn); }
    };
    const React = {
        createElement: (type,props,...children) => ({type, props:props || {}, children:children.flat(Infinity)}),
        useState: initial => {
            const owner = active, index = owner.cursor++;
            if (!(index in owner.cells)) owner.cells[index] = typeof initial === 'function' ? initial() : initial;
            return [owner.cells[index], value => {owner.cells[index] = typeof value === 'function' ? value(owner.cells[index]) : value;}];
        },
        useEffect: (effect,deps) => {
            const owner = active, index = owner.cursor++;
            const previous = owner.effects[index];
            if (previous && deps && previous.deps && deps.length === previous.deps.length && deps.every((value,i) => value === previous.deps[i])) return;
            if (previous && previous.cleanup) previous.cleanup();
            owner.effects[index] = {deps, pending:effect};
        }
    };
    win.React = React;
    win.ReactDOM = {};
    const storage = {
        getItem: key => backing[key] || null,
        setItem: (key,value) => {backing[key]=value; writes.push({key,value});}
    };
    const history = {replaceState: (_state,_title,next) => {win.location.hash=next;}};
    const exported = source.replace('  ReactDOM.createRoot(root).render(h(App));',
        '  window.testApi = {App, Training, Quiz, SubstationNav, trainingEntries, trainingSettings, trainingHash, trainingBatches, trainingResultKey};');
    assert(exported !== source, 'Test must load the actual renderer, not a duplicate implementation');
    new Function('window','document','React','ReactDOM','localStorage','location','URLSearchParams','history',exported)(
        win,{getElementById:() => ({})},React,{},storage,win.location,Params,history);
    function mount(component,props) {
        const instance = {cursor:0,cells:[],effects:[],props:props || {}};
        instance.render = () => {
            instance.cursor=0; active=instance;
            let tree;
            try { tree=component(instance.props); } finally { active=null; }
            instance.effects.forEach(record => {if (record.pending) {record.cleanup=record.pending(); delete record.pending;}});
            return tree;
        };
        instance.dispose = () => instance.effects.forEach(record => {if (record.cleanup) record.cleanup();});
        return instance;
    }
    return {api:win.testApi,win,mount,writes,backing,
        emit:name => {if (listeners[name]) Array.from(listeners[name]).forEach(fn => fn());},
        listenerCount:name => listeners[name] ? listeners[name].size : 0};
}

// The public entry lives only in the ending, never beside each theory page.
const original = {'sec:learning-route':true, 'checkpoint:v2:object-interface':{score:2,total:3},
    'station-final:coverage:v1:basic':{score:21,total:25}, 'station-final:v2:interview':{score:8,total:12}};
const env = environment('',original), app = env.mount(env.api.App);
let tree = app.render();
assert(!button(tree,'Дополнительная тренировка →'), 'Theory must not gain another permanent training button');
const nav = () => find(tree,node => node.type === env.api.SubstationNav);
nav().props.onPage('checkpoint'); tree=app.render();
assert(!button(tree,'Дополнительная тренировка →'), 'The short checkpoint must remain uncluttered');
nav().props.onPage('final'); tree=app.render();
const entry=button(tree,'Дополнительная тренировка →');
assert(entry && findAll(tree,node => node.type === 'button' && text(node) === 'Дополнительная тренировка →').length === 1, 'Exactly one optional entry is required in the ending');
assert(find(tree,node => node.props.className === 'training-entry'), 'Training must be visually subordinate to the exam card');
assert(findAll(tree,node => node.props.className === 'finale-item').length === 4, 'Keep the existing four ending destinations');
entry.props.onClick(); tree=app.render();
let trainingNode=find(tree,node => node.type === env.api.Training);
assert(trainingNode && trainingNode.props.bank === data.quizzes, 'The visible training route must receive the full authored bank');
assert(env.win.location.hash === '#view=training', 'Entry must produce a usable direct URL');
assert(button(tree,'← Завершение станции'), 'Training needs a way back to the station ending');
const saveEntries=env.api.trainingEntries(data.quizzes).slice(0,5), savedKey=env.api.trainingResultKey(saveEntries);
const writesBefore=env.writes.length;
trainingNode.props.onSave('station-final:coverage:v1:basic',0,25);
trainingNode.props.onSave(savedKey,6,5);
trainingNode.props.onSave('',0,0);
assert(env.writes.length === writesBefore, 'Invalid or non-training result keys must not overwrite any score');
trainingNode.props.onSave(savedKey,4,5); tree=app.render();
const saved=JSON.parse(env.backing[data.meta.storeKey]);
Object.keys(original).forEach(key => assert(JSON.stringify(saved[key]) === JSON.stringify(original[key]), 'Training overwrote existing progress: '+key));
assert(Object.keys(saved).length === Object.keys(original).length+1 && saved[savedKey].score === 4, 'Training must save under exactly one isolated key');
assert(savedKey.startsWith('station-training:v1:') && !savedKey.startsWith('station-final:'), 'Training results must not become final scores');
assert(env.writes.every(write => write.key === data.meta.storeKey), 'No unrelated localStorage keys may change');
button(tree,'← Завершение станции').props.onClick(); tree=app.render();
assert(button(tree,'Дополнительная тренировка →') && !find(tree,node => node.type === env.api.Training), 'Back must return to the ending, not start an exam');
env.win.location.hash='#view=training&size=5&set=2'; env.emit('hashchange'); tree=app.render();
assert(find(tree,node => node.type === env.api.Training), 'Hash navigation must open training without a reload');
env.win.location.hash='#view=final'; env.emit('popstate'); tree=app.render();
assert(button(tree,'Дополнительная тренировка →'), 'Browser history navigation must leave training normally');
app.dispose();
assert(env.listenerCount('hashchange') === 0 && env.listenerCount('popstate') === 0, 'App navigation listeners must be cleaned up');

// Filtering and sequential sets retain duplicates and do not mutate source data.
const demo = {
    basic:[{q:'same',substation:'a'},{q:'same',substation:'a'},{q:'b',substation:'b'}],
    advanced:[{q:'hard',substation:'a'}],interview:[]
};
const before=JSON.stringify(demo), modules=[{id:'a',label:'0.1',title:'A'},{id:'b',label:'0.2',title:'B'}];
const entries=env.api.trainingEntries(demo);
assert(entries.length === 4 && entries[0].id !== entries[1].id && entries[0].question !== entries[1].question, 'Equal authored texts must remain separate questions');
assert(env.api.trainingEntries(demo,'a','basic').length === 2 && env.api.trainingEntries(demo,'b','advanced').length === 0, 'Module and kind filters must combine exactly');
assert(env.api.trainingEntries({},'', 'all').length === 0, 'An empty bank must be supported');
assert(env.api.trainingBatches([],5).length === 0 && env.api.trainingBatches(entries,0).flat().length === 4, 'Empty/invalid batch sizes must not cause an endless loop');
assert(env.api.trainingResultKey([]) === '', 'An empty attempt must not create a score key');
assert(env.api.trainingResultKey(entries.slice(0,2)) !== env.api.trainingResultKey(entries.slice(1,3)), 'Results for different authored sets must not collide by question text');
const legacyTrainingKey=env.api.trainingResultKey(entries.slice(0,2));
data.trainingVersion='version-a';
const trainingVersionA=env.api.trainingResultKey(entries.slice(0,2));
data.trainingVersion='version-b';
assert(env.api.trainingResultKey(entries.slice(0,2)) !== trainingVersionA && trainingVersionA !== legacyTrainingKey,
    'Changed questions must not reuse a legacy or previous-bank attempt');
assert(env.api.trainingResultKey(entries.slice(0,2)).startsWith('station-training:v1:version-b:'),
    'Versioned attempts must remain in the existing training result namespace');
delete data.trainingVersion;
assert(JSON.stringify(demo) === before, 'Training helpers mutated source questions');
const settings=env.api.trainingSettings(new Params('module=a&kind=advanced&size=5&set=2'),modules);
assert(JSON.stringify(settings) === JSON.stringify({module:'a',kind:'advanced',size:5,batch:1}), 'Direct URL must select the requested scope and set');
assert(env.api.trainingHash(settings) === '#view=training&module=a&kind=advanced&size=5&set=2', 'Training URL round trip');
const invalid=env.api.trainingSettings(new Params('module=missing&kind=unknown&size=0&set=-2'),modules);
assert(JSON.stringify(invalid) === JSON.stringify({module:'',kind:'all',size:10,batch:null}), 'Invalid URL parameters must fall back safely');

const scopeEnv=environment('#view=training'), scopeStore={};
const scope=scopeEnv.mount(scopeEnv.api.Training,{bank:demo,modules,store:scopeStore,onSave:()=>{}});
tree=scope.render();
let selects=findAll(tree,node => node.type === 'select');
assert(selects.length === 3 && findAll(tree,node => node.props.className === 'training-batch').length === 1, 'Picker needs accessible native filters and a real selectable set');
selects[0].props.onChange({target:{value:'b'}}); tree=scope.render();
selects=findAll(tree,node => node.type === 'select');
selects[1].props.onChange({target:{value:'advanced'}}); tree=scope.render();
assert(text(tree).includes('пока нет вопросов') && !find(tree,node => node.type === scopeEnv.api.Quiz), 'An empty filter must explain itself, not crash Quiz');
assert(findAll(tree,node => node.props.className === 'training-batch').length === 0, 'Empty filters must not offer an empty attempt');
scopeEnv.win.location.hash='#view=training&set=999'; scopeEnv.emit('hashchange'); tree=scope.render();
assert(text(tree).includes('Такого набора') && !find(tree,node => node.type === scopeEnv.api.Quiz), 'An obsolete set URL must fall back to the real set picker');
scopeEnv.win.location.hash='#view=training&module=a&kind=basic&size=5'; scopeEnv.emit('popstate'); tree=scope.render();
selects=findAll(tree,node => node.type === 'select');
assert(selects[0].props.value === 'a' && selects[1].props.value === 'basic' && selects[2].props.value === 5, 'Browser history must restore the training scope');
scope.dispose();
assert(scopeEnv.listenerCount('hashchange') === 0 && scopeEnv.listenerCount('popstate') === 0, 'Training navigation listeners must be cleaned up');

// Run a real production Quiz attempt, its explanations, retry and next set.
const attemptEnv=environment('#view=training&size=5&set=1'), attemptStore={}, recorded=[];
const training=attemptEnv.mount(attemptEnv.api.Training,{bank:data.quizzes,modules:data.substations,store:attemptStore,
    onSave:(key,score,total) => {attemptStore[key]={score,total};recorded.push({key,score,total});}});
tree=training.render();
let quizNode=find(tree,node => node.type === attemptEnv.api.Quiz);
assert(quizNode && quizNode.props.questions.length === 5 && quizNode.props.kind === 'training', 'A direct set URL must open a small actual Quiz attempt');
const expected=attemptEnv.api.trainingEntries(data.quizzes).slice(0,5).map(entry => entry.question);
assert(quizNode.props.questions.every((q,index)=>q === expected[index]), 'An attempt must retain authored question order');
const quiz=attemptEnv.mount(attemptEnv.api.Quiz,quizNode.props);
for (let index=0; index<5; index++) {
    let quizTree=quiz.render();
    const correct=expected[index].options[expected[index].answer];
    const answer=find(quizTree,node=>node.type==='button' && node.props.className==='option' && text(node).endsWith(correct));
    assert(answer, 'Every question must expose its correct option after answer shuffling');
    answer.props.onClick(); quizTree=quiz.render();
    assert(find(quizTree,node=>node.props.className==='explanation') && text(quizTree).includes(expected[index].why), 'Answer explanations must remain available in training');
    assert(find(quizTree,node=>node.type==='a' && node.props.target==='_blank' && node.props.href.startsWith('#section=')), 'Training must keep theory links without replacing the attempt');
    button(quizTree,index===4?'Показать результат':'Следующий вопрос →').props.onClick();
}
let resultTree=quiz.render();
assert(recorded.length === 1 && recorded[0].score === 5 && recorded[0].total === 5, 'Completed attempt must save the actual training result');
assert(text(resultTree).includes('ДОПОЛНИТЕЛЬНАЯ ТРЕНИРОВКА'), 'Result must not masquerade as the final exam');
tree=training.render();
assert(button(tree,'Следующий набор →'), 'Completion must offer the next sequential set');
const review=find(tree,node=>node.type==='details' && node.props.className==='training-review');
assert(review && findAll(review,node=>node.props.className==='training-review-item').length === 5, 'Finished training needs an optional review of every question, not just a score');
expected.forEach(question => assert(text(review).includes(question.why), 'Post-attempt review must retain answer explanations'));
assert(findAll(review,node=>node.type==='a').every(node=>node.props.target==='_blank' && node.props.href.startsWith('#section=')), 'Review links must keep the attempt intact');
button(resultTree,'Пройти заново').props.onClick();
assert(text(quiz.render()).includes('1 / 5') && !button(training.render(),'Следующий набор →') && !find(training.render(),node=>node.props.className==='training-review'), 'Retry must restart the same set without advancing or leaving stale completion controls/answers');
quizNode.props.onBack(); tree=training.render();
assert(attemptEnv.win.location.hash === '#view=training&size=5' && !find(tree,node=>node.type===attemptEnv.api.Quiz), 'Back from an attempt must preserve filters and return to set selection');
assert(text(tree).includes('Последняя попытка: 5/5') && find(tree,node=>node.props.className==='training-batch is-attempted'), 'The picker must show the isolated saved training result');
training.dispose(); quiz.dispose();

const directEnv=environment('#view=training&kind=advanced&size=5&set=1'), directApp=directEnv.mount(directEnv.api.App);
assert(find(directApp.render(),node=>node.type===directEnv.api.Training), 'Reloading a training URL must select training at app startup');
directApp.dispose();
print('PASS: optional ending-only entry, full-bank route, sequential/filter/empty sets, real attempt + explanations/theory links, retry, hash/back, listener cleanup, isolated results and preserved progress');
