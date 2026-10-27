// Execute the real bundled worker protocol without claiming browser coverage.
const GLib=imports.gi.GLib,BA=imports.byteArray;
const read=p=>BA.toString(GLib.file_get_contents(p)[1]);
const bundle={};new Function('window',read('roadmap/generated/sql-lab-worker.data.js'))(bundle);
function assert(value,message){if(!value)throw new Error(message);}
async function job(query,exerciseId,mode){
 const messages=[],self={postMessage:m=>messages.push(m)};
 new Function('self',bundle.SQL_LAB_WORKER_SOURCE)(self);
 await self.onmessage({data:{query,exerciseId,mode}});
 return messages;
}
(async()=>{
 let m=await job('SELECT id,title FROM tasks ORDER BY id','columns','check');
 assert(m[0].type==='ready','Readiness signal missing');
 assert(m.at(-1).type==='result'&&m.at(-1).verdict.ok,'Valid SQL rejected');
 m=await job('SELECT broken FROM tasks','columns','run');
 assert(m.at(-1).type==='error'&&m.at(-1).hint.includes('столбец'),'Error protocol');
 m=await job('UPDATE tasks SET done=true WHERE id=10','update','check');
 assert(m.at(-1).verdict.ok,'State check');
 m=await job('SELECT id FROM tasks WHERE id=900','columns','run');
 assert(m.at(-1).results[0].values.length===0,'Empty query result');
 m=await job('x'.repeat(16001),'columns','run');
 assert(m.length===1&&m[0].type==='error','Input limit');
 print('PASS: bundled SQL worker protocol: ready, result, checks, SQL errors, empty results and input limit');
})().catch(e=>{printerr(e.stack||e);imports.system.exit(1);});
