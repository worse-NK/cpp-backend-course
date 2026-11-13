// Controller with a DOM model: structural/interaction QA, never pixel/browser QA.
const read=p=>imports.byteArray.toString(imports.gi.GLib.file_get_contents(p)[1]);
const assert=(v,m)=>{if(!v)throw Error(m);};
const helper=read('roadmap/tools/test_visual_labs_ui.js');
const createDOM=new Function('read',helper.slice(helper.indexOf('function createDOM('),helper.indexOf('const doc=createDOM()'))+';return createDOM;')(read);
function environment(hash='') {
  const doc=createDOM('roadmap/security_labs.html'),proto=Object.getPrototypeOf(doc.body);
  Object.defineProperty(proto,'id',{configurable:true,get(){return this.attrs.id||'';},set(v){this.attrs.id=String(v);}});
  Object.defineProperty(proto,'className',{configurable:true,get(){return this.attrs.class||'';},set(v){this.attrs.class=String(v);}});
  proto.clear=function(){for(const n of this.nodes)if(typeof n!=='string')n.parentElement=null;this.nodes=[];};
  proto.append=function(...nodes){for(const node of nodes){if(typeof node!=='string')node.parentElement=this;this.nodes.push(node);}};
  proto.replaceChildren=function(...nodes){this.clear();this.append(...nodes);};
  doc.createElement=tag=>new proto.constructor(tag);
  doc.createTextNode=value=>String(value);
  doc.getElementById=id=>doc.querySelectorAll('[id]').find(n=>n.id===id)||null;
  const listeners={},window={location:{hash},addEventListener:(key,f)=>listeners[key]=f};
  window.history={replaceState:(_a,_b,value)=>{window.location.hash=value;}};
  new Function('window',read('roadmap/generated/visual-labs.data.js'))(window);
  new Function('globalThis','module',read('roadmap/assets/security-lab-models.js'))(window,undefined);
  doc.getElementById('backend').value='plaintext';
  new Function('window','document',read('roadmap/assets/security-labs.js'))(window,doc);
  const get=id=>{const n=doc.getElementById(id);assert(n,'Missing id '+id);return n;};
  function action(id,type='click') {const n=get(id);n.listeners[type]({preventDefault(){},target:n,currentTarget:n});}
  return {doc,window,listeners,get,action};
}
let visited=0;
for(const module of ['access','outbound','tls']) {
  const e=environment('#lab=security&scenario='+module);
  const lesson=e.window.SecurityLabs.modules[module];
  assert(e.get('context').children.length===lesson.context.length,'Every introductory paragraph is rendered '+module);
  lesson.context.forEach((paragraph,i)=>assert(e.get('context').children[i].textContent===paragraph,'Unabridged introduction '+module));
  assert(e.get('experiment-goal').textContent===lesson.goal,'Specific experiment goal '+module);
  assert(e.get('policy-label').textContent===lesson.policyLabel,'Control is explained for this scenario '+module);
  const sequence=e.doc.querySelectorAll('[id]');
  assert(sequence.indexOf(e.get('context'))<sequence.indexOf(e.get('experiment'))&&
         sequence.indexOf(e.get('experiment-goal'))<sequence.indexOf(e.get('experiment')),
         'Situation and goal precede experimental controls '+module);
  assert(e.get('fixture-table').querySelectorAll('tbody').length===1,'Visible data '+module);
  assert(!e.get('run').disabled,'Runnable '+module);
  for(let i=0;i<5;i++) {
    e.action('step-'+i);
    assert(e.get('step-'+i).getAttribute('aria-current')==='step','Current stage');
    assert(e.doc.activeElement===e.get('guide-title'),'Stage focus for keyboard user');
    assert(e.get('guide-action').textContent&&e.get('guide-expectation').textContent,'Visible task and comparison');
    assert(e.get('trace').children.length===0,'No stale trace after stage change');
    e.action('model-form','submit');
    assert(e.get('trace').children.length>0,'Actual decision trace');
    assert(e.get('result').textContent.length>100,'Result explanation');
    visited++;
  }
  assert(!e.get('checks-section').hidden,'Checks at final stage');
  e.action('check');
  assert(e.get('checks-summary').textContent.includes('совпало'),'Explicit scoped check result');
  const expected=e.window.SecurityLabs.modules[module].cases.length;
  assert(e.get('checks-results').children.length===expected,'All contract cases listed');
  e.get('case').value=e.window.SecurityLabs.modules[module].cases[0].id;e.action('case','change');
  assert(e.get('trace').children.length===0&&e.get('checks-results').children.length===0,'Changed setting clears observations');
  e.action('reset');assert(e.get('previous').disabled,'Start boundary');assert(!e.get('next').disabled,'Next enabled');
}
const e=environment('#scenario=access&from=station15&section=access-laboratory&step=1');
assert(e.get('theory-link').getAttribute('href')==='cpp_station15_security.html#section=access-laboratory&fromLab=security','Exact approved theory return with reader context');
e.action('model-form','submit');assert(e.get('result').textContent.includes('Не совпало'),'Weak policy violation visible');
e.action('lab-tls');assert(e.get('theory-link').getAttribute('href')==='cpp_station15_security.html#section=transport-laboratory&fromLab=security','Switch updates the exact approved theory topic');
assert(e.doc.activeElement===e.get('title'),'Switching topic starts at the new introduction, not below it');
e.action('model-form','submit');assert(e.get('hops').children.length===2,'TLS renders two separate connections');
e.get('backend').value='tls';e.action('backend','change');e.action('model-form','submit');
assert(e.get('hops').textContent.includes('отдельное'),'Second-hop assumption visible');
const invalid=environment('#scenario=%ZZ&from=javascript%3Aalert(1)&section=missing&step=99');
assert(invalid.get('theory-link').getAttribute('href')==='cpp_station15_security.html#section=access-laboratory&fromLab=security','Untrusted context cannot become URL');
assert(invalid.get('step-0').getAttribute('aria-current')==='step','Malformed route defaults');
assert(!/innerHTML|\beval\s*\(|\bfetch\s*\(|XMLHttpRequest|WebSocket/.test(read('roadmap/assets/security-labs.js')),'No HTML evaluation or networking');
print('PASS: '+visited+' guided stages, visible task/data/expectations, results/trace, full-case checks, state invalidation, keyboard focus, return-link allowlist. DOM model only; visual browser QA not performed.');
