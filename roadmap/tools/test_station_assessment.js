const nodeRuntime = typeof require === 'function';
const nodeFs = nodeRuntime ? require('node:fs') : null;
const GLib = nodeRuntime ? {
    file_get_contents: path => [true, nodeFs.readFileSync(path)],
    Dir: {open: path => { const names = nodeFs.readdirSync(path); let index = 0; return {read_name: () => names[index++] || null}; }},
    ChecksumType: {SHA256: 'sha256'},
    compute_checksum_for_string: (_type, text) => require('node:crypto').createHash('sha256').update(text).digest('hex')
} : imports.gi.GLib;
const ByteArray = nodeRuntime ? {toString: value => value.toString('utf8')} : imports.byteArray;
function report(text) { if (nodeRuntime) console.log(text); else print(text); }
function read(path) { return ByteArray.toString(GLib.file_get_contents(path)[1]); }
function assert(condition, message) { if (!condition) throw new Error(message); }
const source = read('roadmap/assets/station-app.js');
new Function(source);
const helper = source.slice(source.indexOf('  function assessmentPriorityRefs('), source.indexOf('  function VisualBlock('));
const select = new Function(helper + ';return finalQuestions;')();
const practice = new Function(helper + ';return isPracticeTask;')();
const chapter = new Function(helper + ';return chapterQuestions;')();
const priorityRefs = new Function(helper + ';return assessmentPriorityRefs;')();
const finalBudgets = new Function(helper + ';return assessmentFinalBudgets;')();
const checkpointRefs = new Function(helper + ';return assessmentCheckpointRefs;')();
const optionalRefs = new Function(helper + ';return assessmentOptionalRefs;')();
const training = new Function(helper + ';return trainingEntries;')();
const batches = new Function(helper + ';return trainingBatches;')();
// A reserved chapter question must not leave a hole in a completed final.
const refillBank = {basic:Array.from({length:30}, (_,i)=>({q:'Question '+i,substation:'one',theoryRefs:['topic-'+i]})),advanced:[]};
const refillBefore = JSON.stringify(refillBank);
const reservedChecks = {one:refillBank.basic.slice(0,5).map(q=>Object.assign({},q,{q:'  '+q.q.toUpperCase()+'  '}))};
const refilled = select(refillBank,[{id:'one'}],25,true,[],null,reservedChecks);
assert(refilled.length === 25, 'Reserve checkpoints before selection so the final keeps 25 questions');
assert(refilled.every(q=>!refillBank.basic.slice(0,5).includes(q)), 'Normalized checkpoint copies must not enter the final');
assert(JSON.stringify(refillBank) === refillBefore, 'Reserving checkpoints must not mutate source banks');
const appSelection = source.slice(source.indexOf('    var priorityRefs = assessmentPriorityRefs(meta.id);'), source.indexOf('    var workedSections ='));
function appAssessment(data, moduleId) {
    return new Function('data', 'meta', 'quizzes', 'substations', 'activeSubstationId', helper + appSelection + ';return {quizzes:activeQuizzes,checkpoint:checkpointQuestions};')(
        data, data.meta, data.quizzes, data.substations, moduleId);
}
const keyHelper = source.slice(source.indexOf('    function quizStoreKey('), source.indexOf('    var quizResults ='));
function quizKey(meta, kind) { return new Function('meta', keyHelper + ';return quizStoreKey;')(meta)(kind); }
const resultHelper = source.slice(source.indexOf('    var quizResults ='), source.indexOf('    function updateStore('));
function savedResults(meta, store) { return new Function('meta', 'store', keyHelper + resultHelper + ';return quizResults;')(meta, store); }
const storeUpdateHelper = source.slice(source.indexOf('    function updateStore('), source.indexOf('    function openPage('));
const foundationsIds = ['station1', 'station3', 'station5'];
const deepeningIds = ['station5','station7','station7-netlab','station7-traffic','station9-sql','station9','station11','station15','station16'];
function reviewEpoch(id, kind, fallback) {
    if ((deepeningIds.includes(id) && (kind === 'basic' || kind === 'interview')) || (id === 'station5-linux' && kind === 'interview')) return 'deepening-20261105:v1';
    if (foundationsIds.includes(id) && (kind === 'basic' || kind === 'interview')) return 'foundations-20261105:v1';
    return fallback;
}
const editorialCases = [
    [{id:'station1',number:1}, 'basic', 'v1', ['station-final:coverage:v1:basic', 'station-final:v3:basic']],
    [{id:'station1',number:1}, 'interview', 'v1', ['station-final:interview-gaps:v1:interview', 'station-final:v2:interview']],
    [{id:'station2',number:2}, 'basic', 'v1', ['station-final:coverage:v1:basic', 'station-final:editorial-20261029:v2:basic']],
    [{id:'station2',number:2}, 'interview', 'v1', ['station-final:v2:interview', 'station-final:editorial-20261029:v2:interview']],
    [{id:'station3',number:3}, 'basic', 'v2', ['station-final:editorial-20261029:v1:basic', 'station-final:systems-depth-20261025:v1:basic', 'station-final:coverage:v1:basic', 'station-final:v3:basic']],
    [{id:'station3',number:3}, 'interview', 'v2', ['station-final:editorial-20261029:v1:interview', 'station-final:systems-depth-20261025:v1:interview', 'station-final:audit-20261015:v1:interview', 'station-final:v2:interview']],
    [{id:'station4',number:4}, 'basic', 'v1', ['station-final:coverage:v1:basic', 'station-final:v3:basic', 'station-final:editorial-20261029:v2:basic']],
    [{id:'station4',number:4}, 'interview', 'v1', ['station-final:v2:interview', 'station-final:editorial-20261029:v2:interview']],
    ...['station5','station5-linux','station6'].flatMap(id => ['basic','interview'].map(kind => [
        {id,number:parseInt(id.slice(7),10)}, kind, 'v1', ['station-final:systems-depth-20261025:v1:'+kind, 'station-final:editorial-20261029:v2:'+kind]
    ])),
    ...[['station7','architecture-20261025'], ['station7-netlab','netlab-20261021'], ['station7-traffic','traffic-20261026'], ['station8','architecture-20261025'], ['station9-sql','systems-depth-20261025'], ['station9','architecture-20261025'], ['station10','architecture-20261025']].flatMap(([id,oldEpoch]) => ['basic','interview'].map(kind => [
        {id,number:parseInt(id.slice(7),10)}, kind, 'v1', ['station-final:'+oldEpoch+':v1:'+kind, 'station-final:editorial-20261029:v2:'+kind]
    ])),
    ...['station11','station15','station16'].flatMap(id => ['basic','interview'].map(kind => [
        {id,number:Number(id.slice(7))}, kind, 'v1', ['station-final:v3:'+kind, 'station-final:v2:'+kind]
    ]))
];
editorialCases.forEach(([meta,kind,epoch,oldKeys]) => {
    const foundations = foundationsIds.includes(meta.id);
    const currentKey = 'station-final:' + reviewEpoch(meta.id,kind,'editorial-20261029:' + epoch) + ':' + kind;
    if (foundations) oldKeys = oldKeys.concat(['v1', 'v2'].map(version => 'station-final:editorial-20261029:' + version + ':' + kind));
    if (currentKey.includes(':deepening-')) oldKeys = oldKeys.concat(['station-final:editorial-20261029:v1:'+kind, 'station-final:foundations-20261105:v1:'+kind]);
    assert(quizKey(meta,kind) === currentKey, 'Wrong editorial score epoch: ' + meta.id + '/' + kind);
    const advancedKey = quizKey(meta, 'advanced');
    const advancedResult = {score:11,total:17};
    const store = {'sec:existing-section':true, 'sec:unread-section':false, [advancedKey]:advancedResult};
    oldKeys.forEach(key => { store[key] = {score:25,total:25}; });
    const before = JSON.stringify(store);
    assert(!savedResults(meta,store)[kind], 'Old score must not complete the revised assessment: ' + meta.id + '/' + kind);
    assert(savedResults(meta,store).advanced === advancedResult, 'Changing basic/interview must retain the advanced result: ' + meta.id);
    assert(JSON.stringify(store) === before && store['sec:existing-section'], 'Reading revised scores must preserve theory progress and old records');
    let nextState, persisted;
    const score = {score:20,total:25};
    const update = new Function('store', 'setStore', 'persist', 'loadStore', storeUpdateHelper + ';return updateStore;')(
        store, value => { nextState = value; }, value => { persisted = value; }, () => store);
    update({[currentKey]:score});
    assert(nextState === persisted && nextState[currentKey] === score, 'Saving must persist the new score epoch: ' + meta.id + '/' + kind);
    assert(nextState['sec:existing-section'] && nextState['sec:unread-section'] === false && oldKeys.every(key => nextState[key] === store[key]), 'Saving the new score must retain section marks and old records');
    assert(JSON.stringify(store) === before, 'Saving must not mutate the previous progress state');
    assert(savedResults(meta,nextState)[kind] === score, 'Current editorial score must be loaded: ' + meta.id + '/' + kind);
    assert(savedResults(meta,nextState).advanced === advancedResult, 'Saving a revised result must retain advanced progress: ' + meta.id);
});
// Simulate sequential actions in two windows whose React closures are stale.
let sharedProgress = {'sec:already-read':true};
const originalProgress = sharedProgress;
function staleWindowUpdate(stale) {
    return new Function('store', 'setStore', 'persist', 'loadStore', storeUpdateHelper + ';return updateStore;')(
        stale, () => {}, value => {sharedProgress=value;}, () => sharedProgress);
}
const quizWindow = staleWindowUpdate(originalProgress), theoryWindow = staleWindowUpdate(originalProgress);
theoryWindow({'sec:other-window':true});
quizWindow({'station-final:coverage:v1:basic':{score:21,total:25}});
assert(sharedProgress['sec:already-read'] && sharedProgress['sec:other-window'], 'Saving a result must retain another window mark');
theoryWindow({'sec:third':true});
assert(sharedProgress['station-final:coverage:v1:basic'].score===21, 'Stale theory state must retain a saved quiz score');
assert(!originalProgress['sec:other-window'], 'Shared-store merge must not mutate the original React object');
sharedProgress={}; // explicit reset in another window
quizWindow({'station-final:coverage:v1:basic':{score:9,total:25}});
assert(!sharedProgress['sec:already-read'] && !sharedProgress['sec:other-window'] && !sharedProgress['sec:third'], 'A stale window must not resurrect marks after reset');
const storageEffectStart=source.indexOf('    // Keep progress shared by other course windows');
const storageEffectEnd=source.indexOf('    var hasSubstations', storageEffectStart);
const storageEffect=source.slice(storageEffectStart, storageEffectEnd);
let listener, cleanupListener, received;
const storageToken={};
new Function('React','window','localStorage','meta','setStore','loadStore',storageEffect)(
    {useEffect: fn => {cleanupListener=fn();}},
    {addEventListener:(name,fn)=>{assert(name==='storage','Only storage handler expected');listener=fn;},removeEventListener:(name,fn)=>{assert(name==='storage'&&fn===listener,'Clean up exact listener');}},
    storageToken,{storeKey:'station-key'},value=>{received=value;},()=>sharedProgress);
