// Run: gjs roadmap/tools/test_design_previews.js
// Actual derived station renderer in the existing React/history model.
// No real browser, learner storage, server, layout or accessibility certification.
const GLib = imports.gi.GLib, BA = imports.byteArray;
const read = path => BA.toString(GLib.file_get_contents(path)[1]);
function assert(ok, message) { if (!ok) throw new Error(message); }
function replaceOnce(source, from, to) {
    assert(source.split(from).length === 2, 'Harness boundary changed: ' + from);
    return source.replace(from, to);
}
const appPath = 'roadmap/generated/station-design-preview.app.js';
const source = read(appPath);
new Function(source);
const executableSource = source.replace(/\/\/[^\n]*|\/\*[\s\S]*?\*\//g, '');
assert(!/\blocalStorage\b/.test(executableSource), 'Preview renderer must never access production localStorage');
const helper = read('roadmap/tools/test_station_reading_ui.js');
const boundary = helper.indexOf('let sectionLists = 0');
assert(boundary >= 0, 'Reading model boundary changed');
let model = helper.slice(0, boundary);
model = replaceOnce(model, "const appSource = read('roadmap/assets/station-app.js');",
    'const appSource = read(' + JSON.stringify(appPath) + ');');
model = replaceOnce(model, 'matchMedia:() => ({matches:!!options.reducedMotion}),',
    "matchMedia:query => ({matches:query.includes('min-width') ? options.desktop !== false : !!options.reducedMotion}),");
model = replaceOnce(model, '    win.history = history;', `
    const previewBacking = {}, previewWrites = [], productionAccesses = [];
    win.COURSE_DESIGN_VARIANT = options.variant || 'editorial';
    win.sessionStorage = {
        getItem:key => {
            if (options.storageDenied) throw new Error('Storage denied');
            return previewBacking[key] || null;
        },
        setItem:(key,value) => {
            if (options.storageDenied) throw new Error('Storage denied');
            previewBacking[key] = value; previewWrites.push({key,value});
        }
    };
    storage.getItem = key => { productionAccesses.push({operation:'read',key}); throw new Error('Production storage forbidden'); };
    storage.setItem = (key,value) => { productionAccesses.push({operation:'write',key}); throw new Error('Production storage forbidden'); };
    win.history = history;`);
model = replaceOnce(model, 'window.testApi = {App,Theory,SubstationNav,LabBlock};',
    'window.testApi = {App,Theory,SubstationNav,LabBlock,previewStorage,loadStore};');
model = replaceOnce(model, 'function stored() { return JSON.parse(backing[data.meta.storeKey]); }',
    'function stored() { return win.testApi.loadStore(); }');
model = replaceOnce(model, 'api:win.testApi, mount,',
    'api:win.testApi, mount, previewBacking, previewWrites, productionAccesses,');
model = replaceOnce(model, "'URLSearchParams', 'history', exported)(",
    "'URLSearchParams', 'history', 'confirm', exported)(");
model = replaceOnce(model, 'win, doc, React, {}, storage, win.location, Params, history);',
    'win, doc, React, {}, storage, win.location, Params, history, () => true);');
const api = new Function(model + ';return {environment,loadStation,orderedSections,nodes,text,button};')();
const {environment,loadStation,orderedSections,nodes,text,button} = api;
const originalVariants = ['editorial','workbook','focus'];
const alternativeVariants = ['ribbon','studio','folio'];
const variants = originalVariants.concat(alternativeVariants);
const filenames = Object.fromEntries(variants.map(name => [name,'design_station0_' + name + '.html']));
const namespace = 'cpp_course_design_preview_v1:';
const classHas = (node,name) => String(node.props.className || '').split(/\s+/).includes(name);
const findClass = (tree,name) => nodes(tree).find(node => classHas(node,name));
const settle = env => { const view = env.render(); env.flushAnimationFrames(); return view; };
// Flatten only semantic leaves, not wrapper names. This compares the actual
// rendered lesson, including raw HTML and opaque block components, so moving a
// note into a folio margin cannot silently drop, repeat or reorder the content.
function lessonLeaves(value) {
    if (value == null || typeof value === 'boolean') return [];
    if (typeof value !== 'object') return [['text',String(value)]];
    const props = value.props || {};
    if (props.dangerouslySetInnerHTML) return [['html',props.dangerouslySetInnerHTML.__html]];
    if (typeof value.type === 'function') {
        assert(props.block, 'Unexpected opaque component inside the lesson: ' + value.type.name);
        return [['block',value.type.name,JSON.stringify(props.block)]];
    }
    return (value.children || []).flatMap(lessonLeaves);
}
function nativeLinkChecks(link, env, description) {
    assert(link && link.type === 'a' && typeof link.props.href === 'string', description + ': real anchor');
    for (const modifier of ['ctrlKey','metaKey','shiftKey','altKey']) {
        const hash = env.win.location.hash; let prevented = false;
        link.props.onClick({[modifier]:true,button:0,preventDefault:() => { prevented = true; }});
        assert(!prevented && env.win.location.hash === hash, description + ': modified links remain native: ' + modifier);
    }
    for (const event of [{button:1},{button:0,defaultPrevented:true}]) {
        const hash = env.win.location.hash; let prevented = false;
        link.props.onClick(Object.assign({},event,{preventDefault:() => { prevented = true; }}));
        assert(!prevented && env.win.location.hash === hash, description + ': non-primary/handled event remains native');
    }
}
function expectContents(tree, variant, desktop) {
    if (originalVariants.includes(variant)) {
        assert(tree.type === 'details' && tree.props.open === (desktop && variant !== 'focus'),
            variant + ': original contents has its deliberate initial state');
        return tree;
    }
    assert(tree.type === 'nav' && classHas(tree,'experiment-contents') && tree.props['aria-label'],
        variant + ': alternative contents is a named navigation landmark');
    const details = findClass(tree,'experiment-index');
    assert(details && details.type === 'details' && details.props.open === (desktop && variant === 'studio'),
        variant + ': compact index initial state');
    const summary = details.children.find(node => node && node.type === 'summary');
    assert(summary && text(summary) === (variant === 'folio' ? 'Открыть содержание станции' : 'Разделы подглавы'),
        variant + ': native details has a meaningful visible summary');
    const chapters = findClass(tree,'experiment-chapters');
    assert(chapters && chapters.children.filter(node => node && node.type === 'a').length === canonical.substations.length,
        variant + ': every chapter is directly navigable');
    assert(nodes(findClass(tree,'experiment-ending')).some(node => node.type === 'a' && node.props.href === '#view=final'),
        variant + ': station ending remains discoverable');
    if (variant === 'folio') {
        assert(nodes(details).includes(chapters), variant + ': complete index lives inside the single disclosure');
    } else {
        assert(!nodes(details).includes(chapters), variant + ': chapters stay visible outside the section disclosure');
    }
    return details;
}
function previewData(variant) {
    const data = loadStation('station0');
    data.meta.sourceFile = filenames[variant];
    return data;
}
function assertIsolated(env) {
    assert(!env.productionAccesses.length && !env.writes.length, 'Preview never reads or writes production storage');
    assert(env.previewWrites.every(write => write.key.startsWith(namespace)), 'Every session write has a preview namespace');
    assert(JSON.stringify(JSON.parse(env.backing[env.data.meta.storeKey])) === JSON.stringify(env.original),
        'Production progress fixture remains byte-for-byte equivalent');
}

const canonical = loadStation('station0');
let sectionsChecked = 0, viewsChecked = 0, quizChecks = 0, syntaxChecks = 0;
let folioPairs = 0, alternativeChapterChecks = 0;
for (const variant of variants) {
    const data = previewData(variant), before = JSON.stringify(data);
    const env = environment(data,'#section=why-oop',{variant,desktop:true});
    const reference = environment(previewData('editorial'),'#section=why-oop',{variant:'editorial',desktop:true});
    settle(reference);
    let view = settle(env);
    assert(findClass(view.appTree,alternativeVariants.includes(variant) ? 'experiment-header' : 'reader-header') &&
        !findClass(view.appTree,'hero'), variant + ': intended real reader shell');
    assert(!findClass(view.appTree,alternativeVariants.includes(variant) ? 'reader-header' : 'experiment-header'),
        variant + ': one header, without a hidden duplicate');
    assert(findClass(view.appTree,'reader-content'), variant + ': lesson wrapper retained');
    assert(!env.scrolls.length && !env.focuses.length, variant + ': initial deep link preserves browser position');
    const nav = env.mount(env.api.SubstationNav,env.nav().props);
    let navTree = nav.render();
    expectContents(navTree,variant,true);
    const lessonLink = nodes(navTree).find(node => node.type === 'a' && node.props.href === '#section=why-oop');
    nativeLinkChecks(lessonLink,env,variant + ': contents section');
    if (alternativeVariants.includes(variant)) {
        const chapterLinks = findClass(navTree,'experiment-chapters').children.filter(node => node && node.type === 'a');
        chapterLinks.forEach((link,index) => {
            assert(link.props.href === '#section=' + orderedSections(data,data.substations[index].id)[0].id,
                variant + ': chapter link targets its real first lesson');
            nativeLinkChecks(link,env,variant + ': chapter ' + index);
        });
        const ending = nodes(findClass(navTree,'experiment-ending')).find(node => node.type === 'a' && node.props.href === '#view=final');
        nativeLinkChecks(ending,env,variant + ': station ending');
        for (const module of data.substations) {
            const target = orderedSections(data,module.id)[0];
            const chapter = nodes(findClass(navTree,'experiment-chapters')).find(node => node.type === 'a' &&
                node.props.href === '#section=' + target.id);
            let prevented = false;
            chapter.props.onClick({button:0,preventDefault:() => { prevented = true; }});
            view = settle(env); nav.props = env.nav().props; navTree = nav.render();
            assert(prevented && view.node.props.initialSectionId === target.id,
                variant + ': actual chapter anchor opens its first lesson');
            const selected = nodes(findClass(navTree,'experiment-chapters')).filter(node => node.type === 'a' && node.props['aria-current']);
            assert(selected.length === 1 && selected[0].props.href === '#section=' + target.id,
                variant + ': active chapter is exposed without relying on color');
            assert(nodes(findClass(navTree,'experiment-sections')).filter(node => node.type === 'a').length === orderedSections(data,module.id).length,
                variant + ': section index reflects the newly chosen chapter');
            ++alternativeChapterChecks;
        }
        let search = nodes(navTree).find(node => node.type === 'input' && node.props.type === 'search');
        assert(search && search.props.name && search.props.autoComplete === 'off', variant + ': named labeled search input');
        search.props.onChange({target:{value:'конструктор'}}); navTree = nav.render();
        const matching = data.theory.filter(section => !/(?:-final-workbook|clock-worked-example)$/.test(section.id) &&
            (section.title + ' ' + data.substations.find(module => module.id === section.substation).title).toLocaleLowerCase('ru').includes('конструктор'));
        assert(nodes(findClass(navTree,'experiment-sections')).filter(node => node.type === 'a').length === matching.length && matching.length > 0,
            variant + ': real search indexes lessons across the station');
        search = nodes(navTree).find(node => node.type === 'input' && node.props.type === 'search');
        search.props.onChange({target:{value:'заведомо-несуществующий-раздел'}}); navTree = nav.render();
        assert(!nodes(findClass(navTree,'experiment-sections')).some(node => node.type === 'a') &&
            nodes(navTree).some(node => node.props.role === 'status' && text(node).includes('Попробуй другое название')),
            variant + ': empty search keeps an actionable announced state');
        nodes(navTree).find(node => node.type === 'input' && node.props.type === 'search').props.onChange({target:{value:''}});
        env.nav().props.onNavigate('why-oop'); view = settle(env); nav.props = env.nav().props; navTree = nav.render();
    }
    const skip = findClass(view.appTree,'reader-skip');
    const skipHash = env.win.location.hash, skipCalls = env.historyCalls.length;
    skip.props.onClick({preventDefault() {}}); view = settle(env);
    assert(env.win.location.hash === skipHash && env.historyCalls.length === skipCalls,
        variant + ': skipping chrome does not destroy the canonical route');
    assert(env.focuses.at(-1).id === 'lesson-content', variant + ': skip hands focus to the lesson');

    for (const section of data.theory) {
        env.nav().props.onNavigate(section.id); view = settle(env);
        reference.nav().props.onNavigate(section.id); const referenceView = settle(reference);
        assert(view.node.props.initialSectionId === section.id, variant + ': section deep link: ' + section.id);
        assert(text(findClass(view.tree,'section-title')) === section.title, variant + ': unchanged real title');
        assert(JSON.stringify(view.node.props.sections.find(item => item.id === section.id)) === JSON.stringify(section),
            variant + ': actual theory blocks and code retained: ' + section.id);
        assert(JSON.stringify(lessonLeaves(view.tree)) === JSON.stringify(lessonLeaves(referenceView.tree)),
            variant + ': rendered content, code, self-checks and their order are unchanged: ' + section.id);
        const articles = nodes(view.tree).filter(node => node.type === 'article');
        assert(articles.length === 1 && articles[0].props['data-terms-scope'] === section.id,
            variant + ': one article preserves glossary scope: ' + section.id);
        if (variant === 'folio') {
            assert(classHas(articles[0],'folio-article') && findClass(articles[0],'folio-heading'),
                variant + ': folio adapts article structure, not only its colors');
            const sectionActions = findClass(articles[0],'section-actions');
            assert(sectionActions && (button(sectionActions,'Отметить раздел изученным') ||
                button(sectionActions,'✓ Раздел изучен')), variant + ': folio retains the actual completion action');
            for (const pair of nodes(articles[0]).filter(node => classHas(node,'folio-pair'))) {
                assert(findClass(pair,'folio-main') && findClass(pair,'folio-margin'), variant + ': folio pair has both reading regions');
                assert(!nodes(pair).some(node => classHas(node,'source-note')), variant + ': primary-source notes remain full width');
                ++folioPairs;
            }
        }
        ++sectionsChecked;
    }
    for (const module of data.substations) {
        env.nav().props.onCheckpoint(module.id); view = settle(env);
        const checkpoint = nodes(view.appTree).find(node => typeof node.type === 'function' && node.props.kind === 'checkpoint');
        assert(checkpoint && checkpoint.props.questions.length === 5, variant + ': five checkpoint questions: ' + module.id);
        assert(checkpoint.props.questions.filter(question => question.type === 'assemble').length === 2,
            variant + ': two existing syntax builders preserved: ' + module.id);
        assert(env.win.location.hash === '#view=checkpoint&module=' + module.id, variant + ': checkpoint URL');
        ++viewsChecked;
    }
    for (const page of ['final','quiz','interview','tasks','analysis','training']) {
        env.nav().props.onPage(page); view = settle(env);
        assert(!view.node && findClass(view.appTree,'reader-content'), variant + ': reader handles ' + page);
        assert(env.win.location.hash === '#view=' + page, variant + ': view URL: ' + page);
        assert(!text(findClass(view.appTree,'reader-breadcrumb')).includes('Станция 15'), variant + ': breadcrumb names station0');
        ++viewsChecked;
    }
    env.nav().props.onNavigate('why-oop'); view = settle(env);
    button(view.tree,'Отметить раздел изученным').props.onClick(); view = settle(env);
    assert(env.stored()['sec:why-oop'] === true, variant + ': marking works in isolated session state');
    button(view.tree,'✓ Раздел изучен').props.onClick(); view = settle(env);
    assert(env.stored()['sec:why-oop'] === false, variant + ': unmarking works in isolated session state');
    const settings = findClass(view.appTree,'reading-settings');
    button(settings,'Крупнее').props.onClick(); view = settle(env);
    assert(classHas(view.appTree,'reading-large'), variant + ': larger text setting is functional');
    assert(env.previewBacking[namespace + 'cpp_course_text_size_v1'] === 'large', variant + ': text size also isolated');
    const position = JSON.parse(env.previewBacking[namespace + 'cpp_course_last_read_v1']);
    assert(position.file === filenames[variant] && position.section === 'why-oop', variant + ': isolated recent-location record');
    const previous = env.win.location.hash;
    env.nav().props.onNavigate('constructor'); settle(env);
    const beforeBack = {scrolls:env.scrolls.length,focuses:env.focuses.length,calls:env.historyCalls.length};
    env.history.back(); view = settle(env);
    assert(env.win.location.hash === previous && view.node.props.initialSectionId === 'why-oop', variant + ': browser Back restores lesson');
    assert(env.scrolls.length === beforeBack.scrolls && env.focuses.length === beforeBack.focuses && env.historyCalls.length === beforeBack.calls,
        variant + ': history restore does not force viewport/focus or add entries');
    env.history.forward(); view = settle(env);
    assert(view.node.props.initialSectionId === 'constructor', variant + ': browser Forward restores lesson');

    // Exercise the real Quiz and nested AssemblyAnswer, rather than a synthetic
    // implementation of correctness or a direct onSave call.
    env.nav().props.onCheckpoint(data.substations[0].id); view = settle(env);
    const quizNode = nodes(view.appTree).find(node => typeof node.type === 'function' && node.props.kind === 'checkpoint');
    const quiz = env.mount(quizNode.type,quizNode.props);
    let quizTree = quiz.render();
    const questions = quizNode.props.questions;
    for (let index = 0; index < questions.length; index++) {
        const current = questions[index];
        if (current.type === 'assemble') {
            const assemblyNode = nodes(quizTree).find(node => typeof node.type === 'function' && node.props.question && node.props.onCheck);
            assert(assemblyNode, variant + ': syntax builder mounted inside actual checkpoint');
            const assembly = env.mount(assemblyNode.type,assemblyNode.props);
            let assemblyTree = assembly.render();
            for (const token of current.answer) {
                const pool = findClass(assemblyTree,'assembly-pool');
                const choice = pool.children.find(node => node.props.key === token);
                assert(choice && !choice.props.disabled, variant + ': syntax token available');
                choice.props.onClick(); assemblyTree = assembly.render();
            }
            button(assemblyTree,'Проверить код').props.onClick(); quizTree = quiz.render();
            assert(text(findClass(quizTree,'explanation')).includes(current.why), variant + ': syntax feedback retained');
            ++syntaxChecks; assembly.dispose();
        } else {
            const correct = current.options[current.answer];
            const options = nodes(quizTree).filter(node => node.type === 'button' && classHas(node,'option'));
            const correctNode = options.find(node => text(findClass(node,'option-text')) === correct);
            assert(correctNode, variant + ': actual answer survives shuffling');
            correctNode.props.onClick(); quizTree = quiz.render();
            assert(findClass(quizTree,'option') && text(findClass(quizTree,'explanation')).includes(current.why), variant + ': explanation retained');
            ++quizChecks;
        }
        const next = button(quizTree,index + 1 === questions.length ? 'Показать результат' : 'Следующий вопрос →');
        assert(next, variant + ': answer unlocks next/result action'); next.props.onClick(); quizTree = quiz.render();
    }
    assert(findClass(quizTree,'result-score') && text(findClass(quizTree,'result-score')) === '5/5', variant + ': actual checkpoint result');
    const scores = Object.entries(env.stored()).filter(([key]) => key.startsWith('checkpoint:'));
    assert(scores.length === 1 && scores[0][1].score === 5 && scores[0][1].total === 5,
        variant + ': result saved only inside the isolated preview station state');
    quiz.dispose();
    const wrongQuestion = questions.find(question => question.type !== 'assemble');
    let wrongSaved = null;
    const wrongAttempt = env.mount(quizNode.type,Object.assign({},quizNode.props,{
        questions:[wrongQuestion],onSave:(score,total) => { wrongSaved = {score,total}; }
    }));
    let wrongTree = wrongAttempt.render();
    const wrongChoice = nodes(wrongTree).find(node => node.type === 'button' && classHas(node,'option') &&
        text(findClass(node,'option-text')) !== wrongQuestion.options[wrongQuestion.answer]);
    wrongChoice.props.onClick(); wrongTree = wrongAttempt.render();
    assert(findClass(wrongTree,'wrong') && findClass(wrongTree,'correct') &&
        text(findClass(wrongTree,'explanation')).includes(wrongQuestion.why),
        variant + ': wrong answer reveals both semantic result states and the full explanation');
    button(wrongTree,'Показать результат').props.onClick(); wrongTree = wrongAttempt.render();
    assert(wrongSaved && wrongSaved.score === 0 && wrongSaved.total === 1 &&
        text(findClass(wrongTree,'result-score')) === '0/1', variant + ': wrong answer never earns a point');
    wrongAttempt.dispose();
    view = settle(env);
    button(view.appTree,'Сбросить прогресс').props.onClick(); settle(env);
    assert(Object.keys(env.stored()).length === 0, variant + ': confirmed reset clears only the preview station state');
    assertIsolated(env);
    assert(JSON.stringify(data) === before, variant + ': interactions did not mutate source lessons/questions');
    nav.dispose(); env.dispose(); reference.dispose();

    const mobile = environment(previewData(variant),'#section=why-oop',{variant,desktop:false});
    settle(mobile);
    const mobileContents = mobile.mount(mobile.api.SubstationNav,mobile.nav().props);
    let mobileTree = mobileContents.render();
    const mobileDisclosure = expectContents(mobileTree,variant,false);
    mobileDisclosure.props.onToggle({currentTarget:{open:true}}); mobileTree = mobileContents.render();
    const openDisclosure = originalVariants.includes(variant) ? mobileTree : findClass(mobileTree,'experiment-index');
    assert(openDisclosure.props.open && nodes(mobileTree).some(node => node.type === 'a' && node.props.href === '#section=why-oop'),
        variant + ': native details can reveal the same complete linked contents');
    mobileContents.dispose(); mobile.dispose();
}
assert(folioPairs > 0 && alternativeChapterChecks === 3 * canonical.substations.length,
    'New compositions must actually render margin notes and all chapter actions');

// Denying session storage must not break the lesson or fall back to real
// localStorage. The derived runtime keeps an IIFE-local in-memory store.
const denied = environment(previewData('editorial'),'#section=why-oop',{storageDenied:true});
let deniedView = settle(denied);
button(deniedView.tree,'Отметить раздел изученным').props.onClick(); settle(denied);
assert(denied.stored()['sec:why-oop'] === true, 'Denied session storage still supports temporary in-memory progress');
assertIsolated(denied); denied.dispose();

const generated = {};
new Function('window',read('roadmap/generated/station0-design-preview.data.js'))(generated);
assert(generated.STATION_DATA, 'Preview data has the expected renderer entry point');
for (const key of ['meta','theory','quizzes','tasks','substations','readingOrder','checkpoints']) {
    if (key === 'meta') continue;
    assert(JSON.stringify(generated.STATION_DATA[key]) === JSON.stringify(canonical[key]),
        'Generated preview data preserves the full real station0 ' + key);
}
assert(generated.STATION_DATA.meta.id === 'station0' && generated.STATION_DATA.meta.number === 0,
    'Preview data retains station identity for assessment and lab routing');

// The comparison controller is evaluated unchanged against its small actual
// DOM contract. This checks clone/self-link isolation and native switcher URLs,
// including the observer used after React/pushState navigation.
const controllerSource = read('roadmap/assets/station-design-preview.js');
function controllerEnvironment(variant, hash) {
    const original = JSON.parse(JSON.stringify(generated.STATION_DATA));
    const originalBytes = JSON.stringify(original);
    const links = variants.map(name => ({
        href:filenames[name] + '#section=why-oop',
        getAttribute:key => key === 'data-design-link' ? name : null
    }));
    const courseLink = {href:'cpp_station0_oop_basics.html#section=why-oop'};
    const listeners = {}, observations = [], replacements = [];
    const root = {id:'root'};
    const doc = {
        body:{getAttribute:name => name === 'data-design-variant' ? variant : null},
        querySelectorAll:selector => selector === '[data-design-link]' ? links : [],
        querySelector:selector => selector === '.design-course-link' ? courseLink : null,
        getElementById:id => id === 'root' ? root : null
    };
    const win = {
        STATION_DATA:original, location:{hash:hash || ''},
        addEventListener:(name,callback) => { listeners[name] = callback; },
        history:{replaceState:(_state,_title,next) => { win.location.hash = next; replacements.push(next); }}
    };
    class Observer {
        constructor(callback) { this.callback = callback; }
        observe(element,settings) { observations.push({callback:this.callback,element,settings}); }
    }
    new Function('window','document','MutationObserver',controllerSource)(win,doc,Observer);
    return {win,doc,links,courseLink,listeners,observations,replacements,original,originalBytes};
}
for (const variant of variants) {
    const control = controllerEnvironment(variant,'#view=checkpoint&module=object-model');
    assert(control.win.COURSE_DESIGN_VARIANT === variant, variant + ': explicit allowlisted variant flag');
    assert(control.win.STATION_DATA !== control.original && JSON.stringify(control.original) === control.originalBytes,
        variant + ': controller clones instead of mutating the downloaded canonical data');
    assert(control.win.STATION_DATA.meta.sourceFile === filenames[variant], variant + ': own metadata targets its comparison page');
    assert(JSON.stringify(control.win.STATION_DATA.quizzes) === JSON.stringify(control.original.quizzes) &&
        JSON.stringify(control.win.STATION_DATA.checkpoints) === JSON.stringify(control.original.checkpoints),
        variant + ': controller changes no question or answer bank');
    for (let index = 0; index < control.original.theory.length; index++) {
        const oldSection = control.original.theory[index], newSection = control.win.STATION_DATA.theory[index];
        for (let blockIndex = 0; blockIndex < oldSection.blocks.length; blockIndex++) {
            const oldBlock = oldSection.blocks[blockIndex], newBlock = newSection.blocks[blockIndex];
            for (const key of ['html','prompt','answer']) {
                if (typeof oldBlock[key] !== 'string') continue;
                const expected = oldBlock[key].replace(/href=(["'])cpp_station0_oop_basics\.html(?=[#"'])/g,'href=$1' + filenames[variant]);
                assert(newBlock[key] === expected, variant + ': only exact same-station hrefs rewritten');
            }
            if (oldBlock.code) assert(oldBlock.code === newBlock.code, variant + ': code never rewritten for styling');
        }
    }
    const routes = ['#section=constructor','#view=quiz','#view=training&module=object-model&size=5'];
    routes.forEach((hash,index) => {
        control.win.location.hash = hash;
        if (index === 0) control.listeners.hashchange();
        else if (index === 1) control.listeners.popstate();
        else control.observations[0].callback();
        control.links.forEach((link,i) => assert(link.href === filenames[variants[i]] + hash,
            variant + ': variant switch retains the exact current lesson/view route'));
        assert(control.courseLink.href === canonical.meta.sourceFile + hash, variant + ': explicit current-course link targets the same lesson');
    });
    assert(control.observations.length === 1 && control.observations[0].element.id === 'root' &&
        control.observations[0].settings.childList && control.observations[0].settings.subtree,
        variant + ': observer is scoped to React content, not its own switcher mutations');
    assert(!control.replacements.length, variant + ': controller never overwrites an explicit deep link');
}
const emptyController = controllerEnvironment('editorial','');
assert(emptyController.win.location.hash === '#section=why-oop' && emptyController.replacements.length === 1,
    'An unqualified comparison URL starts at the real introductory lesson');
const invalidController = controllerEnvironment('unknown','#section=why-oop');
assert(invalidController.win.STATION_DATA === invalidController.original && !invalidController.win.COURSE_DESIGN_VARIANT &&
    !invalidController.observations.length && !Object.keys(invalidController.listeners).length,
    'Unknown variant is fail-closed: no data rewrite, observer or handlers');
for (const variant of variants) {
    const html = read('roadmap/' + filenames[variant]);
    assert(html.includes('data-design-variant="' + variant + '"'), variant + ': body identifies its style explicitly');
    assert(html.includes('station-design-variants.css') && html.includes('station-design-preview.js') &&
        html.includes('station-design-preview.app.js') && html.includes('station0-design-preview.data.js'), variant + ': isolated preview assets');
    assert(!/assets\/station-app\.js/.test(html), variant + ': production renderer is not loaded as a second app');
    assert(!/maximum-scale=1|user-scalable=no/.test(html), variant + ': zoom remains available');
    assert(variants.every(name => html.includes('data-design-link="' + name + '"')), variant + ': six actual comparison anchors');
}
print('PASS: 6 isolated real station0 designs; ' + sectionsChecked + ' theory routes, ' + viewsChecked +
    ' checkpoints/final views, ' + quizChecks + ' actual answers, ' + syntaxChecks +
    ' click-to-assemble solutions; native links, focus/history, session namespace and memory fallback. No real-browser/layout audit.');
