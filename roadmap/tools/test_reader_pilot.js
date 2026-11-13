// Run: gjs roadmap/tools/test_reader_pilot.js
// Actual shared React components and actual security controller with isolated
// hooks, history, storage and DOM models. Not a browser, layout or AT audit.
const GLib = imports.gi.GLib, BA = imports.byteArray;
const read = path => BA.toString(GLib.file_get_contents(path)[1]);
function assert(ok, message) { if (!ok) throw new Error(message); }
const helper = read('roadmap/tools/test_station_reading_ui.js');
const split = helper.indexOf('let sectionLists = 0');
assert(split >= 0, 'Reading helper boundary changed: update the harness explicitly');
const api = new Function(helper.slice(0, split) +
    '; return {environment,loadStation,orderedSections,nodes,text,button};')();
const {environment, loadStation, orderedSections, nodes, text, button} = api;
const classes = node => String(node.props.className || '').split(/\s+/);
const withClass = (tree, name) => nodes(tree).filter(node => classes(node).includes(name));
const readerContent = view => nodes(view.appTree).find(node => node.props.id === 'lesson-content');
function settle(env) {
    const view = env.render(); env.flushAnimationFrames(); return view;
}
function expectPosition(view, module, label, stationLabel = 'Станция 15') {
    const breadcrumbs = withClass(view.appTree, 'reader-breadcrumb');
    assert(breadcrumbs.length === 1, 'One reader breadcrumb in every pilot view');
    assert(text(breadcrumbs[0]).includes(module ? module.title : stationLabel),
           'Breadcrumb identifies the chapter or station-wide scope');
    assert(text(breadcrumbs[0]).includes(label), 'Breadcrumb identifies the active view: ' + label);
    assert(nodes(breadcrumbs[0]).some(node => node.props['aria-current']), 'Breadcrumb exposes the current position');
}
function expectFocusedLesson(env, startScrolls, startFocuses) {
    const scrolls = env.scrolls.slice(startScrolls), focuses = env.focuses.slice(startFocuses);
    assert(scrolls.length === 1 && scrolls[0].id === 'lesson-content', 'Explicit navigation scrolls to the lesson, not the site heading');
    assert(scrolls[0].settings.block === 'start' && scrolls[0].settings.behavior === 'auto', 'Reader navigation does not animate the whole page');
    assert(focuses.length === 1 && focuses[0].id === 'lesson-content' &&
           focuses[0].settings.preventScroll === true, 'One focus handoff without a second browser scroll');
    assert(env.doc.activeElement.id === 'lesson-content', 'Keyboard focus follows the opened lesson');
}

const data = loadStation('station15'), before = JSON.stringify(data);
const firstModule = data.substations[0], first = orderedSections(data, firstModule.id)[0];
const access = data.theory.find(section => section.id === 'access-laboratory');
const accessModule = data.substations.find(module => module.id === access.substation);
const env = environment(data, '#section=' + first.id);
let view = settle(env);
assert(withClass(view.appTree, 'reader-header').length === 1, 'Pilot uses a compact reader header');
assert(withClass(view.appTree, 'hero').length === 0, 'Old large station hero is absent in the pilot');
assert(classes(view.appTree).includes('reader-page'), 'Pilot main has its scoped reader class');
assert(readerContent(view) && classes(readerContent(view)).includes('reader-content') &&
       readerContent(view).props.tabIndex === -1, 'Focusable lesson wrapper exists');
assert(nodes(readerContent(view)).includes(view.node), 'Theory is inside the shared content wrapper');
assert(env.focuses.length === 0 && env.scrolls.length === 0, 'Initial deep link does not override browser position');
expectPosition(view, firstModule, 'Теория');
env.preserved();

const skip = withClass(view.appTree, 'reader-skip')[0];
assert(skip && skip.type === 'a' && skip.props.href === '#lesson-content', 'Skip navigation retains a semantic fallback destination');
const beforeSkip = {hash:env.win.location.hash, history:env.historyCalls.length,
    store:JSON.stringify(env.stored()), scrolls:env.scrolls.length, focuses:env.focuses.length};
let skipPrevented = false;
skip.props.onClick({preventDefault:() => { skipPrevented = true; }}); view = settle(env);
assert(skipPrevented && env.win.location.hash === beforeSkip.hash && env.historyCalls.length === beforeSkip.history,
       'Working skip navigation does not replace the canonical section route or add history');
