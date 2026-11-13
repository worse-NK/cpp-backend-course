// Canonical navigation across all stations; isolated hooks/geometry, not pixels.
const harnessSource = imports.byteArray.toString(imports.gi.GLib.file_get_contents('roadmap/tools/test_map_harness.js')[1]);
const {mapAssert:assert,mapFixture,mapFixtureIds,mapEnvironment,mapNodes:nodes,mapText:text,mapHasClass:hasClass} = new Function(harnessSource + '\nreturn {mapAssert,mapFixture,mapFixtureIds,mapEnvironment,mapNodes,mapText,mapHasClass};')();
const ids = mapFixtureIds();
assert(ids.length === 21,'All 21 canonical stations are exercised');
let chapters = 0, lessons = 0, checkpoints = 0, labs = 0;
for (const id of ids) {
  const data = mapFixture(id), before = JSON.stringify(data);
  const env = mapEnvironment(data);
  let tree = env.render();
  assert(env.chapters().length === data.substations.length,id + ': exact chapter inventory');
  assert(env.chapters().every(node => node.type === 'button' && node.props.type === 'button' && node.props['aria-expanded'] === false),id + ': native collapsed chapter controls');
  assert(!nodes(tree).some(node => node.props['data-map-section']),id + ': initial branches are collapsed');
  assert(tree.props['aria-label'] === 'Карта станции ' + env.api.stationDisplayNumber(),id + ': current station identity is accessible');
  for (const module of data.substations) {
    const sections = data.theory.filter(section => section.substation === module.id && !/(?:-final-workbook|clock-worked-example)$/.test(section.id));
    tree = env.open(module.id);
    assert(env.actions.length === 0,id + ': inspecting a chapter does not change the article');
    assert(env.chapters().filter(node => node.props['aria-expanded']).length === 1,id + ': one expanded chapter');
    assert(env.chapters().every(node => text(node).includes(data.substations.find(item => item.id === node.props['data-map-module']).title)),id + ': exact authored chapter names');
    const controls = env.chapter(module.id).props['aria-controls'];
    assert(nodes(tree).some(node => node.props.id === controls && !node.props.hidden),id + ': valid open ARIA panel');
    const sectionLinks = nodes(tree).filter(node => node.props['data-map-section']);
    assert(sectionLinks.length === sections.length,id + ': every topic remains available in the full expanded list');
    for (const section of sections) {
      const link = sectionLinks.find(node => node.props['data-map-section'] === section.id);
      assert(link.type === 'a' && link.props.href === '#section=' + encodeURIComponent(section.id),id + ': exact native topic URL');
      assert(text(link).includes(section.title),id + ': full topic title');
      let prevented = false;
      link.props.onClick({ctrlKey:true,button:0,preventDefault() {prevented = true;}});
      assert(!prevented && env.actions.length === 0,id + ': modified clicks remain native');
      env.props.store['sec:' + section.id] = true;
      for (const block of section.blocks.filter(block => block.type === 'lab')) {
        const expected = env.window.courseLabHref(block.lab,block.scenario,id,section.id);
        assert(nodes(tree).some(node => node.type === 'a' && node.props.href === expected),id + ': lab has a contextual contents entry');
        labs++;
      }
      lessons++;
    }
    tree = env.render();
    assert(hasClass(env.chapter(module.id),'is-complete'),id + ': fully studied chapter turns complete');
    const checkpoint = nodes(tree).find(node => node.props['data-map-checkpoint'] === module.id);
    assert(checkpoint && checkpoint.type === 'a' && checkpoint.props.href === '#view=checkpoint&module=' + encodeURIComponent(module.id),id + ': exact checkpoint URL');
    assert(text(checkpoint).includes(String(data.checkpoints[module.id].length)),id + ': actual authored checkpoint count');
    env.chapter(module.id).props.onClick(); tree = env.render();
    assert(!nodes(tree).some(node => node.props['data-map-section']),id + ': second click closes the chapter');
    assert(hasClass(env.chapter(module.id),'is-complete'),id + ': studied state survives collapse');
    chapters++; checkpoints++;
  }
  const finish = nodes(tree).filter(node => hasClass(node,'map-finish'));
  assert(finish.length === 1 && finish[0].props.href === '#view=final',id + ': one clear finale destination');
  finish[0].props.onClick();
  assert(env.actions.length === 1 && env.actions[0][1] === 'final',id + ': finale opens its hub, not a quiz');
  assert(nodes(tree).some(node => node.type === 'a' && node.props.href === 'sources.html#' + id),id + ': source index uses this station');
  if (data.meta.number === 9) assert(nodes(tree).some(node => node.type === 'a' && node.props.href === 'sql_trainer.html'),id + ': persistent SQL trainer access');
  const stage = {station8:'local',station9:'database',station10:'vm'}[id];
  if (stage) assert(nodes(tree).some(node => node.type === 'a' && node.props.href === 'service_workshop.html#' + stage),id + ': server workshop route');
  const own = env.api.backendLabEntry(id);
  if (own) assert(nodes(tree).some(node => node.type === 'a' && node.props.href === own.file + '#section=' + own.section),id + ': own backend preparation route');
  assert(env.writes.length === 0,id + ': map does not write storage or change score namespaces');
  assert(JSON.stringify(data) === before,id + ': authored data was not mutated');
  env.dispose();
  assert(env.observers.size === 0 && [...env.events.values()].every(set => set.size === 0),id + ': no listener leak');
}
const sizing = mapEnvironment(mapFixture('station0'));
sizing.render();
sizing.setHeight(1400); sizing.render();
sizing.scroll(100); sizing.render(); assert(sizing.offset() === -84,'Tall map follows downward page movement');
sizing.scroll(1000); sizing.render(); assert(sizing.offset() === -416,'Tall map pins its bottom edge');
sizing.scroll(800); sizing.render(); assert(sizing.offset() === -216,'Reverse movement reveals the top');
sizing.scroll(0); sizing.render(); assert(sizing.offset() === 16,'Tall map pins its top edge on upward movement');
sizing.setHeight(560); sizing.render(); assert(sizing.offset() === 16,'Collapsed fitting map resets to the top');
assert(sizing.programmaticScrolls.length === 0,'Map behavior never scrolls the page programmatically');
sizing.dispose();
print('PASS: ' + ids.length + ' production maps, ' + chapters + ' chapters, ' + lessons + ' topics, ' + checkpoints + ' checkpoints, ' + labs + ' lab entries; unchanged storage identities, full lists and directional sticky. Model only.');
