// Controller checks with a small DOM/Worker model; not a browser visual test.
const GLib=imports.gi.GLib,BA=imports.byteArray;
const read=p=>BA.toString(GLib.file_get_contents(p)[1]);
function assert(v,m){if(!v)throw new Error(m);}
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.listeners={};this.value='';this.hidden=false;this.open=false;this.disabled=false;this._text='';}
  set textContent(v){this._text=String(v);this.children=[];}
  get textContent(){return this._text+this.children.map(x=>x.textContent).join('');}
  append(...xs){this.children.push(...xs);if(this.tag==='select'&&!this.value&&xs.length)this.value=xs[0].value;}
  replaceChildren(...xs){this._text='';this.children=xs;}
  addEventListener(k,fn){this.listeners[k]=fn;}
  focus(){this.focused=true;}
}
const ids='exercise previous next exercise-position task-title task-prompt theory-link hint-text solution explanation hint answer state query results state-tables status run check stop reset schema seed-tables'.split(' ');
const nodes={};ids.forEach(id=>nodes[id]=new Element(id==='exercise'?'select':'div'));
const storage=new Map(),listeners={},timers=new Map(),workers=[];let timerID=0,revoked=0;
const win={SQL_LAB_WORKER_SOURCE:'test-worker',addEventListener:(k,f)=>listeners[k]=f};
new Function('globalThis',read('roadmap/assets/sql-lab-core.js'))(win);
const location={hash:'#columns'};
class Worker {constructor(){workers.push(this);}postMessage(m){this.message=m;}terminate(){this.terminated=true;}}
new Function('window','document','localStorage','location','URL','Blob','Worker','setTimeout','clearTimeout',read('roadmap/assets/sql-lab.js'))(
 win,{getElementById:id=>nodes[id],createElement:tag=>new Element(tag)},
 {getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},location,
 {createObjectURL:()=> 'blob:test',revokeObjectURL:()=>revoked++},class {},Worker,
 (f,ms)=>{timers.set(++timerID,{f,ms});return timerID;},id=>timers.delete(id));
assert(nodes.exercise.value==='columns','Deep link selection');
assert(nodes.exercise.children.length===20,'Exercise options');
nodes.query.value='SELECT id,title FROM tasks ORDER BY id;';nodes.query.listeners.input();
assert(storage.get('cpp-sql-lab:v1:columns')===nodes.query.value,'Draft not saved');
nodes.run.listeners.click();let w=workers.at(-1);
assert(w.message.mode==='run'&&nodes.run.disabled&&!nodes.stop.hidden,'Running controls');
assert(nodes.query.readOnly,'Query must remain consistent with the in-flight check');
w.onmessage({data:{type:'ready'}});assert([...timers.values()][0].ms===3000,'Execution timeout not armed');
w.onmessage({data:{type:'result',results:[{columns:['title'],values:[['<script>bad()</script>']]}],state:[],verdict:null}});
assert(nodes.results.textContent.includes('<script>bad()</script>'),'Literal cell value');
assert(!nodes.run.disabled&&nodes.stop.hidden&&w.terminated,'Worker cleanup');
assert(!nodes.query.readOnly,'Editor not restored');
assert(nodes.status.textContent.includes('ещё не проверка'),'Run must not claim passing');
nodes.check.listeners.click();w=workers.at(-1);assert(w.message.mode==='check','Check action');
nodes.stop.listeners.click();assert(w.terminated&&!nodes.run.disabled,'Stop cleanup');
w.onmessage({data:{type:'result',results:[],state:[],verdict:{ok:true,reason:'STALE'}}});
assert(!nodes.status.textContent.includes('STALE'),'Cancelled result leaked');
nodes.check.listeners.click();w=workers.at(-1);
w.onmessage({data:{type:'error',message:'near FROM: syntax error',hint:'Проверь запятую'}});
assert(nodes.status.className==='error'&&nodes.results.textContent.includes('syntax error'),'Engine error output');
nodes.run.listeners.click();[...timers.values()][0].f();
assert(nodes.status.textContent.includes('лимит')&&!nodes.run.disabled,'Timeout recovery');
location.hash='#null';listeners.hashchange();assert(nodes.query.value==='','Exercise isolation');
location.hash='#columns';listeners.hashchange();assert(nodes.query.value.startsWith('SELECT'),'Draft restoration');
nodes.reset.listeners.click();assert(nodes.query.value===''&&nodes.query.focused,'Reset');
assert(revoked>=4,'Blob URLs leaked');
nodes.query.value='SELECT title FROM tasks;';
nodes.next.listeners.click();assert(location.hash==='filter','Next exercise address');
location.hash='#filter';listeners.hashchange();
assert(nodes.exercise.value==='filter'&&nodes.query.value==='','Next exercise must have its own draft');
assert(nodes['theory-link'].href.endsWith('#section=sql-filter-basics'),'Matching theory link');
nodes.previous.listeners.click();location.hash='#columns';listeners.hashchange();
assert(nodes.query.value==='SELECT title FROM tasks;','Step navigation must save the draft');
location.hash='';listeners.hashchange();
assert(nodes.exercise.value==='expression'&&nodes.previous.disabled&&!nodes.next.disabled,'Empty address must select first exercise');
location.hash='#report';listeners.hashchange();assert(nodes.next.disabled&&!nodes.previous.disabled,'Last exercise boundary');
assert(nodes['exercise-position'].textContent==='20 / 20','Position label');
location.hash='#unknown';listeners.hashchange();assert(nodes.exercise.value==='expression','Invalid address fallback');
print('PASS: SQL trainer controller: deep links, drafts, execute/check, cancel, stale messages, timeout, errors, literal text and cleanup');