assert(JSON.stringify(env.stored()) === beforeSkip.store, 'Skipping chrome changes no learner progress or scores');
expectFocusedLesson(env, beforeSkip.scrolls, beforeSkip.focuses); env.preserved();

let startScrolls = env.scrolls.length, startFocuses = env.focuses.length;
env.nav().props.onNavigate(access.id); view = settle(env);
assert(env.historyCalls.at(-1).method === 'push' && env.win.location.hash === '#section=' + access.id,
       'Explicit section navigation creates a history entry');
assert(view.node.props.initialSectionId === access.id, 'Section route selects the intended theory');
expectPosition(view, accessModule, 'Теория');
expectFocusedLesson(env, startScrolls, startFocuses); env.preserved();
const accessRead = JSON.parse(env.backing.cpp_course_last_read_v1);
assert(accessRead.file === data.meta.sourceFile && accessRead.section === access.id,
       'Reading position keeps the established file/section format');

startScrolls = env.scrolls.length; startFocuses = env.focuses.length;
env.nav().props.onCheckpoint(accessModule.id); view = settle(env);
assert(!view.node && env.nav().props.view === 'checkpoint', 'Checkpoint replaces, not overlaps theory');
assert(env.historyCalls.at(-1).method === 'push' &&
       env.win.location.hash === '#view=checkpoint&module=' + accessModule.id, 'Checkpoint has a navigable URL');
expectPosition(view, accessModule, 'Закрепление');
expectFocusedLesson(env, startScrolls, startFocuses);
const checkpoint = nodes(view.appTree).find(node => typeof node.type === 'function' && node.props.kind === 'checkpoint');
assert(checkpoint && checkpoint.props.questions.length === 5, 'The chapter checkpoint retains its five actual questions');
assert(nodes(readerContent(view)).includes(checkpoint), 'Checkpoint stays inside the shared lesson wrapper');
env.preserved();

const callsBeforeBack = env.historyCalls.length;
startScrolls = env.scrolls.length; startFocuses = env.focuses.length;
env.history.back(); view = settle(env);
assert(view.node && view.node.props.initialSectionId === access.id, 'Back restores the previous section');
expectPosition(view, accessModule, 'Теория');
assert(env.scrolls.length === startScrolls && env.focuses.length === startFocuses,
       'History restoration leaves scroll and focus restoration to the browser');
assert(env.historyCalls.length === callsBeforeBack, 'Restoration does not create or replace history entries');
env.history.forward(); view = settle(env);
assert(!view.node && env.nav().props.view === 'checkpoint', 'Forward restores the checkpoint');
assert(env.scrolls.length === startScrolls && env.focuses.length === startFocuses,
       'Forward also avoids forced top scroll/focus');
env.preserved();

// Exercise the real hash listener, including an invalid route. A URL supplied
// by another component is not rewritten into a fabricated existing section.
env.win.location.hash = '#section=' + first.id; env.emit('hashchange'); view = settle(env);
assert(view.node.props.initialSectionId === first.id, 'Hash navigation still follows section links');
assert(env.scrolls.length === startScrolls && env.focuses.length === startFocuses,
       'External hash restoration does not force reader scroll');
env.win.location.hash = '#section=missing'; env.emit('hashchange'); view = settle(env);
assert(view.node.props.initialSectionId === first.id, 'Invalid hash does not select a nonexistent section');
env.preserved(); env.dispose();

// A plain station URL must become a valid first history entry; otherwise the
// first Back would have no meaningful section to restore.
const plain = environment(loadStation('station15'), '');
view = settle(plain);
assert(plain.win.location.hash === '#section=' + first.id &&
       plain.historyCalls[0].method === 'replace', 'Pilot normalizes its initial empty route');
plain.nav().props.onNavigate(access.id); settle(plain); plain.history.back(); view = settle(plain);
assert(view.node.props.initialSectionId === first.id, 'Back from first explicit navigation restores the initial lesson');
plain.preserved(); plain.dispose();