listener({key:'unrelated',storageArea:storageToken}); assert(received===undefined,'Ignore another namespace');
listener({key:'station-key',storageArea:{}}); assert(received===undefined,'Ignore session/other storage');
listener({key:'station-key',storageArea:storageToken}); assert(received===sharedProgress,'Synchronize latest progress');
sharedProgress={}; listener({key:null,storageArea:storageToken}); assert(received===sharedProgress,'Explicit clear synchronizes reset');
cleanupListener();
const unchangedScoreCases = [
    [{id:'station5-linux',number:5}, 'basic', 'station-final:editorial-20261029:v1:basic'],
    [{id:'station2',number:2}, 'advanced', 'station-final:v2:advanced'],
    [{id:'station3',number:3}, 'advanced', 'station-final:systems-depth-20261025:v1:advanced'],
    [{id:'station4',number:4}, 'advanced', 'station-final:v2:advanced'],
    ...[0].flatMap(number => [
        [{id:'station'+number,number}, 'basic', 'station-final:coverage:v1:basic'],
        [{id:'station'+number,number}, 'advanced', 'station-final:v2:advanced'],
        [{id:'station'+number,number}, 'interview', number === 1 ? 'station-final:interview-gaps:v1:interview' : 'station-final:v2:interview']
    ]),
    [{id:'station1',number:1}, 'advanced', 'station-final:v2:advanced'],
    ...['station5','station5-linux','station6'].map(id => [
        {id,number:parseInt(id.slice(7),10)}, 'advanced', 'station-final:systems-depth-20261025:v1:advanced'
    ]),
    ...['station9-sql'].flatMap(id => ['advanced'].map(kind => [
        {id,number:parseInt(id.slice(7),10)}, kind, 'station-final:systems-depth-20261025:v1:'+kind
    ])),
    ...[7,10].flatMap(number => ['advanced'].map(kind => [
        {id:'station'+number,number}, kind, 'station-final:architecture-20261025:v1:'+kind
    ])),
    [{id:'station8',number:8}, 'advanced', 'station-final:architecture-20261025:v1:advanced'],
    [{id:'station9',number:9}, 'advanced', 'station-final:architecture-20261025:v1:advanced'],
    ...['station11','station15','station16'].map(id => [{id,number:Number(id.slice(7))}, 'advanced', 'station-final:v2:advanced']),
    ...[['station7-netlab','netlab-20261021'],['station7-traffic','traffic-20261026']].flatMap(([id,epoch]) => ['advanced'].map(kind => [
        {id,number:7}, kind, 'station-final:'+epoch+':v1:'+kind
    ]))
];
unchangedScoreCases.forEach(([meta,kind,key]) => {
    assert(quizKey(meta,kind) === key, 'Unrelated score epoch must stay unchanged: ' + meta.id + '/' + kind);
    const store = {'sec:existing-section':true, [key]:{score:12,total:15}, ['station-final:editorial-20261029:v2:'+kind]:{score:1,total:15}};
    assert(savedResults(meta,store)[kind] === store[key] && store['sec:existing-section'], 'Unrelated saved score and theory progress must survive: ' + meta.id + '/' + kind);
});
const architectureRefs = {
    station7: ['linux-packet-to-handler', 'server-queues-two-bottlenecks', 'load-balancing-connections-requests'],
    station8: ['request-execution-workbook', 'architecture-boundaries', 'dependency-fanout-workbook', 'replica-state-workbook'],
    station9: ['write-lifecycle', 'replication-path', 'replication-failover', 'cache-race', 'cache-pressure', 'outbox-transaction', 'outbox-delivery'],
    station10: ['request-budget-architecture', 'proxy-release-timeline']
};
const systemsRefs = {
    station3: ['request-memory-arena'],
    station5: ['loader-before-main'],
    'station5-linux': ['linux-mapped-generations', 'linux-cpu-quota-workbook'],
    station6: ['shared-state-architecture'],
    'station9-sql': ['sql-join-multiplication', 'sql-window-peers']
};
const foundationsRefs = {
    station1: ['object-representation-access', 'representation-copy-bit-cast'],
    station3: ['numeric-sizes-conversions', 'numeric-intermediate-narrowing',
        'lookup-adl', 'adl-customization', 'parameter-packs-fold', 'template-specialization-choices',
        'chrono-types-units', 'chrono-deadline-clock'],
    station5: ['global-initialization-order', 'global-lifetime-workbook']
};
const deepeningRefs = {
    station5: ['conan-target-lock-workbook','gdb-core-regression','perf-cpu-wait-workbook'],
    station7: ['linux-name-resolution-path','split-dns-debug-workbook','bounded-asio-server-contract','bounded-asio-server-lab'],
    'station7-netlab': ['netlab-tcp-loss-slow-reader'],
    'station7-traffic': ['traffic-real-tcp-evidence'],
    'station9-sql': ['sql-relationship-design'],
    station9: ['schema-history-boundaries','physical-join-workbook','query-memory-spill-lab','postgres-recovery-real-lab'],
    station16: ['failure-model','unknown-outcome','operation-histories','consistency-contracts','partitions-cap',
        'quorum-intersections','raft-log-commit','raft-elections-reads','logical-physical-clocks','leases-fencing',
        'sharding-key-design','shard-migration','workflow-state-machine','workflow-recovery','compensation-not-rollback',
        'coordination-choices','atomic-commit-boundaries','distributed-final-workbook']
};
const optionalTopicRefs = {
    'station5-linux': ['linux-unix-sockets','linux-unix-descriptor-transfer'],
    'station7-netlab': ['netlab-vlan-boundaries','netlab-stp-loop-recovery','netlab-ospf-route-convergence','netlab-bgp-policy-choice']
};
const newTopicRefs = Object.assign({}, architectureRefs, systemsRefs, {'station7-netlab':[], 'station7-traffic':[], station16:[]});
Object.keys(newTopicRefs).forEach(id => {
    const retainedAuditRefs = id === 'station3' ? ['templates-class'] : [];
    const expected = (id === 'station7' ? ['private-public-addresses', 'dhcp-network-config'] : []).concat(newTopicRefs[id], retainedAuditRefs, foundationsRefs[id] || [], deepeningRefs[id] || []);
    assert(JSON.stringify(priorityRefs(id)) === JSON.stringify(expected), 'Wrong editorial priorities for ' + id);
    const disposable = priorityRefs(id); disposable.push('not-a-section');
    assert(JSON.stringify(priorityRefs(id)) === JSON.stringify(expected), 'Priority callers must not mutate future selections');
    assert(JSON.stringify(checkpointRefs(id)) === JSON.stringify(id === 'station5-linux' ? [] : expected), 'Wrong checkpoint priorities for ' + id);
});
assert(JSON.stringify(priorityRefs('station1')) === JSON.stringify(foundationsRefs.station1), 'Object-representation priorities must use station1 only');
assert(JSON.stringify(checkpointRefs('station1')) === JSON.stringify(foundationsRefs.station1), 'Station1 helper must keep checkpoint priorities coherent');
['station0', 'station30', 'station5-linux-extra', 'station7-netlab-extra', 'station70', 'station9-sql-extra'].forEach(id => {
    assert(priorityRefs(id).length === 0, 'Priorities must use exact station IDs, not a shared number: ' + id);
    assert(finalBudgets(id) === null, 'Final budgets must use exact station IDs: ' + id);
    assert(checkpointRefs(id).length === 0, 'Checkpoint priorities must use exact station IDs: ' + id);
    assert(optionalRefs(id).length === 0, 'Optional exclusions must use exact station IDs: ' + id);
});
Object.entries(optionalTopicRefs).forEach(([id, refs]) => {
    assert(JSON.stringify(optionalRefs(id)) === JSON.stringify(refs), 'Wrong optional specialization refs: ' + id);
    const disposable = optionalRefs(id); disposable.push('not-a-section');
    assert(JSON.stringify(optionalRefs(id)) === JSON.stringify(refs), 'Optional-ref callers must not mutate future selection');
});
const linuxBudgets = {'os-boundary':4, processes:4, descriptors:4, 'files-storage':4, memory:5, 'signals-limits':4};
assert(JSON.stringify(finalBudgets('station5-linux')) === JSON.stringify(linuxBudgets), '5Б needs five memory slots without losing any module');
const disposableBudget = finalBudgets('station5-linux'); disposableBudget.memory = 0;
assert(finalBudgets('station5-linux').memory === 5, 'Budget callers must not mutate future selections');
const postgresBudgets = {storage:2,transactions:2,'concurrent-update':2,isolation:2,indexes:2,
    'cpp-storage':2,pool:2,evolution:2,design:2,replication:3,cache:2,delivery:2};
