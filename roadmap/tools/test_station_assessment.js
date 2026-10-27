const GLib = imports.gi.GLib;
const ByteArray = imports.byteArray;
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
const training = new Function(helper + ';return trainingEntries;')();
const batches = new Function(helper + ';return trainingBatches;')();
const appSelection = source.slice(source.indexOf('    var priorityRefs = assessmentPriorityRefs(meta.id);'), source.indexOf('    var workedSections ='));
function appAssessment(data, moduleId) {
    return new Function('data', 'meta', 'quizzes', 'substations', 'activeSubstationId', helper + appSelection + ';return {quizzes:activeQuizzes,checkpoint:checkpointQuestions};')(
        data, data.meta, data.quizzes, data.substations, moduleId);
}
const keyHelper = source.slice(source.indexOf('    function quizStoreKey('), source.indexOf('    var quizResults ='));
function quizKey(meta, kind) { return new Function('meta', keyHelper + ';return quizStoreKey;')(meta)(kind); }
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
const newTopicRefs = Object.assign({}, architectureRefs, systemsRefs);
Object.keys(newTopicRefs).forEach(id => {
    const expected = (id === 'station7' ? ['private-public-addresses', 'dhcp-network-config'] : []).concat(newTopicRefs[id]);
    assert(JSON.stringify(priorityRefs(id)) === JSON.stringify(expected), 'Wrong editorial priorities for ' + id);
    const disposable = priorityRefs(id); disposable.push('not-a-section');
    assert(JSON.stringify(priorityRefs(id)) === JSON.stringify(expected), 'Priority callers must not mutate future selections');
    assert(JSON.stringify(checkpointRefs(id)) === JSON.stringify(id === 'station5-linux' ? [] : expected), 'Wrong checkpoint priorities for ' + id);
});
['station0', 'station30', 'station5-linux-extra', 'station7-netlab', 'station70', 'station9-sql-extra'].forEach(id => {
    assert(priorityRefs(id).length === 0, 'Priorities must use exact station IDs, not a shared number: ' + id);
    assert(finalBudgets(id) === null, 'Final budgets must use exact station IDs: ' + id);
    assert(checkpointRefs(id).length === 0, 'Checkpoint priorities must use exact station IDs: ' + id);
});
const linuxBudgets = {'os-boundary':4, processes:4, descriptors:4, 'files-storage':4, memory:5, 'signals-limits':4};
assert(JSON.stringify(finalBudgets('station5-linux')) === JSON.stringify(linuxBudgets), '5Б needs five memory slots without losing any module');
const disposableBudget = finalBudgets('station5-linux'); disposableBudget.memory = 0;
assert(finalBudgets('station5-linux').memory === 5, 'Budget callers must not mutate future selections');
Object.keys(newTopicRefs).filter(id => id !== 'station5-linux').forEach(id =>
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
for (const i of [0,1,2,3,4,5,'5-linux',6,7,'7-netlab','7-traffic',8,9,'9-sql',10]) {
    const data = JSON.parse(read('roadmap/content/station' + i + '.json'));
    const plan = JSON.parse(read('roadmap/content/checkpoints/station' + i + '.json'));
    data.checkpoints = Object.fromEntries(Object.entries(plan.modules).map(([id,entries]) => [id,entries.map(entry => entry.bank ? data.quizzes[entry.bank][entry.index] : entry)]));
    const resources = links(renderLinks(data.meta.number, data.meta.id));
    assert(resources.length > 0, 'Missing external practice for station ' + i);
    resources.forEach(url => assert((/^https:\/\//.test(url) && !url.includes('/problems/https:')) || /^service_workshop\.html#(?:local|database|vm)$/.test(url), 'Malformed practice link'));
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
    const questions = select(data.quizzes, data.substations, 25, data.meta.number <= 4, priorities, budgets);
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
        assert(checkpoint.length === 5, 'Every checkpoint must contain five tasks: station ' + i + ', ' + module.id);
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
    assert(JSON.stringify(select(data.quizzes, data.substations, 25, data.meta.number <= 4, priorities, budgets)) === JSON.stringify(questions), 'Final test selection must be stable');
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
        ['basic', 'advanced', 'interview'].forEach(kind =>
            assert(quizKey(data.meta, kind) === 'station-final:architecture-20261025:v1:' + kind, 'Changed assessment must not reuse old scores: ' + data.meta.id + '/' + kind));
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
        ['basic', 'advanced', 'interview'].forEach(kind =>
            assert(quizKey(data.meta, kind) === 'station-final:systems-depth-20261025:v1:' + kind, 'Changed systems assessment must not reuse old scores: ' + data.meta.id + '/' + kind));
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
}
print('PASS: 15 final tests × 25 questions, full substation coverage, stable selection, no mutation. Short-check gaps: ' + gaps);
print('Task routing: ' + analyticCount + ' open-answer checks, ' + practicalCount + ' practical tasks; no source task deleted');
print('PASS: ' + reachableQuestions + '/' + authoredQuestions + ' authored questions reachable through real assessment/training routes');
assert(source.includes('station-final:v3:'), 'Changed final selection must not reuse the old score key');
[
    [{id:'station0',number:0}, 'basic', 'station-final:coverage:v1:basic'],
    [{id:'station0',number:0}, 'interview', 'station-final:v2:interview'],
    [{id:'station1',number:1}, 'interview', 'station-final:interview-gaps:v1:interview'],
    [{id:'station5-extra',number:5}, 'basic', 'station-final:v3:basic'],
    [{id:'station7-netlab',number:7}, 'basic', 'station-final:netlab-20261021:v1:basic'],
    [{id:'station7-netlab',number:7}, 'interview', 'station-final:netlab-20261021:v1:interview'],
    [{id:'station7-traffic',number:7}, 'basic', 'station-final:traffic-20261026:v1:basic'],
    [{id:'station7-traffic',number:7}, 'interview', 'station-final:traffic-20261026:v1:interview'],
    [{id:'station9-extra',number:9}, 'basic', 'station-final:database-split:v1:basic'],
    [{id:'station9-extra',number:9}, 'interview', 'station-final:audit-20261015:v1:interview']
].forEach(([meta,kind,expected]) => assert(quizKey(meta,kind) === expected, 'Unrelated assessment score key changed: ' + meta.id + '/' + kind));
print('PASS: 16 architecture + 7 systems-depth final topics, all new questions reachable, all 5Б questions preserved, practice routing and isolated score epochs');