// A restored checkpoint must not retain a workbook selected later in a
// different chapter. Its real onBack callback returns to chapter A's final
// ordinary section, not the unrelated workbook.
const restored = environment(loadStation('station15'), '#section=' + first.id);
settle(restored);
restored.nav().props.onCheckpoint(accessModule.id); settle(restored);
const workbook = data.theory.find(section => /(?:-final-workbook|clock-worked-example)$/.test(section.id));
assert(workbook && workbook.substation !== accessModule.id, 'Regression fixture needs a workbook in another chapter');
restored.nav().props.onNavigate(workbook.id); view = settle(restored);
assert(view.node.props.initialSectionId === workbook.id && view.node.props.sections.length === 1,
       'Regression setup opens the actual separate workbook');
const beforeRestore = {history:restored.historyCalls.length, scrolls:restored.scrolls.length, focuses:restored.focuses.length};
restored.history.back(); view = settle(restored);
const restoredQuiz = nodes(view.appTree).find(node => typeof node.type === 'function' && node.props.kind === 'checkpoint');
assert(!view.node && restoredQuiz && restored.nav().props.active === accessModule.id,
       'Browser Back restores chapter A checkpoint from another chapter workbook');
assert(restored.historyCalls.length === beforeRestore.history && restored.scrolls.length === beforeRestore.scrolls &&
       restored.focuses.length === beforeRestore.focuses, 'Checkpoint history restoration does not force position or mutate history');
restoredQuiz.props.onBack(); view = settle(restored);
const finalOrdinary = orderedSections(data, accessModule.id).at(-1);
assert(view.node.props.initialSectionId === finalOrdinary.id && !view.node.props.sections.some(section => section.id === workbook.id),
       'Checkpoint Back uses its own chapter, never the stale unrelated workbook');
restored.preserved(); restored.dispose();

// Pilot contents use real links so modified clicks keep native browser
// behavior. An ordinary primary click still delegates to the real route API.
const links = environment(loadStation('station15'), '#section=' + first.id), clicks = [];
const contentsOwner = links.mount(links.api.SubstationNav, {items:data.substations, active:firstModule.id,
    selected:first.id, view:'theory', store:links.stored(), analysisCount:2,
    onChoose:id => clicks.push(['chapter', id]), onNavigate:id => clicks.push(['section', id]),
    onCheckpoint:id => clicks.push(['checkpoint', id]), onPage:id => clicks.push(['page', id])});
let contents = contentsOwner.render();
const chapterLink = withClass(contents, 'map-chapter-toggle')[0];
assert(chapterLink.type === 'button' && chapterLink.props['aria-expanded'] === false &&
       chapterLink.props['aria-current'] && !('aria-pressed' in chapterLink.props),
       'Current chapter is a native independent disclosure, not an article navigation action');
chapterLink.props.onClick(); contents = contentsOwner.render();
assert(!clicks.length, 'Opening a map chapter leaves the article route unchanged');
const sectionLink = nodes(withClass(contents, 'map-lessons').find(node => !node.props.hidden)).find(node =>
    node.type === 'a' && node.props.href === '#section=' + first.id);
assert(sectionLink && sectionLink.props['aria-current'] === 'page', 'Current section is a semantic deep link');
for (const modifiers of [{metaKey:true}, {ctrlKey:true}, {shiftKey:true}, {altKey:true}, {button:1}, {defaultPrevented:true}]) {
    let prevented = false;
    sectionLink.props.onClick({button:0, ...modifiers, preventDefault:() => { prevented = true; }});
    assert(!prevented && !clicks.length, 'Modified/default-handled link click remains native');
}
let prevented = false;
sectionLink.props.onClick({button:0, preventDefault:() => { prevented = true; }});
assert(prevented && JSON.stringify(clicks) === JSON.stringify([['section', first.id]]),
       'Unmodified primary click uses the existing section navigation callback exactly once');
assert(withClass(contents, 'map-checkpoint')[0].type === 'a' &&
       withClass(contents, 'map-checkpoint')[0].props.href === '#view=checkpoint&module=' + firstModule.id,
       'Checkpoint contents action has its exact deep-link URL');
links.dispose();

