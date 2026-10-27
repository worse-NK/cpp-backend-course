// Regression: a trainer link changes the parent hash without reloading React.
const GLib = imports.gi.GLib, BA = imports.byteArray;
const read = p => BA.toString(GLib.file_get_contents(p)[1]);
function assert(ok, message) { if (!ok) throw new Error(message); }
const data = JSON.parse(read('roadmap/content/station9-sql.json'));
const source = read('roadmap/assets/station-app.js');
const states = [], effects = [], listeners = {};
const React = {
  createElement: (type, props, ...children) => ({type, props: props || {}, children: children.flat(Infinity)}),
  useState: initial => {
    const cell = {value: typeof initial === 'function' ? initial() : initial};
    states.push(cell);
    return [cell.value, value => { cell.value = typeof value === 'function' ? value(cell.value) : value; }];
  },
  useEffect: fn => effects.push(fn)
};
const win = {location: {hash: '#section=sql-trainer'}, addEventListener: (name, fn) => {listeners[name] = fn;}, removeEventListener: name => {delete listeners[name];}};
const appSource = source.slice(source.indexOf('  function App()'), source.indexOf('  ReactDOM.createRoot'));
let saved;
const App = new Function('React', 'window', 'localStorage', 'location', 'URLSearchParams', 'persist', `
var h=React.createElement, useState=React.useState, data=${JSON.stringify(data)}, meta=data.meta,
theory=data.theory, tasks=data.tasks, quizzes=data.quizzes, substations=data.substations,
requestedSection=theory.find(s=>s.id==='sql-trainer'), requestedView='theory', requestedModule=null;
function loadStore(){return {'sec:storage':true};} function scrollTop(){}
function isWorkbook(){return false;} function isPracticeTask(){return false;}
function finalQuestions(){return [];} function excludeCheckpointQuestions(q){return q;} function chapterQuestions(){return [];} function SubstationNav(){} function Theory(){}
function Quiz(){} function Tasks(){} function QuizPicker(){}
${source.slice(source.indexOf('  function assessmentPriorityRefs('), source.indexOf('  function finalQuestions('))}
${appSource}; return App;`)(React, win, {getItem: () => null}, {protocol: 'file:'}, class {
  constructor(query){this.query=query;} get(key){const pair=this.query.split('&').find(x=>x.startsWith(key+'='));return pair ? decodeURIComponent(pair.slice(key.length+1)) : null;}
}, value => {saved=value;});
App(); const cleanup=effects[0]();
win.location.hash='#section=sql-null-basics'; listeners.hashchange();
assert(states[2].value==='sql-null-basics', 'Hash must select the requested lesson');
assert(states[3].value==='theory' && states[5].value==='queries', 'Hash must open theory and correct subchapter');
assert(saved['sec:storage']===true, 'Navigation must preserve progress');
win.location.hash='#section=sql-aggregate-basics'; listeners.hashchange();
assert(states[5].value==='aggregation', 'Cross-subchapter navigation');
win.location.hash='#section=missing'; listeners.hashchange();
assert(states[2].value==='sql-aggregate-basics', 'Ignore unknown sections');
cleanup(); assert(!listeners.hashchange, 'Listener cleanup');
print('PASS: embedded SQL trainer returns to theory by hash, switches subchapters and preserves progress');
