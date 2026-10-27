/* Bundled with sql.js and sql-lab-core.js; run in a disposable Web Worker. */
self.onmessage = async function (event) {
  let db;
  try {
    const {query,exerciseId,mode}=event.data;
    if(typeof query!=='string' || !query.trim() || query.length>16000)
      throw new Error('Введите запрос длиной от 1 до 16000 символов.');
    const exercise=SqlLab.exercises.find(e=>e.id===exerciseId);
    if(!exercise) throw new Error('Неизвестное упражнение.');
    const SQL=await initSqlJs();
    self.postMessage({type:'ready'});
    db=SqlLab.seed(SQL,false);
    const results=SqlLab.execute(db,query);
    const state=SqlLab.snapshot(db);
    const verdict=mode==='check' ? SqlLab.check(SQL,exercise,query) : null;
    self.postMessage({type:'result',results,state,verdict});
  } catch(error) {
    self.postMessage({type:'error',message:String(error.message || error),hint:SqlLab.explainError(String(error.message || error))});
  } finally {if(db)db.close();}
};
