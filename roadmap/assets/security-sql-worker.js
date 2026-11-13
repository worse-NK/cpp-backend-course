/* Bundled with the local sql.js engine and security-sql-model.js. No imports,
 * network calls, live database, passwords or persistent storage are used.
 * The page owns cancellation by terminating this disposable Worker.
 */
(function (scope) {
  'use strict';
  let initialization = null, announced = false, busy = false;
  function message(error) {
    let text;
    try { text=String(error && error.message ? error.message : error); }
    catch (_) { text='Не удалось выполнить учебный запрос.'; }
    return text.length>200 ? text.slice(0,199)+'…' : text;
  }
  function validId(id) {
    return (typeof id==='number' && Number.isSafeInteger(id) && id>=0) ||
      (typeof id==='string' && id.length>0 && id.length<=64);
  }
  scope.onmessage = async function (event) {
    const data = event && event.data;
    const id = data && validId(data.id) ? data.id : null;
    if (!data || typeof data!=='object' || id===null ||
        !['run','checks'].includes(data.type) || !SecuritySQLDemo.modes.includes(data.mode)) {
      scope.postMessage({id,type:'error',message:'Неизвестная команда или способ построения запроса.'});
      return;
    }
    if (busy) {
      scope.postMessage({id,type:'error',message:'Этот Worker уже выполняет учебную команду.'});
      return;
    }
    busy = true;
    try {
      if (!initialization) initialization=Promise.resolve().then(() => initSqlJs());
      const SQL = await initialization;
      if (!announced) { announced=true; scope.postMessage({id,type:'ready'}); }
      if (data.type==='run') {
        scope.postMessage({id,type:'result',result:SecuritySQLDemo.execute(SQL,data.term,data.mode)});
      } else {
        scope.postMessage({id,type:'checks',checks:SecuritySQLDemo.runChecks(SQL,data.mode)});
      }
    } catch (error) { scope.postMessage({id,type:'error',message:message(error)}); }
    finally { busy=false; }
  };
})(self);
