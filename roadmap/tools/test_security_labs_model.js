// Executes prepared model rules. It does not exercise TLS, DNS or a browser.
const read=p=>imports.byteArray.toString(imports.gi.GLib.file_get_contents(p)[1]);
const assert=(value,message)=>{if(!value)throw Error(message);};
const scope={};
new Function('globalThis','module',read('roadmap/assets/security-lab-models.js'))(scope,undefined);
const m=scope.SecurityLabs;
let count=0;
for(const [id,policy] of [['access','strict'],['outbound','every-hop'],['tls','verify']]) {
  for(const c of m.modules[id].cases) {
    const before=JSON.stringify(c),r=m.evaluate(id,c.id,policy);
    assert(r.correct,id+'/'+c.id+' strict result');
    assert(r.trace.length>0,id+'/'+c.id+' missing reasoning');
    assert(JSON.stringify(c)===before,'Fixture mutation '+id+'/'+c.id);
    count++;
  }
}
assert(m.evaluate('access','other','login_only').actual===true,'Reproduce missing ownership');
assert(m.evaluate('access','organization','owner_only').actual===true,'Reproduce cross-context omission');
assert(m.evaluate('access','extra-field','owner_only').actual===true,'Reproduce fields omission');
assert(JSON.stringify(m.evaluate('access','list','strict').actual)==='[41]','List scoped per row');
assert(JSON.stringify(m.evaluate('access','list','owner_only').actual)==='[41,43]','Weak list exposes context omission');
assert(m.evaluate('access','expired-list','strict').actual===false,'Expired list is request denial, not []');
assert(m.evaluate('outbound','redirect','initial-host-only').actual===true,'Reproduce redirect gap');
assert(m.evaluate('outbound','mixed','first-address').actual===true,'Reproduce first-address gap');
assert(m.evaluate('outbound','changed','first-address').actual===true,'Reproduce checked/selected gap');
assert(m.evaluate('outbound','wrong-port','initial-host-only').actual===true,'Reproduce name-only port gap');
assert(m.evaluate('tls','wrong-name','skip-name').actual===true,'Reproduce missing service identity');
assert(m.evaluate('tls','unknown-ca','insecure').actual===true,'Reproduce missing trust');
assert(m.evaluate('tls','expired','verify').actual===false,'Expired fixture denied');
assert(m.evaluate('tls','private-ca','verify').actual===true,'Explicit private trust is allowed');
assert(m.evaluate('tls','no-key','insecure').actual===false,'Disabling cert validation does not remove key possession');
for(const backend of ['plaintext','tls']) {
  const r=m.evaluate('tls','normal','verify',backend);
  assert(r.hops.length===2,'Two separate connections');
  assert(r.hops[0].encrypted===true&&r.hops[1].encrypted===(backend==='tls'),'Second hop independent');
}
const task=m.tasks[0],context={session_valid:true,user_id:7,tenant_id:10};
for(const fields of [[],['title','title'],['title','owner_id'],['owner_id']]) {
  assert(!m.accessDecision('strict',context,task,{action:'rename',fields}).allow,'rename requires exactly title');
}
const before=JSON.stringify([task,context]);
m.accessDecision('strict',context,task,{action:'get',fields:[]});
assert(before===JSON.stringify([task,context]),'Decision changes no task/context');
for(const id of Object.keys(m.modules)) {
  assert(m.modules[id].stages.length===5,'Five explained stages');
  for(const stage of m.modules[id].stages) {
    assert(stage.context.trim()&&stage.action.trim()&&stage.expectation.trim(),'Stage must explain task/action/expectation');
    assert(m.modules[id].cases.some(c=>c.id===stage.case),'Stage fixture exists');
  }
  for(const [policy] of m.modules[id].policies) {
    const checks=m.checks(id,policy);
    assert(checks.length===m.modules[id].cases.length,'Same contract cases for every policy');
  }
}
for(const args of [['unknown','normal','verify'],['access','missing','strict'],['tls','normal','missing']]) {
  let failed=false;try{m.evaluate(...args);}catch(_){failed=true;}assert(failed,'Invalid configuration rejected');
}
print('PASS: '+count+' strict fixture cases, weak-policy regressions, list/session boundary, address pinning, private trust/key proof, separate TLS hops; prepared models only.');