assert(JSON.stringify(finalBudgets('station9')) === JSON.stringify(postgresBudgets), 'PostgreSQL final must keep all twelve modules and one extra replication slot');
assert(Object.values(postgresBudgets).reduce((sum,n)=>sum+n,0) === 25, 'PostgreSQL budget must total exactly 25');
const disposablePostgresBudget = finalBudgets('station9'); disposablePostgresBudget.replication=0;
assert(finalBudgets('station9').replication === 3, 'PostgreSQL budget must be returned independently');
Object.keys(newTopicRefs).filter(id => !['station5-linux','station9'].includes(id)).forEach(id =>
    assert(finalBudgets(id) === null, 'Unrelated finals must retain their existing allocation: ' + id));
assert(source.includes('var priorityRefs = assessmentPriorityRefs(meta.id);'), 'The app must use the tested priority helper');
const workshop = source.slice(source.indexOf('  function ServiceWorkshopEntry('), source.indexOf('  function SubstationNav('));
function renderLinks(number, id) {
    const h = (type, props, ...children) => typeof type === 'function' ? type(props || {}) : ({type, props:props || {}, children:children.flat(Infinity)});
    return new Function('meta', 'h', helper + workshop + ';return PracticeLinks();')({number,id}, h);
}
function links(node) {
    if (!node || typeof node !== 'object') return [];
    return (node.type === 'a' ? [node.props.href] : []).concat((node.children || []).flatMap(links));
}
let gaps = 0;
let analyticCount = 0, practicalCount = 0;
let authoredQuestions = 0, reachableQuestions = 0;
const contentDir=GLib.Dir.open('roadmap/content',0), stationIds=[];
for (let name;(name=contentDir.read_name())!==null;) {
    const match=name.match(/^station(\d+(?:-[a-z]+)?)\.json$/);
    if (match) stationIds.push(/^\d+$/.test(match[1]) ? Number(match[1]) : match[1]);
}
stationIds.sort((a,b)=>parseInt(a)-parseInt(b) || String(a).localeCompare(String(b)));
// Frozen pre-stage banks from /tmp/course-gap-baseline.1tyjSB, read on 2026-11-05.
// Hash the exact authored prefixes: additions must not replace old indexed cases.
const preservedBankPrefixes = {
    station5:{basic:[23,'a4e78f1bf7b1aee9db28251efea07e68b66bb77cee3b91bc393b6014c1af6f64'],advanced:[38,'f7cfc48888a79566ab1ff81d6779d25468cb8e18279c808cdf00dc310cf0cb77'],interview:[21,'db76d110081a419f651d32cd25065700e6a40f17e883b89e60c1772aa9748827']},
    'station5-linux':{basic:[22,'8f413b3e1a56362edc3c4111db1966696f7814bd159170850d9cced77a1ce3a4'],advanced:[12,'95d35e6b1fbcf491e25ecbde828265e784b7cebd6be93f2ba45f08db499c693c'],interview:[24,'f6fc8447a3ac3707950c1746204d055337527cec9d0b45ef84a8bfcb631a098f']},
    station7:{basic:[53,'5d1d9fd13ce8ea5e2c01ec5076109cafde1ed78129e09fef62a2e4297233ad40'],advanced:[85,'90706ef0a70555f565452f948f0db6b597b75125ad1d915fd0a84fa718558677'],interview:[64,'604b3ef2afbd22ac740429fe01bce50f2eb3b8d4966bb6dc86d1e3e7017daa61']},
    'station7-netlab':{basic:[18,'1604309bd51623a80007ad275260804018003a0240513c30954f4a9ae93aa13f'],advanced:[12,'666b565465e32e30f63eb2da3b4ddb82b8e762ba4b36d742aec12b8f3aeca8c4'],interview:[20,'58987c377cbad97fe6beb8f8cdc11a77a2384a9062be75e3ce64204ddadd83f7']},
    'station7-traffic':{basic:[18,'73233cd6f6f991c1ce2da8de6f8dbb179943f40a26ca83eee971debb1f0c80c4'],advanced:[18,'1315db244d91f41a97dc9864d48744dc8784beda3b0dc07826b2a3d4c0db50fe'],interview:[18,'255662761733dc2804bc9a808a18792649d4ef111500a501e334d5268d7bcb64']},
    'station9-sql':{basic:[29,'e7283eb06786ee1004f90edfadbbfcf01af59e60b89ab43b5a5094c9e6c6d093'],advanced:[8,'109a9fd63da329b37893506159ffa292280c36d330b571c84a8e9029bac77111'],interview:[10,'80b5f347150bc93de7680073ae9b650f9a0ce2a7f5cf281b7e0c34245a9f06d6']},
    station9:{basic:[29,'7e8a17f447e76492e27fa5f4c1616f6c4344f232b7bb6f6153f7c21aa8b74576'],advanced:[15,'a66b9998e64b003d406b76447a51f650a398b7c12ef82d48120c0ee12480acda'],interview:[22,'b1b9c191c94dedde5fc2a53b10c01d10db6db1d294e9e03742984d948cd23757']},
    station11:{basic:[32,'cb1937e716a8a23c249924ce5aa245d062215a66de59c69591e24dc767af6576'],advanced:[24,'af113de82cbe234d4628d7b4a2f479eeca4a27490ffd3e1327cb13a48661061f'],interview:[16,'eaec6b966d67ea10f102987c0568e294e82211559db8eb6d91d10fa7981eb541']},
    station15:{basic:[37,'2253d028b7ee56e2c789b4d6262f1cdbf64f8bcb6198c52e641cfa7b3d6f10fb'],advanced:[38,'dcc2774f89797309880e614e6c1ba2195d749afb3866347eaf05f23f26a587da'],interview:[19,'fbf9ebf177a0e39a5c1b0c906800d93a44c9b3010607ee0badc6cd08146984e0']}
};
for (const i of stationIds) {
    const data = JSON.parse(read('roadmap/content/station' + i + '.json'));
    Object.entries(preservedBankPrefixes[data.meta.id] || {}).forEach(([bank,[count,expected]]) => {
        assert(data.quizzes[bank].length >= count, 'Pre-stage bank was shortened: ' + data.meta.id + '/' + bank);
        const actual = GLib.compute_checksum_for_string(GLib.ChecksumType.SHA256,JSON.stringify(data.quizzes[bank].slice(0,count)),-1);
        assert(actual === expected, 'Indexed pre-stage question changed: ' + data.meta.id + '/' + bank);
    });
    const plan = JSON.parse(read('roadmap/content/checkpoints/station' + i + '.json'));
    data.checkpoints = Object.fromEntries(Object.entries(plan.modules).map(([id,entries]) => [id,entries.map(entry => entry.bank ? data.quizzes[entry.bank][entry.index] : entry)]));
    const resources = links(renderLinks(data.meta.number, data.meta.id));
    assert(resources.length > 0, 'Missing external practice for station ' + i);
    resources.forEach(url => assert((/^https:\/\//.test(url) && !url.includes('/problems/https:')) || /^service_workshop\.html#(?:local|database|vm)$/.test(url) || /^cpp_station(?:11_messaging|12_redis|13_kubernetes|14_observability|15_security|16_distributed_systems)\.html#section=[a-z0-9-]+$/.test(url), 'Malformed practice link'));
    const ownWorkshop = resources.filter(url => url.startsWith('service_workshop.html'));
    assert(ownWorkshop.length === ([8,9,10].includes(i) ? 1 : 0), 'Workshop routing must be limited to stations 8, 9B and 10');
    const before = JSON.stringify(data.quizzes);
    const analytical = data.tasks.filter(task => !practice(task));
    const practical = data.tasks.filter(practice);
    analyticCount += analytical.length; practicalCount += practical.length;
    assert(analytical.length + practical.length === data.tasks.length, 'Every task must remain accessible');
    assert(new Set(analytical.concat(practical)).size === data.tasks.length, 'Task routing must not duplicate or lose tasks');
    const priorities = priorityRefs(data.meta.id);
    const budgets = finalBudgets(data.meta.id);
    const shortPriorities = checkpointRefs(data.meta.id);
    const questions = select(data.quizzes, data.substations, 25, data.meta.number <= 4, priorities, budgets, data.checkpoints, optionalRefs(data.meta.id));
    const inApp = appAssessment(data, data.substations[0].id);
    assert(JSON.stringify(inApp.quizzes.basic) === JSON.stringify(questions), 'App final selection differs from tested helper: ' + data.meta.id);
    assert(inApp.quizzes.interview === data.quizzes.interview, 'The app must expose the full interview bank: ' + data.meta.id);
    assert(questions.length === 25, 'Expected 25 questions: station ' + i);
    const allTraining = training(data.quizzes);
    assert(allTraining.length === data.quizzes.basic.length + data.quizzes.advanced.length, 'Training must retain every authored basic/advanced position: ' + data.meta.id);
    assert(new Set(allTraining.map(entry => entry.id)).size === allTraining.length, 'Training IDs must not deduplicate equal question text: ' + data.meta.id);
    const visible = new Set(questions.concat(data.substations.flatMap(module => appAssessment(data, module.id).checkpoint), allTraining.map(entry => entry.question), data.quizzes.interview));
    const authored = Object.values(data.quizzes).flat();
    authored.forEach(question => assert(visible.has(question), 'Authored question has no real UI route: ' + data.meta.id + '/' + question.q));
    authoredQuestions += authored.length; reachableQuestions += authored.filter(question => visible.has(question)).length;
    [5, 10, 15].forEach(size => {
        const sets = batches(allTraining, size);
        assert(sets.every(items => items.length > 0 && items.length <= size), 'Training set size must stay manageable');
        assert(JSON.stringify(sets.flat().map(entry => entry.id)) === JSON.stringify(allTraining.map(entry => entry.id)), 'Sequential sets must expose every question without gaps or repeats: ' + data.meta.id);
    });
    assert(new Set(questions).size === 25, 'No duplicate question');
    assert(!questions.some(q => q.q === 'Что делает std::move на самом деле?'), 'Editorially excluded duplicate must stay out of finals');
    data.substations.forEach(module => {
        assert(questions.some(q => q.substation === module.id), 'Missing module ' + module.id);
        const count = data.quizzes.basic.filter(q => q.substation === module.id).length;
        assert(count >= 2, 'Incomplete checkpoint: station ' + i + ', ' + module.id + ': ' + count + ' basic question(s)');
        const checkpoint = chapter(data.quizzes, module.id, shortPriorities, data.checkpoints);
        assert(JSON.stringify(appAssessment(data,module.id).checkpoint) === JSON.stringify(checkpoint), 'App checkpoint differs from tested helper: ' + data.meta.id + '/' + module.id);
        assert(checkpoint.length >= 5, 'Every checkpoint must contain at least five tasks: station ' + i + ', ' + module.id);
        assert(checkpoint.length === data.checkpoints[module.id].length, 'Checkpoint selection must retain all authored tasks: ' + data.meta.id + '/' + module.id);
        assert(new Set(checkpoint).size === checkpoint.length, 'Checkpoint must not duplicate questions');
        assert(checkpoint.every(q => q.substation === module.id), 'Checkpoint must belong to its subchapter');
        const finalStems = new Set(questions.map(q=>q.q.replace(/\s+/g,' ').trim().toLocaleLowerCase('ru')));
        assert(checkpoint.every(q => !finalStems.has(q.q.replace(/\s+/g,' ').trim().toLocaleLowerCase('ru'))), 'Checkpoint must not repeat the final exam');
        ['basic', 'advanced', 'all'].forEach(kind => {
            const filtered = training(data.quizzes, module.id, kind);
            const expected = (kind === 'all' ? ['basic', 'advanced'] : [kind]).flatMap(key => data.quizzes[key].filter(q => q.substation === module.id));
            assert(filtered.length === expected.length && filtered.every((entry, index) => entry.question === expected[index]), 'Training filters must retain source order and all own questions: ' + data.meta.id + '/' + module.id + '/' + kind);
        });
    });
    assert(JSON.stringify(data.quizzes) === before, 'Bank mutated');
    assert(JSON.stringify(select(data.quizzes, data.substations, 25, data.meta.number <= 4, priorities, budgets, data.checkpoints, optionalRefs(data.meta.id))) === JSON.stringify(questions), 'Final test selection must be stable');
    if (deepeningRefs[data.meta.id]) {
        deepeningRefs[data.meta.id].forEach(ref => {
            assert(data.theory.some(section => section.id === ref), 'New priority has no canonical theory: ' + ref);
            assert(questions.some(q => q.theoryRefs.includes(ref)), 'New mandatory topic missing from the 25-question final: ' + ref);
            assert(data.quizzes.basic.some(q => q.theoryRefs.includes(ref)), 'New topic has no basic case: ' + ref);
        });
    }
    if (optionalTopicRefs[data.meta.id]) {
        const excluded = optionalTopicRefs[data.meta.id];
        assert(!questions.some(q => q.theoryRefs.some(ref => excluded.includes(ref))), 'Optional specialization leaked into mandatory final: ' + data.meta.id);
        excluded.forEach(ref => {
            assert(data.theory.some(section => section.id === ref), 'Optional theory absent: ' + ref);
            const cases = authored.filter(q => q.theoryRefs.includes(ref));
            assert(cases.length > 0, 'Optional section lost all assessments: ' + ref);
            cases.forEach(q => assert(visible.has(q), 'Optional case hidden instead of routed to training/interview: ' + ref));
        });
    }
    if (architectureRefs[data.meta.id]) {
        const refs = architectureRefs[data.meta.id];
        const checkpoints = data.substations.flatMap(module => chapter(data.quizzes, module.id, priorities, data.checkpoints));
        const visible = new Set(questions.concat(checkpoints, allTraining.map(entry=>entry.question), data.quizzes.interview));
        const concernsArchitecture = q => q.theoryRefs.some(ref => refs.includes(ref));
        const basicArchitecture = data.quizzes.basic.filter(concernsArchitecture);
        assert(basicArchitecture.length >= refs.length, 'Missing new basic architecture questions: ' + data.meta.id);
        basicArchitecture.forEach(q => assert(visible.has(q), 'Architecture question must remain reachable: ' + q.q));
        data.quizzes.interview.filter(concernsArchitecture).forEach(q => assert(visible.has(q), 'Architecture interview question hidden: ' + q.q));
        refs.forEach(ref => {
            assert(data.theory.some(section => section.id === ref), 'Priority refers to missing theory: ' + ref);
            assert(questions.some(q => q.theoryRefs.includes(ref)), 'Architecture topic missing from the 25-question final: ' + ref);
            assert(data.quizzes.interview.some(q => q.theoryRefs.includes(ref)), 'Each architecture section needs an interview case: ' + ref);
        });
        data.tasks.filter(concernsArchitecture).forEach(task =>
            assert(practice(task) === (task.level === 'Практика'), 'Architecture exercise routed to the wrong destination: ' + task.title));
        ['basic', 'advanced', 'interview'].forEach(kind => {
            const editorial = ['station7','station8','station9','station10'].includes(data.meta.id) && (kind === 'basic' || kind === 'interview');
            const epoch = reviewEpoch(data.meta.id,kind,editorial ? 'editorial-20261029:v1' : 'architecture-20261025:v1');
            assert(quizKey(data.meta, kind) === 'station-final:' + epoch + ':' + kind, 'Changed assessment must not reuse old scores: ' + data.meta.id + '/' + kind);
        });
    }
    if (systemsRefs[data.meta.id]) {
        const refs = systemsRefs[data.meta.id];
        const checkpoints = data.substations.flatMap(module => appAssessment(data, module.id).checkpoint);
        const visible = new Set(questions.concat(checkpoints, allTraining.map(entry=>entry.question), data.quizzes.interview));
        const concernsSystems = q => q.theoryRefs.some(ref => refs.includes(ref));
        const newBasic = data.quizzes.basic.filter(concernsSystems);
        assert(newBasic.length >= refs.length * 2, 'Missing new systems-depth basic cases: ' + data.meta.id);
        newBasic.forEach(q => assert(visible.has(q), 'New basic question must be reachable in a checkpoint or final: ' + q.q));
        data.quizzes.interview.filter(concernsSystems).forEach(q =>
            assert(visible.has(q), 'Systems-depth interview question hidden: ' + q.q));
        refs.forEach(ref => {
            assert(data.theory.some(section => section.id === ref), 'Priority refers to missing theory: ' + ref);
            assert(questions.some(q => q.theoryRefs.includes(ref)), 'Systems-depth topic missing from the 25-question final: ' + ref);
            assert(data.quizzes.interview.filter(q => q.theoryRefs.includes(ref)).length >= 2, 'Each systems-depth section needs two interview cases: ' + ref);
        });
        const newTasks = data.tasks.filter(concernsSystems);
        assert(newTasks.length > 0, 'Missing systems-depth laboratory: ' + data.meta.id);
        newTasks.forEach(task => assert(task.level === 'Практика' && practice(task), 'New laboratory must remain in practice: ' + task.title));
        ['basic', 'advanced', 'interview'].forEach(kind => {
            const editorial = ['station3','station5','station5-linux','station6','station9-sql'].includes(data.meta.id) && (kind === 'basic' || kind === 'interview');
            const foundations = foundationsIds.includes(data.meta.id) && (kind === 'basic' || kind === 'interview');
            const epoch = reviewEpoch(data.meta.id,kind,foundations ? 'foundations-20261105:v1' : editorial ? 'editorial-20261029:v1' : 'systems-depth-20261025:v1');
            assert(quizKey(data.meta, kind) === 'station-final:' + epoch + ':' + kind, 'Changed systems assessment must not reuse old scores: ' + data.meta.id + '/' + kind);
        });
    }
    if (foundationsRefs[data.meta.id]) {
        const refs = foundationsRefs[data.meta.id];
        refs.forEach(ref => {
            assert(data.theory.some(section => section.id === ref), 'Foundation priority has no theory: ' + ref);
            assert(questions.some(question => question.theoryRefs.includes(ref)), 'Foundation section missing from 25-question final: ' + ref);
            assert(data.quizzes.basic.some(question => question.theoryRefs.includes(ref)), 'Foundation section missing a basic case: ' + ref);
        });
        // An interview case can combine adjacent sections; the complete bank
        // remains visible rather than being reduced to one case per heading.
        assert(data.quizzes.interview.some(question => question.theoryRefs.some(ref => refs.includes(ref))), 'Foundation additions missing from the interview bank: ' + data.meta.id);
        ['basic', 'interview'].forEach(kind => assert(quizKey(data.meta, kind) === 'station-final:' + reviewEpoch(data.meta.id,kind,'foundations-20261105:v1') + ':' + kind, 'Foundation score must have a fresh exact-station epoch: ' + data.meta.id));
    }
    if (data.meta.number <= 4) {
        const addedTopics = ['valid-states-factories', 'smart-ptr-deep', 'nvi-interface-evolution', 'templates-class', 'external-effects-guarantees'];
        assert(questions.some(q => q.theoryRefs.includes(addedTopics[i])), 'Audit question must be reachable in the final test: ' + i);
        const previous = select(data.quizzes, data.substations, 25);
        const coverage = qs => new Set(qs.flatMap(q => q.theoryRefs)).size;
        assert(coverage(questions) >= coverage(previous), 'Do not reduce topic coverage');
    }
    if (data.meta.id === 'station7') {
        const refs = ['private-public-addresses', 'dhcp-network-config', 'inbound-access-cgnat',
            'vpn-network-context', 'ssh-home-access', 'network-diagnostics-basics', 'network-access-workbook'];
        const added = Object.values(data.quizzes).flat().filter(q => q.theoryRefs.some(ref => refs.includes(ref)));
        const checkpoints = data.substations.flatMap(module => chapter(data.quizzes, module.id, priorities, data.checkpoints));
        const visible = new Set(questions.concat(checkpoints, allTraining.map(entry=>entry.question), data.quizzes.interview));
        assert(added.length >= 26, 'Networking additions missing');
        added.forEach(q => assert(visible.has(q), 'Authored network question must be reachable, not hidden in an unused bank: ' + q.q));
        ['private-public-addresses','dhcp-network-config','inbound-access-cgnat','ssh-home-access'].forEach(ref =>
            assert(questions.some(q => q.theoryRefs.includes(ref)), 'Network foundation missing from final: ' + ref));
        data.tasks.filter(t => t.substation === 'remote-access').forEach(task => assert(practice(task), 'Network design lab must be in practice, not only analysis'));
    }
    if (data.meta.id === 'station5-linux') {
        const checkpoints = data.substations.flatMap(module => appAssessment(data, module.id).checkpoint);
        const visible = new Set(questions.concat(checkpoints, allTraining.map(entry=>entry.question), data.quizzes.interview));
        Object.values(data.quizzes).flat().forEach(q => assert(visible.has(q), 'Linux question hidden in an unused bank: ' + q.q));
        data.tasks.forEach(task => assert(practice(task), 'Linux open lab must be routed to practice'));
        data.substations.forEach(module => assert(questions.filter(q => q.substation === module.id).length === linuxBudgets[module.id], 'Wrong Linux final allocation: ' + module.id));
        assert(checkpoints.some(q => q.theoryRefs.includes('linux-inspection-basics')), 'The donated strace final slot must remain available in the real checkpoint');
        ['linux-syscall-contract','linux-fork-exec-wait','linux-fd-open-description','linux-io-results',
            'linux-dup-pipe-inheritance','linux-paths-inodes','linux-file-durability','linux-address-space','linux-signal-model',
            'linux-mapped-generations','linux-cpu-quota-workbook'].forEach(ref =>
            assert(questions.some(q => q.theoryRefs.includes(ref)), 'Linux core missing from final: ' + ref));
    }
    if (data.meta.id === 'station7-netlab') {
        const checkpoints = data.substations.flatMap(module => chapter(data.quizzes, module.id, null, data.checkpoints));
        const visible = new Set(questions.concat(checkpoints, allTraining.map(entry=>entry.question), data.quizzes.interview));
        Object.values(data.quizzes).flat().forEach(q => assert(visible.has(q), 'Network lab question hidden in an unused bank: ' + q.q));
        data.tasks.forEach(task => assert(practice(task), 'Network lab open exercise must be routed to practice'));
        ['netlab-isolation-boundary','netlab-build-observe','netlab-route-next-hop','netlab-nft-rules',
            'netlab-conntrack-states','netlab-snat-reply','netlab-dnat-filter','netlab-ipv6-addresses'].forEach(ref =>
            assert(questions.some(q => q.theoryRefs.includes(ref)), 'Network lab core missing from final: ' + ref));
    }
    if (data.meta.id === 'station9') {
        data.substations.forEach(module => assert(questions.filter(q=>q.substation===module.id).length === postgresBudgets[module.id], 'Wrong PostgreSQL final allocation: ' + module.id));
    }
}
report('PASS: ' + stationIds.length + ' final tests × 25 questions, full substation coverage, stable selection, no mutation. Short-check gaps: ' + gaps);
report('Task routing: ' + analyticCount + ' open-answer checks, ' + practicalCount + ' practical tasks; no source task deleted');
report('PASS: ' + reachableQuestions + '/' + authoredQuestions + ' authored questions reachable through real assessment/training routes');
assert(source.includes('station-final:v3:'), 'Changed final selection must not reuse the old score key');
[
    [{id:'station0',number:0}, 'basic', 'station-final:coverage:v1:basic'],
    [{id:'station0',number:0}, 'interview', 'station-final:v2:interview'],
    [{id:'station1',number:1}, 'basic', 'station-final:foundations-20261105:v1:basic'],
    [{id:'station1',number:1}, 'interview', 'station-final:foundations-20261105:v1:interview'],
    [{id:'station1-extra',number:1}, 'basic', 'station-final:coverage:v1:basic'],
    [{id:'station1-extra',number:1}, 'interview', 'station-final:interview-gaps:v1:interview'],
    [{id:'station2',number:2}, 'advanced', 'station-final:v2:advanced'],
    [{id:'station3',number:3}, 'advanced', 'station-final:systems-depth-20261025:v1:advanced'],
    [{id:'station4-extra',number:4}, 'basic', 'station-final:coverage:v1:basic'],
    [{id:'station4-extra',number:4}, 'interview', 'station-final:v2:interview'],
    [{id:'station2-extra',number:2}, 'basic', 'station-final:coverage:v1:basic'],
    [{id:'station2-extra',number:2}, 'interview', 'station-final:v2:interview'],
    [{id:'station3-extra',number:3}, 'basic', 'station-final:coverage:v1:basic'],
    [{id:'station5-extra',number:5}, 'basic', 'station-final:v3:basic'],
    [{id:'station7-netlab',number:7}, 'basic', 'station-final:deepening-20261105:v1:basic'],
    [{id:'station7-netlab',number:7}, 'interview', 'station-final:deepening-20261105:v1:interview'],
    [{id:'station7-traffic',number:7}, 'basic', 'station-final:deepening-20261105:v1:basic'],
    [{id:'station7-traffic',number:7}, 'interview', 'station-final:deepening-20261105:v1:interview'],
    [{id:'station11-extra',number:11}, 'basic', 'station-final:v3:basic'],
    [{id:'station15-extra',number:15}, 'basic', 'station-final:v3:basic'],
    [{id:'station16-extra',number:16}, 'interview', 'station-final:v2:interview'],
    [{id:'station9-extra',number:9}, 'basic', 'station-final:database-split:v1:basic'],
    [{id:'station9-extra',number:9}, 'interview', 'station-final:audit-20261015:v1:interview']
].forEach(([meta,kind,expected]) => assert(quizKey(meta,kind) === expected, 'Unrelated assessment score key changed: ' + meta.id + '/' + kind));
report('PASS: architecture/systems/foundations/deepening final topics, optional specializations remain in training/interview, all questions reachable, all 5Б questions preserved, practice routing and isolated score epochs; shared-window progress and reset');
