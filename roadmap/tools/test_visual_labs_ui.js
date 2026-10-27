// Controller/DOM-model checks, not a visual or live browser test.
const GLib=imports.gi.GLib,BA=imports.byteArray;
const read=p=>BA.toString(GLib.file_get_contents(p)[1]);
function assert(v,m){if(!v)throw Error(m);}
function createDOM(path='roadmap/visual_labs.html'){
  const ids=new Map();
  const decode=s=>s.replace(/&(?:amp|lt|gt|quot|#39);/g,c=>({'&amp;':'&','&lt;':'<','&gt;':'>','&quot;':'"','&#39;':"'"}[c]));
  let doc;
  class Element {
    constructor(tag,attrs={}){this.tagName=tag.toUpperCase();this.attrs={...attrs};this.nodes=[];this.parentElement=null;this.listeners={};this.scrollTop=0;this.scrollHeight=100;this.clientHeight=300;this.offsetTop=0;this.disabled=false;this.hidden='hidden'in attrs;this.open=false;this.value=attrs.value||'';this.style={};if(attrs.id)ids.set(attrs.id,this);}
    get id(){return this.attrs.id||'';} get dataset(){const d={};for(const [k,v]of Object.entries(this.attrs))if(k.startsWith('data-'))d[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=v;return d;}
    get children(){return this.nodes.filter(n=>typeof n!=='string');}
    get textContent(){return this.nodes.map(n=>typeof n==='string'?n:n.textContent).join('');}
    set textContent(v){this.clear();this.nodes=[String(v)];}
    get innerHTML(){return this.raw||'';}
    clear(){for(const child of this.children){child.clear();if(child.id)ids.delete(child.id);}this.nodes=[];}
    set innerHTML(value){this.clear();this.raw=String(value);parse(this.raw,this);}
    append(child){child.parentElement=this;this.nodes.push(child);}
    matches(selector){if(selector==='input,select,textarea')return ['INPUT','SELECT','TEXTAREA'].includes(this.tagName);if(selector.includes(','))return selector.split(',').some(s=>this.matches(s));if(selector.startsWith('[')){const m=selector.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);return m&&m[1]in this.attrs&&(m[2]===undefined||this.attrs[m[1]]===m[2]);}if(selector.startsWith('.'))return (this.attrs.class||'').split(' ').includes(selector.slice(1));return this.tagName===selector.toUpperCase();}
    querySelectorAll(selector){return this.children.flatMap(c=>[...(c.matches(selector)?[c]:[]),...c.querySelectorAll(selector)]);}
    querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
    closest(selector){return this.matches(selector)?this:this.parentElement?this.parentElement.closest(selector):null;}
    setAttribute(k,v){this.attrs[k]=String(v);}removeAttribute(k){delete this.attrs[k];}getAttribute(k){return this.attrs[k]??null;}
    get classList(){return {toggle:(cls,yes)=>{const old=new Set((this.attrs.class||'').split(' ').filter(Boolean));if(yes)old.add(cls);else old.delete(cls);this.attrs.class=[...old].join(' ');}};}
    addEventListener(k,f){this.listeners[k]=f;}focus(){doc.activeElement=this;}
    showModal(){this.open=true;}close(){this.open=false;}
  }
  function parse(html,parent){
    const stack=[parent],re=/<\/?[a-zA-Z][^>]*>|[^<]+/g;let m;
    while((m=re.exec(html))){const token=m[0];if(token.startsWith('</')){if(stack.length>1)stack.pop();continue;}if(token[0]==='<'){
      const tag=token.match(/^<([\w:-]+)/)[1],attrs={};const ar=/([\w:-]+)(?:="([^"]*)"|='([^']*)'|=([^\s>]+))?/g;ar.lastIndex=tag.length+1;let a;
      while((a=ar.exec(token)))attrs[a[1]]=decode(a[2]??a[3]??a[4]??'');
      const el=new Element(tag,attrs);stack.at(-1).append(el);if(!['input','meta','link','br','hr','img','source'].includes(tag)&&!token.endsWith('/>'))stack.push(el);
    }else stack.at(-1).nodes.push(decode(token));}
  }
  const body=new Element('body');
  doc={body,activeElement:null,hidden:false,listeners:{},getElementById:id=>ids.get(id)||null,querySelectorAll:s=>body.querySelectorAll(s),addEventListener(k,f){this.listeners[k]=f;}};
  body.innerHTML=read(path).replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'');return doc;
}
const doc=createDOM(),listeners={},timers=new Map();let nextTimer=0;
class Params {
  constructor(text=''){this.values=new Map(text.replace(/^\?/,'').split('&').filter(Boolean).map(part=>{const [k,...v]=part.split('=');return [decodeURIComponent(k),decodeURIComponent(v.join('='))];}));}
  get(k){return this.values.get(k)??null;}set(k,v){this.values.set(k,String(v));}
  toString(){return [...this.values].map(([k,v])=>encodeURIComponent(k)+'='+encodeURIComponent(v)).join('&');}
}
const win={addEventListener:(k,f)=>listeners[k]=f},location={hash:''};
let routeHash='';Object.defineProperty(location,'hash',{get:()=>routeHash,set:value=>{routeHash=value&&!value.startsWith('#')?'#'+value:value;}});
new Function('window',read('roadmap/generated/visual-labs.data.js'))(win);
new Function('globalThis',read('roadmap/assets/visual-lab-models.js'))(win);
new Function('window','document','location','setInterval','clearInterval','URLSearchParams',read('roadmap/assets/visual-labs.js'))(win,doc,location,(f,ms)=>{timers.set(++nextTimer,{f,ms});return nextTimer;},id=>timers.delete(id),Params);
const get=id=>doc.getElementById(id);
assert(doc.querySelectorAll('.catalog-card').length===10,'Catalog cards');
let visited=0;
for(const lab of win.COURSE_LABS){if(lab.id==='lifetime')continue;for(const mode of lab.scenarios){
  location.hash='#lab='+lab.id+'&scenario='+mode;listeners.hashchange();
  const model=win.CourseLabModels[lab.id](mode);
  for(let i=0;i<model.steps.length;i++){
    get('labRange').oninput({target:{value:i}});
    assert(get('stepTitle').textContent===model.steps[i].title,'Current explanation '+lab.id+'/'+mode);
    assert(get('labScene').innerHTML.length>100,'Empty scene '+lab.id+'/'+mode);
    assert(get('labCode').querySelector('[aria-current="step"]'),'No highlighted code line');
  }
  assert(get('labNext').disabled,'End boundary');get('labReset').onclick();assert(get('labPrev').disabled,'Start boundary');
  get('labNext').onclick();assert(!get('labPrev').disabled,'Forward');get('labPrev').onclick();assert(get('labPrev').disabled,'Backward');
  get('labPlay').onclick();assert(timers.size===1,'Autoplay start');[...timers.values()][0].f();get('labPrev').onclick();assert(timers.size===0,'Manual navigation stops autoplay');
  visited++;
}}
location.hash='#lab=network&scenario=retry&from=station7&section=stream-parser-engineering';listeners.hashchange();
assert(doc.querySelectorAll('[data-mode]').length===3&&!get('labRoot').textContent.includes('Устаревший If-Match'),'Network prerequisites');
assert(get('returnLink').href==='cpp_station7_networking.html#section=stream-parser-engineering','Exact return to theory');
location.hash='#lab=ownership&scenario=unique&from=station1&section=ownership-graph';listeners.hashchange();
assert(doc.querySelectorAll('[data-mode]').every(b=>b.dataset.mode!=='unique'),'Move hidden before value semantics');
location.hash='#lab=concurrency&scenario=separate';listeners.hashchange();
for(const who of ['A','B','A','B','A','B'])get('thread'+who).onclick();
assert(get('labScene').textContent.includes('1'),'Lost update schedule');assert(get('threadA').disabled&&get('threadB').disabled,'Completed scheduler controls');
get('labReset').onclick();for(const who of ['A','A','A','B','B','B'])get('thread'+who).onclick();
assert(get('labScene').textContent.includes('2'),'Alternate custom schedule');
location.hash='#lab=concurrency&scenario=mutex';listeners.hashchange();get('threadA').onclick();get('threadB').onclick();assert(get('threadB').disabled,'Blocked mutex thread');
for(let i=0;i<4;i++)get('threadA').onclick();assert(!get('threadB').disabled,'Unlock wakes waiting contender');
location.hash='#lab=overload&scenario=bounded';listeners.hashchange();
const rate=doc.querySelectorAll('[data-parameter]').find(e=>e.dataset.parameter==='rate');rate.value='12';rate.oninput();
assert(rate.parentElement.querySelector('output').textContent==='12','Live model parameter');
get('toggleEvents').onclick();assert(!get('labEvents').hidden,'Timeline toggle');
location.hash='#lab=ownership&scenario=shared';listeners.hashchange();get('openProgram').onclick();assert(get('programDialog').open,'Full source dialog');get('closeProgram').onclick();assert(!get('programDialog').open,'Close source');
assert(get('labScene').textContent.includes('Ещё не создан')&&!get('labScene').textContent.includes('Освобождён'),'Not created is not already freed');
assert(get('labScene').textContent.includes('Не объявлен'),'Do not present future pointer variables as already empty');
let shortcut=false;
doc.listeners.keydown({target:get('labCode'),key:'ArrowRight',preventDefault:()=>{shortcut=true;}});
assert(!shortcut&&Number(get('labRange').value)===0,'Arrow keys must scroll focused source instead of changing events');
doc.listeners.keydown({target:doc.body,key:'ArrowRight',preventDefault:()=>{shortcut=true;}});
assert(shortcut&&Number(get('labRange').value)===1,'Global step shortcut still works outside scrollable content');
shortcut=false;doc.listeners.keydown({target:get('labScene'),key:'ArrowRight',preventDefault:()=>{shortcut=true;}});
assert(!shortcut&&Number(get('labRange').value)===1,'Wide focused SVG must remain keyboard-scrollable');
const cycleButton=doc.querySelectorAll('[data-mode]').find(b=>b.dataset.mode==='cycle');cycleButton.focus();cycleButton.onclick();listeners.hashchange();
assert(doc.activeElement.dataset.mode==='cycle'&&doc.activeElement.getAttribute('aria-pressed')==='true','Mode switch preserves keyboard focus');
location.hash='#lab=ownership&scenario=shared';listeners.hashchange();
get('labRange').oninput({target:{value:8}});assert(get('labScene').textContent.includes('Освобождён'),'Control block released at the actual final event');
for(const mode of ['cycle','weak-cycle']){location.hash='#lab=ownership&scenario='+mode;listeners.hashchange();assert(!get('labScene').textContent.includes('уничтожен'),'Future nodes shown as destroyed');}
location.hash='#lab=network&scenario=retry';listeners.hashchange();assert(!get('labScene').innerHTML.includes('class="edge strong"'),'No exchange arrow before the first command');
get('labNext').onclick();assert(get('labScene').innerHTML.includes('class="edge strong"'),'Request arrow absent when actually sent');
location.hash='#lab=network&scenario=oversize';listeners.hashchange();assert(get('labScene').innerHTML.includes('prefix'),'Invalid length is still a length prefix');
location.hash='#lab=sql&scenario=where';listeners.hashchange();get('labRange').oninput({target:{value:3}});
assert(get('labScene').textContent.includes('owner_id')&&get('labScene').textContent.includes('Пары после WHERE'),'SQL displayed schema/stage must agree with query');
get('labPlay').onclick();location.hash='';listeners.hashchange();assert(timers.size===0&&doc.title==='Визуальные лаборатории · C++ / Backend','Catalog resets playback and document title');
const app=read('roadmap/assets/station-app.js');
const blockSource=app.slice(app.indexOf('  function LabBlock('),app.indexOf('  function SubstationNav('));
const navSource=app.slice(app.indexOf('  function SubstationNav('),app.indexOf('  function Theory('));
const h=(type,props,...children)=>({type,props:props||{},children:children.flat(Infinity)});
const walk=n=>n&&typeof n==='object'?[n,...(n.children||[]).flatMap(walk)]:[];
win.matchMedia=()=>({matches:true});let entries=0;
for(const item of win.COURSE_LABS)for(const entry of item.entries){
  const station=JSON.parse(read('roadmap/content/'+entry.station+'.json'));
  const section=station.theory.find(s=>s.id===entry.section),block=section.blocks.find(b=>b.type==='lab'&&b.lab===item.id);
  const makeBlock=new Function('h','meta','window',blockSource+';return LabBlock;')(h,station.meta,win);
  const href=win.courseLabHref(item.id,entry.scenario,entry.station,entry.section);
  assert(walk(makeBlock({block,section})).some(n=>n.type==='a'&&n.props.href===href),'Theory lab card '+entry.station);
  const makeNav=new Function('h','meta','theory','window','useState','isWorkbook',navSource+';return SubstationNav;')(
    h,station.meta,station.theory,win,initial=>[typeof initial==='function'?initial():initial,()=>{}],s=>/(?:-final-workbook|clock-worked-example)$/.test(s.id));
  const tree=makeNav({items:station.substations,active:section.substation,selected:section.id,view:'theory',store:{}});
  assert(walk(tree).some(n=>n.type==='a'&&n.props.className==='contents-lab-link'&&n.props.href===href),'Contents entry '+entry.station+'/'+entry.section);
  let hook=0;
  const searchNav=new Function('h','meta','theory','window','useState','isWorkbook',navSource+';return SubstationNav;')(
    h,station.meta,station.theory,win,initial=>[hook++===1?entry.title.toLocaleUpperCase('ru'):typeof initial==='function'?initial():initial,()=>{}],()=>false);
  const searchTree=searchNav({items:station.substations,active:'another-substation',selected:null,view:'theory',store:{}});
  assert(walk(searchTree).some(n=>n.type==='a'&&n.props.className==='contents-lab-link'&&n.props.href===href),'Find laboratory by title in course contents '+entry.station+'/'+entry.section);
  entries++;
}
const lifetimeScript=read('roadmap/object_lifetime_demo.html').match(/<script>\n([\s\S]*?)<\/script>/)[1];
for(const [from,hash,expectedModes] of [['station0','#exception',1],['station2','#inheritance',2],['station4','#dynamic',4]]){
  const page=createDOM('roadmap/object_lifetime_demo.html'),win={location:{search:'?from='+from,hash}};
  new Function('window','document','URLSearchParams','setInterval','clearInterval',lifetimeScript)(win,page,Params,()=>1,()=>{});
  const buttons=page.querySelectorAll('[data-scenario]');
  assert(buttons.filter(b=>!b.hidden).length===expectedModes,'Lifetime prerequisite profile '+from);
  assert(page.getElementById('returnToTheory').href.includes('#section='),'Lifetime exact course return');
  if(from==='station0')assert(!page.getElementById('fullSource').textContent.includes('throw '),'Exception implementation shown before exceptions');
  let prevented=false;
  page.listeners.keydown({target:page.getElementById('codeBody'),key:'ArrowRight',preventDefault:()=>{prevented=true;}});
  assert(!prevented,'Lifetime code must retain native keyboard scrolling');
  if(from==='station4'){
    const model=win.LifetimeDemo.makeScenario('dynamic');
    const destroyed=model.events.findIndex(e=>e.state.pointer==='destroyed');
    assert(destroyed>=0&&model.events[destroyed].state.storage==='allocated','Destruction precedes deallocation');
    assert(model.events.at(-2).state.pointer==='dangling'&&model.events.at(-1).state.pointer==='out-of-scope','Pointer variable lifetime differs from managed object lifetime');
    page.getElementById('stepRange').oninput({target:{value:model.events.length-1}});
    assert(page.getElementById('pointerStatus').textContent.includes('самого ptr завершилось'),'Final pointer state readable in UI');
  }
}
print('PASS: '+visited+' lab modes, every event rendered, navigation/timers, custom schedules, queue parameters, source dialog; '+entries+' theory/contents entries and 3 lifetime course profiles. DOM model only.');
