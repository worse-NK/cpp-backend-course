// Execute the actual vendored SQLite engine, not a SQL parser mock.
const GLib=imports.gi.GLib, ByteArray=imports.byteArray;
const read=p=>ByteArray.toString(GLib.file_get_contents(p)[1]);
const init=new Function(read('roadmap/vendor/sqljs/sql-asm.js')+';return initSqlJs;')();
new Function(read('roadmap/assets/sql-lab-core.js'))();
function assert(v,m){if(!v)throw new Error(m);}
init().then(SQL=>{
  for(const e of SqlLab.exercises){
    const result=SqlLab.check(SQL,e,e.solution);
    assert(result.ok,e.id+': '+result.reason);
    assert(!SqlLab.check(SQL,e,'SELECT 999999;').ok,'Wrong answer accepted: '+e.id);
  }
  const columns=SqlLab.exercises.find(e=>e.id==='columns');
  assert(SqlLab.check(SQL,columns,'select id, title from tasks order by id asc').ok,'Equivalent SQL rejected');
  assert(!SqlLab.check(SQL,columns,"SELECT 10, 'Написать тест' UNION ALL SELECT 11, 'Обновить README' UNION ALL SELECT 12, 'Проверить API';").ok,'Hardcoded fixture accepted');
  const db=SqlLab.seed(SQL,false);
  assert(SqlLab.execute(db,'SELECT id FROM tasks WHERE priority = NULL;')[0].values.length===0,'NULL comparison');
  assert(SqlLab.execute(db,'SELECT id FROM tasks WHERE priority IS NULL;')[0].values[0][0]===11,'IS NULL');
  assert(SqlLab.execute(db,"SELECT '<img src=x onerror=alert(1)>' AS value;")[0].values[0][0].startsWith('<img'),'SQL text must remain text');
  let failed=false;try{SqlLab.execute(db,"INSERT INTO tasks VALUES(90,999,'bad',0,1)");}catch(e){failed=true;assert(SqlLab.explainError(e.message).includes('владельца'),'FK error explanation');}assert(failed,'FK disabled');
  assert(SqlLab.execute(db,'SELECT id FROM tasks WHERE id=999;')[0].columns[0]==='id','Empty result metadata');
  const bounded=SqlLab.execute(db,'WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<500) SELECT x FROM n;')[0];
  assert(bounded.values.length===200 && bounded.truncated,'Unbounded display');
  db.close();
  print('PASS: '+SqlLab.exercises.length+' real SQLite exercises, alternate datasets, equivalent queries, NULL, FK, literal HTML, empty and bounded results');
}).catch(error=>{printerr(error.stack || error);imports.system.exit(1);});
