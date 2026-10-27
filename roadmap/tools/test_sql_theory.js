// Execute all new complete query listings with real SQLite and expected outputs.
const GLib=imports.gi.GLib,BA=imports.byteArray;
const read=p=>BA.toString(GLib.file_get_contents(p)[1]);
const data=JSON.parse(read('roadmap/content/station9-sql.json'));
new Function(read('roadmap/assets/sql-lab-core.js'))();
const init=new Function(read('roadmap/vendor/sqljs/sql-asm.js')+';return initSqlJs;')();
const expected={
 'sql-exists':[[[3,'Вера']]],
 'sql-cte-union':[[['Анна',2]],[[1],[1],[2]]],
 'sql-window-rank':[[[11,1,1],[10,1,2],[12,2,1]],[[11,1],[12,2]]],
 'sql-window-frame':[[[10,1,2,1],[11,1,2,2],[12,2,1,1]]],
 'sql-backend-boundaries':[[[12,'Проверить API']],null],
 'sql-report-final-workbook':[[[1,'Анна',1,10],[2,'Борис',1,12],[3,'Вера',0,null]]]
};
init().then(SQL=>{
 for(const [id,answers] of Object.entries(expected)){
  const snippets=data.theory.find(s=>s.id===id).blocks.filter(b=>b.type==='code');
  if(snippets.length!==answers.length)throw Error('Unverified listing '+id);
  snippets.forEach((b,i)=>{
   const db=SqlLab.seed(SQL,false);
   const result=SqlLab.execute(db,b.code);
   if(answers[i]!==null && JSON.stringify(result[0].values)!==JSON.stringify(answers[i]))throw Error('Wrong example output '+id+' '+i);
   if(answers[i]===null && SqlLab.execute(db,'SELECT name FROM users WHERE id=1')[0].values[0][0]!=='Анна Петрова')throw Error('UPSERT failed');
   db.close();
  });
 }
 print('PASS: 9 new SQL theory listings and stated results executed on SQLite');
}).catch(e=>{printerr(e.stack);imports.system.exit(1);});
