// Shared isolated production-map harness. This models hooks/geometry, not pixels.
const mapGLib = imports.gi.GLib, mapBytes = imports.byteArray;
const mapRead = path => mapBytes.toString(mapGLib.file_get_contents(path)[1]);
function mapAssert(ok, message) { if (!ok) throw new Error(message); }
function mapNodes(tree) {
  return tree && typeof tree === 'object'
    ? [tree, ...(tree.children || []).flatMap(mapNodes)] : [];
}
function mapText(tree) {
  return tree == null || typeof tree === 'boolean' ? '' : typeof tree === 'object'
    ? (tree.children || []).map(mapText).join('') : String(tree);
}
function mapHasClass(node, name) { return String(node.props.className || '').split(/\s+/).includes(name); }
class MapParams {
  constructor(query) {
    this.entries = String(query || '').split('&').map(value => {
      const cut = value.indexOf('='), decode = s => decodeURIComponent(s.replace(/\+/g, ' '));
      return cut < 0 ? [decode(value), ''] : [decode(value.slice(0, cut)), decode(value.slice(cut + 1))];
    });
  }
  get(name) { return this.entries.find(entry => entry[0] === name)?.[1] ?? null; }
}
function mapFixture(id) {
  const holder = {};
  new Function('window', mapRead('roadmap/generated/' + id + '.data.js'))(holder);
  return holder.STATION_DATA;
}
function mapFixtureIds() {
  const dir = mapGLib.Dir.open('roadmap/content', 0), ids = [];
  let name;
  while ((name = dir.read_name()) !== null) if (/^station.*\.json$/.test(name)) ids.push(name.slice(0, -5));
  return ids.sort();
}
function mapEnvironment(data, options = {}) {
  let cursor = 0, changed = false, queued = [], bodyHeight = options.height || 560, nextFrame = 0;
  const cells = [], effects = [], frames = new Map(), observers = new Set(), events = new Map(), eventOptions = new Map();
  const actions = [], writes = [], styleValues = new Map(), programmaticScrolls = [];
  const media = {matches:options.wide !== false, listeners:new Set(),
    addEventListener(type, fn) {if (type === 'change') this.listeners.add(fn);},
    removeEventListener(type, fn) {if (type === 'change') this.listeners.delete(fn);}};
  const useState = initial => {
    const i = cursor++;
    if (!(i in cells)) cells[i] = typeof initial === 'function' ? initial() : initial;
    return [cells[i], value => {
      const next = typeof value === 'function' ? value(cells[i]) : value;
      if (!Object.is(next, cells[i])) {cells[i] = next; changed = true;}
    }];
  };
  const useEffect = (run, deps) => {
    const i = cursor++, previous = effects[i];
    if (!previous || !deps || deps.some((item, j) => !Object.is(item, previous.deps[j]))) queued.push(() => {
      if (previous && typeof previous.cleanup === 'function') previous.cleanup();
      effects[i] = {deps:deps && [...deps], cleanup:run()};
    });
  };
  const React = {
    Fragment:'fragment',createElement:(type, props, ...children) => ({type,props:props || {},children:children.flat(Infinity).filter(value => value !== undefined && value !== null && value !== false)}),
    useState,useEffect,useLayoutEffect:useEffect,
    useRef(initial) {const i = cursor++; if (!(i in cells)) cells[i] = {current:initial}; return cells[i];}
  };
  const win = {React,ReactDOM:{},STATION_DATA:data,location:{hash:options.hash || '',protocol:'https:'},innerHeight:options.viewport || 1000,scrollY:0,
    matchMedia:() => media,
    addEventListener(type, fn, settings) {if (!events.has(type)) events.set(type,new Set()); events.get(type).add(fn); eventOptions.set(fn,settings);},
    removeEventListener(type, fn) {events.get(type)?.delete(fn); eventOptions.delete(fn);},
    requestAnimationFrame(fn) {const id = ++nextFrame; frames.set(id,fn); return id;},cancelAnimationFrame(id) {frames.delete(id);},
    scrollBy(...args) {programmaticScrolls.push(['by',...args]);},scrollTo(...args) {programmaticScrolls.push(['to',...args]);},
    ResizeObserver:class {
      constructor(callback) {this.callback = callback; this.targets = new Set(); observers.add(this);}
      observe(target) {this.targets.add(target);}
      disconnect() {this.targets.clear(); observers.delete(this);}
    }};
  new Function('window',mapRead('roadmap/generated/visual-labs.data.js'))(win);
  const offset = () => parseFloat(styleValues.get('--map-sticky-top') || '16');
  const body = {getBoundingClientRect:() => ({top:offset(),bottom:offset()+bodyHeight,height:bodyHeight})};
  const header = {getBoundingClientRect:() => ({top:offset()+224,bottom:offset()+294,height:70})};
  const rail = {getBoundingClientRect:body.getBoundingClientRect,
    querySelector:selector => selector.includes('map-rail-body') ? body : header,
    style:{setProperty(name,value) {styleValues.set(name,String(value));},getPropertyValue(name) {return styleValues.get(name) || '';}}};
  const doc = {getElementById:id => id === 'root' ? {} : null,documentElement:{get clientHeight() {return win.innerHeight;}}};
  const backing = {[data.meta.storeKey]:JSON.stringify(options.store || {learnerNote:'preserve me'})};
  const storage = {getItem:key => backing[key] || null,setItem:(key,value) => {backing[key] = String(value); writes.push([key,value]);}};
  const source = mapRead('roadmap/assets/station-app.js');
  const needle = '  ReactDOM.createRoot(root).render(h(App));';
  mapAssert(source.includes(needle),'Canonical renderer entry point changed');
  const exported = source.replace(needle,'  window.mapTestApi = {SubstationNav,LabBlock,ServiceWorkshopEntry,backendLabEntry,stationDisplayNumber,stationMapStickyTop,stationMapNeedsPageScroll};');
  new Function('window','document','React','ReactDOM','localStorage','location','URLSearchParams','history',exported)(
    win,doc,React,{},storage,win.location,MapParams,{replaceState() {},pushState() {}});
  const api = win.mapTestApi;
  const currentModule = data.substations.find(item => item.id === options.active) || data.substations[0];
  const currentSections = data.theory.filter(section => section.substation === currentModule.id && !/(?:-final-workbook|clock-worked-example)$/.test(section.id));
  const props = {items:data.substations,active:currentModule.id,selected:options.selected || currentSections[0].id,view:options.view || 'theory',store:options.store || {},analysisCount:8,
    onChoose:id => actions.push(['chapter',id]),onNavigate:id => actions.push(['section',id]),onCheckpoint:id => actions.push(['checkpoint',id]),onPage:id => actions.push(['page',id])};
  const env = {data,props,api,window:win,doc,media,actions,writes,backing,frames,events,eventOptions,observers,styleValues,programmaticScrolls,rail,header,offset,
    render() {
      let tree;
      for (let pass = 0; pass < 24; pass++) {
        cursor = 0; changed = false; queued = [];
        tree = api.SubstationNav(props);
        mapNodes(tree).filter(node => node.props.ref).forEach(node => {
          const target = mapHasClass(node,'map-rail-body') ? body : rail;
          if (typeof node.props.ref === 'function') node.props.ref(target); else node.props.ref.current = target;
        });
        queued.forEach(run => run());
        const pending = [...frames.values()]; frames.clear(); pending.forEach(run => run());
        if (!changed) {env.tree = tree; return tree;}
      }
      throw new Error('Map did not settle: ' + data.meta.id);
    },
    chapters() {return mapNodes(env.tree).filter(node => node.props['data-map-module']);},
    chapter(id) {return env.chapters().find(node => node.props['data-map-module'] === id);},
    open(id) {if (env.chapter(id).props['aria-expanded'] !== true) env.chapter(id).props.onClick(); return env.render();},
    setSearch(value) {mapNodes(env.tree).find(node => node.type === 'input' && node.props.type === 'search').props.onChange({target:{value}}); return env.render();},
    setHeight(value) {bodyHeight = value; observers.forEach(observer => observer.callback([...observer.targets].map(target => ({target}))));},
    scroll(value) {win.scrollY = value; events.get('scroll')?.forEach(fn => fn({type:'scroll'}));},
    resize(value) {win.innerHeight = value; events.get('resize')?.forEach(fn => fn({type:'resize'}));},
    dispose() {effects.forEach(effect => {if (typeof effect?.cleanup === 'function') effect.cleanup();});}
  };
  return env;
}