// Only the approved three security entries use the in-tab pilot. SQL and
// other established labs retain their independent-tab learning workflow.
let labEntries = 0;
for (const id of ['station15', 'station0']) {
    const fixture = loadStation(id), e = environment(fixture);
    new Function('window', read('roadmap/generated/visual-labs.data.js'))(e.win);
    for (const section of fixture.theory) for (const block of section.blocks.filter(block => block.type === 'lab')) {
        const item = e.win.COURSE_LABS.find(lab => lab.id === block.lab);
        const expected = e.win.courseLabHref(item.id, block.scenario, id, section.id);
        const entry = e.mount(e.api.LabBlock, {section, block}).render();
        const link = nodes(entry).find(node => node.type === 'a');
        assert(link && link.props.href === expected, 'Lab retains its exact canonical return-context URL');
        const pilot = id === 'station15' && block.lab === 'security';
        assert(pilot ? link.props.target !== '_blank' : link.props.target === '_blank',
               'Only station15 security labs switch to in-tab navigation');
        const navOwner = e.mount(e.api.SubstationNav, {items:fixture.substations, active:section.substation,
            selected:section.id, view:'theory', store:e.stored(), analysisCount:0,
            onChoose:() => {}, onNavigate:() => {}, onCheckpoint:() => {}, onPage:() => {}});
        let nav = navOwner.render();
        nodes(nav).find(node => node.props['data-map-module'] === section.substation).props.onClick();
        nav = navOwner.render();
        const sidebarLink = nodes(nav).find(node => node.type === 'a' &&
            classes(node).includes('map-lab-link') && node.props.href === expected);
        assert(sidebarLink && (pilot ? sidebarLink.props.target !== '_blank' : sidebarLink.props.target === '_blank'),
               'Contents entry uses the same pilot navigation rule');
        ++labEntries;
    }
    e.dispose();
}

// A lab return is an explicit allowlisted section context, not a completion
// event. Both onward choices must use the already existing section/checkpoint.
for (const id of ['access-laboratory', 'transport-laboratory', 'outbound-laboratory']) {
    const e = environment(loadStation('station15'), '#section=' + id + '&fromLab=security');
    view = settle(e);
    assert(withClass(view.appTree, 'reader-return').length === 1, 'Approved lab return is acknowledged: ' + id);
    const actions = withClass(view.appTree, 'reader-return-actions');
    assert(actions.length === 1, 'Return banner offers one quiet action group');
    assert(nodes(actions[0]).filter(node => node.type === 'button' || node.type === 'a').length === 2,
           'Return has exactly the chapter and checkpoint choices');
    const startScrolls = e.scrolls.length, startFocuses = e.focuses.length;
    button(actions[0], 'Продолжить чтение').props.onClick(); view = settle(e);
    assert(view.node.props.initialSectionId === id && e.win.location.hash === '#section=' + id,
           'Continue reading dismisses the marker without skipping the current explanation');
    assert(!withClass(view.appTree, 'reader-return').length, 'Dismissed return banner stays dismissed');
    expectFocusedLesson(e, startScrolls, startFocuses);
    e.preserved(); e.dispose();
    const check = environment(loadStation('station15'), '#section=' + id + '&fromLab=security');
    view = settle(check);
    button(withClass(view.appTree, 'reader-return-actions')[0], 'Закрепить тему').props.onClick(); view = settle(check);
    const section = data.theory.find(section => section.id === id);
    assert(check.win.location.hash === '#view=checkpoint&module=' + section.substation && !view.node,
           'Return checkpoint belongs to the same chapter, not a station-wide quiz');
    check.preserved(); check.dispose();
}
for (const hash of ['#section=learning-route&fromLab=security', '#section=access-laboratory&fromLab=untrusted']) {
    const e = environment(loadStation('station15'), hash); view = settle(e);
    assert(withClass(view.appTree, 'reader-return').length === 0, 'Unapproved return marker is ignored');
    e.preserved(); e.dispose();
}

const pages = environment(loadStation('station15'), '#section=' + access.id);
settle(pages);
for (const [page, label] of Object.entries({final:'Завершение станции', quiz:'Итоговый тест',
    interview:'Интервью', tasks:'Практика', analysis:'Вопросы с разбором', training:'Тренировка'})) {
    const startScrolls = pages.scrolls.length, startFocuses = pages.focuses.length;
    pages.nav().props.onPage(page); view = settle(pages);
    assert(readerContent(view) && pages.nav().props.view === page, 'Every ending view uses the shared reader surface: ' + page);
    assert(pages.historyCalls.at(-1).method === 'push' && pages.win.location.hash === '#view=' + page,
           'Every explicit ending-page navigation has a history entry: ' + page);
    expectPosition(view, null, label); expectFocusedLesson(pages, startScrolls, startFocuses);
    pages.preserved();
}
pages.dispose();

