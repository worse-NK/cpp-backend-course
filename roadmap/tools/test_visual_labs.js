// Model contracts; no browser, network service, or PostgreSQL server is imitated.
const GLib=imports.gi.GLib,BA=imports.byteArray;
const read=p=>BA.toString(GLib.file_get_contents(p)[1]);
function assert(v,m){if(!v)throw new Error(m);}
const window=globalThis;
(0,eval)(read('roadmap/generated/visual-labs.data.js'));
(0,eval)(read('roadmap/assets/visual-lab-models.js'));
const M=CourseLabModels;
let total=0;
for(const lab of COURSE_LABS){
  if(lab.id==='lifetime')continue;
  for(const mode of lab.scenarios){
    const model=M[lab.id](mode);
    assert(model.steps.length>=3,'Incomplete event sequence: '+lab.id+'/'+mode);
    for(const step of model.steps){assert(step.title&&step.text&&step.rule,'Missing explanation');assert(step.line>=0&&step.line<model.code.length,'Invalid highlighted line: '+lab.id+'/'+mode);}
    total++;
  }
}
for(const mode of ['separate','mutex','rmw']){
  const seen=new Set(),results=new Set(),limit=mode==='mutex'?5:mode==='rmw'?1:3;
  function visit(s){
    const key=JSON.stringify([s.value,s.locals,s.pc,s.lock]);if(seen.has(key))return;seen.add(key);
    if(s.pc.A===limit&&s.pc.B===limit){results.add(s.value);return;}
    for(const who of ['A','B']){const next=M.concurrencyStep(s,who,mode);if(next&&next.state.pc[who]>s.pc[who])visit(next.state);}
  }
  visit(M.concurrencyInitial());
  assert([...results].sort().join(',')===(mode==='separate'?'1,2':'2'),'Concurrent outcomes '+mode+': '+[...results]);
}
let partitions=0;
for(let bits=0;bits<64;bits++){
  const chunks=[];let length=1;
  for(let i=0;i<6;i++){if(bits&(1<<i)){chunks.push(length);length=1;}else length++;}chunks.push(length);
  const last=M.network('fragmented',{chunks}).steps.at(-1).state;
  assert(last.messages.join(',')==='ABC,DE'&&last.buffer.length===0&&last.expected===null,'Chunk boundary changed message');partitions++;
}
assert(M.network('oversize').steps.at(-1).state.rejected,'Oversize frame accepted');
const shared=M.ownership('shared').steps;
shared.forEach(e=>{assert(e.state.strong===e.state.owners.length,'Strong owner count');assert(!e.state.alive||e.state.strong>0,'Live object without owner');assert(e.state.owners.every(name=>e.state.declared.includes(name)),'Owner not yet declared');});
assert(!shared[0].state.created&&shared[0].state.declared.length===0,'Initial objects must not be confused with destroyed objects');
assert(shared.at(-2).state.control&&!shared.at(-2).state.alive,'Weak link must retain control block, not Item');
assert(!shared.at(-1).state.control,'Control block never released');
assert(M.ownership('cycle').steps.at(-1).state.aliveA,'Strong cycle silently collected');
assert(!M.ownership('weak-cycle').steps.at(-1).state.aliveA&&!M.ownership('weak-cycle').steps.at(-1).state.aliveB,'Weak cycle not released');
assert(M.vector('growth').steps.at(-1).state.pointer==='invalid','Reallocation access');
assert(M.vector('reserved').steps.at(-1).state.pointer==='valid','Reserved append access');
assert(M.vector('erase').steps.at(-1).state.pointer==='at-after-invalid','Erase invalidation');
for(const mode of ['left','where','count-star','inner']){
  const groups=M.sql(mode).steps.find(e=>e.state.stage==='groups');
  const vera=groups.state.rows.find(r=>r.id===3);
  if(mode==='where'||mode==='inner')assert(!vera&&groups.text.includes('отсутствующую группу'),'Missing user cannot acquire a zero group');
  else assert(vera.count===(mode==='left'?0:1),'Preserved LEFT JOIN group count');
}
for(const mode of ['commit','rollback']){
  const last=M.transactions(mode).steps.at(-1).state;assert(last.database===0&&last.winners===1,'Parking invariant '+mode);
}
const rechecked=M.transactions('commit').steps.at(-2).state;
assert(rechecked.lock==='B'&&rechecked.b===null&&rechecked.database===0,'Post-wait recheck can lock a row even when UPDATE changes zero rows');
assert(M.transactions('rc').steps.at(-1).state.a===110,'RC snapshot');
assert(M.transactions('rr').steps.at(-1).state.a===100,'RR snapshot');
assert(M.network('retry').steps.at(-1).state.count===2,'Retry must show duplicate effect');
assert(M.network('dedup').steps.at(-1).state.count===1,'Dedup changed effect twice');
assert(M.network('version').steps.at(-1).state.version===8,'Rejected update changed version');
let queues=0;
for(let rate=0;rate<=12;rate++)for(let workers=1;workers<=8;workers++)for(const queue of [0,1,8,20])for(const mode of ['bounded','drain']){
  const model=M.overload(mode,{rate,workers,queue});
  for(const {state:s} of model.steps){
    assert(s.accepted===s.completed+s.pending,'Work conservation');assert(s.arrived===s.accepted+s.rejected,'Admission conservation');assert(s.pending>=0&&s.pending<=queue,'Queue limit');
    if(s.phase!=='Serving')assert(s.lastAccepted===0,'Drain admitted new work');
  }queues++;
}
if(ARGV.includes('--json'))print(JSON.stringify(COURSE_LABS.filter(l=>l.id!=='lifetime').flatMap(l=>l.scenarios.map(mode=>({lab:l.id,mode,...M[l.id](mode)})))));
else print('PASS: '+total+' scenarios, all scheduler outcomes, '+partitions+' TCP partitions, ownership/vector/transaction invariants, '+queues+' queue configurations');
