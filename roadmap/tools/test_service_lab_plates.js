/* Run from the repository root: gjs roadmap/tools/test_service_lab_plates.js */
const GLib = imports.gi.GLib, BA=imports.byteArray;
const read = p => BA.toString(GLib.file_get_contents('roadmap/assets/'+p+'.js')[1]);
(0,eval)(read('visual-lab-models')); (0,eval)(read('lab-service-plates'));
const M=globalThis.CourseLabModels, P=globalThis.CourseServicePlates;
const assert = (ok,what) => {if(!ok)throw new Error(what);};
const modes = {concurrency:['separate','mutex','rmw'],network:['fragmented','combined','oversize','retry','dedup','version'],
               transactions:['rc','rr','commit','rollback'],overload:['bounded','drain']};
const draw = (id,mode,t,i) => P.render(id,mode,t.steps[i].state,t,i);
let count=0;
for(const [id,items] of Object.entries(modes))for(const mode of items){
  const t=M[id](mode);
  t.steps.forEach((entry,i)=>{
    const h=draw(id,mode,t,i), s=entry.state;count++;
    assert(/^<figure /.test(h)&&!/(undefined|NaN|<script| style=| on[a-z]+=)/.test(h),id+':'+mode+':'+i);
    // Access to future steps is unnecessary, including after a hand-built schedule.
    assert(h===draw(id,mode,{steps:t.steps.slice(0,i+1)},i),'Future leak '+id+':'+mode+':'+i);
    if(id==='network'&&!s.api){
      const segmentSizes=k=>Array.from(h.matchAll(new RegExp('svc-brace svc-'+k+'" data-size="(\\d+)"','g')),m=>Number(m[1]));
      assert(segmentSizes('read').reduce((a,b)=>a+b,0)===s.received,'Unread bytes shown as received');
      assert(segmentSizes('record').reduce((a,b)=>a+b,0)===s.messages.reduce((a,m)=>a+1+m.length,0),'Message boundaries');
      assert((h.match(/svc-buffer"/g)||[]).length===s.buffer.length,'Buffer view');
    }
    if(id==='concurrency')assert((h.match(/class="svc-beat"/g)||[]).length===Math.min(i,4),'Thread window');
    if(id==='overload')assert((h.match(/class="svc-shutdown"/g)||[]).length===(mode==='drain'&&s.time>=7?2:0),'Drain limit');
  });
}
const at=(id,mode,i)=>{const t=M[id](mode);return draw(id,mode,t,i<0?t.steps.length+i:i);};
assert(!at('network','retry',0).includes('class="edge strong"')&&at('network','retry',1).includes('class="edge strong"'),'Traffic only on exchange');
assert(at('network','retry',3).includes('svc-clock')&&(at('network','retry',3).match(/svc-to-lost/g)||[]).length===1,'A timeout is not another lost answer');
assert(at('network','dedup',-1).includes('Одна задача 42')&&at('network','retry',-1).includes('Созданы задачи 42 и 43'),'Distinct retry effects');
assert(at('transactions','rr',3).includes('Второй SELECT</b><strong>100')&&at('transactions','rc',3).includes('Второй SELECT</b><strong>110'),'Second read');
assert(at('transactions','rollback',3).includes('блокировка снята')&&at('transactions','commit',2).includes('Ждёт завершения A'),'Waiting vs. released');
const t=M.concurrency('separate');t.steps=t.steps.slice(0,1);
for(const who of ['A','A','A','B','B','B'])t.steps.push(M.concurrencyStep(t.steps.at(-1).state,who,'separate'));
assert(!draw('concurrency','separate',t,t.steps.length-1).includes('Оба потока записали единицу'),'Serial schedule does not lose an increment');
for(const params of [{rate:0,workers:8,queue:0},{rate:12,workers:1,queue:20}]){
 const t=M.overload('drain',params), i=t.steps.length-1, h=draw('overload','drain',t,i);
 assert(!h.includes('NaN')&&h.includes('от 0 до '+Math.max(params.rate,params.queue,1)),'Load scale at bounds');
}
assert(P.render('unrelated','',{},null,0)==='','Unknown plate');
print('PASS: '+count+' rendered service snapshots, 15 scenarios, history/semantics, boundary parameters and a custom schedule.');