// The production reader is shared by all twenty-one current stations. Exercise
// real components against every canonical fixture, not a station0 copy with
// its metadata renamed. Preserve scores, unknown fields and every content byte.
const allDirectory = GLib.Dir.open('roadmap/content', 0), allIds = [];
for (let name; (name = allDirectory.read_name()) !== null;) {
    if (/^station\d+(?:-[a-z]+)?\.json$/.test(name)) allIds.push(name.replace(/\.json$/, ''));
}
assert(allIds.length === 21, 'Expected all twenty-one canonical reader fixtures');
let productionReaders = 0, nativeContents = 0;
for (const id of allIds) {
    const fixture = loadStation(id), original = JSON.stringify(fixture), module = fixture.substations[0];
    const ordinary = orderedSections(fixture, module.id);
    assert(ordinary.length > 1, id + ': history test needs two actual lessons');
    const e = environment(fixture, '#section=' + ordinary[0].id);
    view = settle(e);
    assert(withClass(view.appTree, 'reader-header').length === 1 && !withClass(view.appTree, 'hero').length,
           id + ': one compact production reader header');
    assert(readerContent(view) && readerContent(view).props.tabIndex === -1,
           id + ': keyboard-focusable reading surface');
    assert(!e.scrolls.length && !e.focuses.length, id + ': initial deep link leaves browser position alone');
    expectPosition(view, module, 'Теория');
    const railOwner = e.mount(e.api.SubstationNav, e.nav().props);
    let rail = railOwner.render();
    const chapter = nodes(rail).find(node => node.props['data-map-module'] === module.id);
    assert(chapter.type === 'button' && chapter.props['aria-expanded'] === false,
           id + ': chapter starts as a native closed disclosure');
    const historyBeforeDisclosure = e.historyCalls.length;
    chapter.props.onClick(); rail = railOwner.render();
    assert(e.historyCalls.length === historyBeforeDisclosure, id + ': opening a chapter does not create article history');
    const target = nodes(rail).find(node => node.type === 'a' && node.props.href === '#section=' + ordinary[1].id);
    assert(target && typeof target.props.onClick === 'function', id + ': second lesson has its native sidebar URL');
    const ending = nodes(rail).find(node => node.type === 'a' && node.props.href === '#view=final');
    assert(ending, id + ': station completion has one discoverable native URL');
    for (const modifier of [{ctrlKey:true}, {metaKey:true}, {shiftKey:true}, {altKey:true}, {button:1}, {defaultPrevented:true}]) {
        let intercepted = false;
        target.props.onClick({button:0, ...modifier, preventDefault:() => { intercepted = true; }});
        assert(!intercepted && e.win.location.hash === '#section=' + ordinary[0].id,
               id + ': modified links retain native browser behavior');
    }
    let intercepted = false;
    const initialHistory = e.historyCalls.length;
    target.props.onClick({button:0, preventDefault:() => { intercepted = true; }}); view = settle(e);
    assert(intercepted && view.node.props.initialSectionId === ordinary[1].id &&
           e.historyCalls.length === initialHistory + 1 && e.historyCalls.at(-1).method === 'push',
           id + ': explicit native-link navigation adds one history entry');
    expectFocusedLesson(e, 0, 0);
    const restores = {scrolls:e.scrolls.length, focuses:e.focuses.length, history:e.historyCalls.length};
    e.history.back(); view = settle(e);
    assert(view.node.props.initialSectionId === ordinary[0].id, id + ': Back restores the original lesson');
    e.history.forward(); view = settle(e);
    assert(view.node.props.initialSectionId === ordinary[1].id, id + ': Forward restores the selected lesson');
    assert(e.scrolls.length === restores.scrolls && e.focuses.length === restores.focuses &&
           e.historyCalls.length === restores.history, id + ': Back/Forward never override browser restoration');
    e.nav().props.onCheckpoint(module.id); view = settle(e);
    assert(e.win.location.hash === '#view=checkpoint&module=' + module.id && !view.node,
           id + ': checkpoint keeps its exact chapter route');
    expectPosition(view, module, 'Закрепление');
    e.nav().props.onPage('final'); view = settle(e);
    expectPosition(view, null, 'Завершение станции', 'Станция ' + fixture.meta.number);
    e.preserved();
    assert(JSON.stringify(fixture) === original, id + ': reader did not mutate canonical course data');
    e.dispose(); ++productionReaders; nativeContents += 3;
}
assert(JSON.stringify(data) === before, 'Pilot navigation never mutates canonical lesson content');

