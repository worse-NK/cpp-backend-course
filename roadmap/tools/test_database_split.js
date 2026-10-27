// Compatibility checks; no real browser or user storage.
const GLib=imports.gi.GLib, BA=imports.byteArray;
const read=p=>BA.toString(GLib.file_get_contents(p)[1]);
function assert(ok,m){if(!ok)throw new Error(m);}
const source=read('roadmap/assets/database-route.js');
class Params {constructor(s){this.s=s;}get(k){const x=this.s.split('&').find(p=>p.startsWith(k+'='));return x?decodeURIComponent(x.slice(k.length+1)):null;}}
function run(path,hash,storage){
 const listeners={};let destination='';
 new Function('location','localStorage','window','URLSearchParams',source)(
  {pathname:'/roadmap/'+path,hash,replace:s=>{destination=s;}},
  {getItem:k=>storage[k]||null,setItem:(k,v)=>{storage[k]=v;}},
  {addEventListener:(k,f)=>{listeners[k]=f;}},Params);
 return destination;
}
const sql=JSON.parse(read('roadmap/content/station9-sql.json'));
const pg=JSON.parse(read('roadmap/content/station9.json'));
const storage={'cpp_station9_progress_v1':JSON.stringify({'sec:tables':true,'sec:transactions':true,'station-final:sql-foundations:v1:basic':{score:25,total:25}})};
assert(run('cpp_station9_databases.html','#section=sql-null-basics',storage)==='cpp_station9_sql.html#section=sql-null-basics','Old deep link');
assert(run('cpp_station9_databases.html','#view=checkpoint&module=aggregation',storage).startsWith('cpp_station9_sql.html'),'Old checkpoint');
assert(!run('cpp_station9_databases.html','#section=transactions',storage),'PostgreSQL stays put');
run('cpp_station9_sql.html','',storage);
let migrated=JSON.parse(storage.cpp_station9_sql_progress_v1);
assert(migrated['sec:tables']&&!migrated['sec:transactions'],'Copy only SQL lessons');
assert(!Object.keys(migrated).some(k=>k.includes('final:')),'Do not reuse old exam score');
migrated['sec:tables']=false;storage.cpp_station9_sql_progress_v1=JSON.stringify(migrated);
run('cpp_station9_sql.html','',storage);
assert(JSON.parse(storage.cpp_station9_sql_progress_v1)['sec:tables']===false,'Migration must not overwrite subsequent progress');
assert(JSON.parse(storage.cpp_station9_progress_v1)['sec:tables'],'Do not delete old progress');
const sqlIDs=new Set(sql.theory.map(s=>s.id));
assert(!pg.theory.some(s=>sqlIDs.has(s.id)&&s.id!=='learning-route'),'No duplicated teaching sections');
for(const d of [sql,pg]){
 const ids=new Set(d.theory.map(s=>s.id));
 for(const item of Object.values(d.quizzes).flat().concat(d.tasks))for(const ref of item.theoryRefs)assert(ids.has(ref),'Missing reference '+ref);
}
print('PASS: split stations, legacy links, one-time progress migration, score isolation and theory references');