// Actual standalone security controller, using its existing isolated DOM
// harness (no duplicated model or simplified replacement controller).
const securityHelper = read('roadmap/tools/test_security_labs_ui.js');
const securityBoundary = securityHelper.indexOf('let visited=0;');
assert(securityBoundary >= 0, 'Security helper boundary changed: update the harness explicitly');
const securityEnvironment = new Function(securityHelper.slice(0, securityBoundary) + ';return environment;')();
let stages = 0;
for (const scenario of ['access', 'outbound', 'tls']) {
    const e = securityEnvironment('#lab=security&scenario=' + scenario + '&from=station15&section=' +
        ({access:'access-laboratory',outbound:'outbound-laboratory',tls:'transport-laboratory'}[scenario]));
    for (let step = 0; step < 5; ++step) {
        e.action('step-' + step); e.action('model-form', 'submit');
        assert(e.get('after-run-next').hidden, 'No duplicate next action appears after running the model');
        assert(!e.get('after-run-next').listeners.click, 'Hidden compatibility control has no active navigation listener');
        assert(e.get('lesson-return').hidden === (step !== 4), 'Theory return is shown at the last stage');
        if (step !== 4) assert(!e.get('next').disabled, 'The sole next-stage action remains usable');
        else {
            const expected = 'cpp_station15_security.html#section=' + e.window.SecurityLabs.modules[scenario].section + '&fromLab=security';
            assert(e.get('lesson-return').getAttribute('href') === expected, 'Final return has the approved section and pilot marker');
        }
        ++stages;
    }
}
const hostile = securityEnvironment('#scenario=access&from=https%3A%2F%2Fevil.test&section=missing&step=4');
assert(hostile.get('lesson-return').getAttribute('href') ===
       'cpp_station15_security.html#section=access-laboratory&fromLab=security', 'Untrusted lab context cannot become a return URL');

// Generated page contracts for the production-wide rollout. Design-comparison
// previews remain a separate isolated fixture and are checked by their suite.
const directory = GLib.Dir.open('roadmap/content', 0);
let shells = 0;
for (let name; (name = directory.read_name()) !== null;) {
    if (!/^station\d+(?:-[a-z]+)?\.json$/.test(name)) continue;
    const fixture = JSON.parse(read('roadmap/content/' + name));
    const html = read('roadmap/' + fixture.meta.sourceFile);
    assert(/<body\b[^>]*class="[^"]*\bcourse-reader\b/.test(html), 'Reader body class is enabled: ' + name);
    assert(/href="assets\/course-reader\.css(?:\?[^\"]*)?"/.test(html), 'Shared reader stylesheet exists: ' + name);
    assert(/href="assets\/course-ui\.css(?:\?[^\"]*)?"/.test(html), 'Shared foundation stylesheet exists: ' + name);
    assert(!/fonts\.(?:googleapis|gstatic)\.com/.test(html), 'Production reader fonts work without a remote request: ' + name);
    ++shells;
}
const securityHTML = read('roadmap/security_labs.html');
assert(/<body\b[^>]*class="[^"]*\bcourse-lab-pilot\b/.test(securityHTML) &&
       /href="assets\/course-ui\.css(?:\?[^\"]*)?"/.test(securityHTML), 'Security lab uses the same scoped design foundation');
assert(/class="skip-link"\s+href="#experiment"/.test(securityHTML), 'Lab keeps a semantic skip link to the experiment');
const foundationCSS = read('roadmap/assets/course-ui.css');
assert(/--course-sans:\s*ui-sans-serif,\s*system-ui/.test(foundationCSS) &&
       /--course-mono:\s*ui-monospace/.test(foundationCSS), 'Reader and laboratory share the explicit system font tokens');
assert(!/fonts\.(?:googleapis|gstatic)\.com/.test(securityHTML), 'Security laboratory does not load a competing external font');
print('PASS: ' + productionReaders + ' production readers, ' + nativeContents + ' native contents destinations, reader/history/focus/return contracts; ' + labEntries + ' lab entry links, ' +
      stages + ' real-controller security stages and ' + shells + ' generated shells. ' +
      'Progress and canonical content retained. DOM/React model only; no browser, layout or assistive-technology audit.');
