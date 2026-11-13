// Actual vendored SQLite, plus explicit API/protocol boundary fault injection.
// Run from repo root: gjs roadmap/tools/test_security_sql_model.js
// Also supports node roadmap/tools/test_security_sql_model.js when Node exists.
(function () {
  'use strict';
  const node = typeof process==='object' && process.versions && process.versions.node;
  const read = node ? p=>require('fs').readFileSync(p,'utf8') :
    p=>imports.byteArray.toString(imports.gi.GLib.file_get_contents(p)[1]);
  const log = node ? value=>console.log(value) : value=>print(value);
  function assert(value, message) { if (!value) throw new Error(message); }
  function equal(a,b,message) { assert(JSON.stringify(a)===JSON.stringify(b),message); }
  const modelSource = read('roadmap/assets/security-sql-model.js');
  const moduleMock = {exports:{}}, globalMock = {};
  new Function('globalThis','module',modelSource)(globalMock,moduleMock);
  const model = moduleMock.exports;
  assert(globalMock.SecuritySQLDemo===model, 'UMD global/export mismatch');
  assert(Object.isFrozen(model.fixture) && model.fixture.length===6, 'Fixture contract');
  assert(model.byteLength('RAII')===4 && model.byteLength('я')===2 &&
    model.byteLength('🙂')===4 && model.byteLength('\uD800')===3 &&
    model.byteLength('\uDC00')===3 && model.byteLength('\uD800A')===4, 'UTF8 byte counting');
  if (typeof TextEncoder==='function') {
    for (const term of ['a','я','🙂','\uD800','\uDC00','\uD800A','🙂яa'])
      assert(model.byteLength(term)===new TextEncoder().encode(term).length, 'TextEncoder agreement');
  }
  assert(!model.buildQuery('a'.repeat(120),'bind').rejected, 'Exact ASCII byte boundary rejected');
  assert(!model.buildQuery('я'.repeat(60),'bind').rejected, 'Exact Unicode byte boundary rejected');
  assert(!model.buildQuery('🙂'.repeat(30),'bind').rejected, 'Exact astral boundary rejected');
  for (const term of ['a'.repeat(121),'я'.repeat(61),'🙂'.repeat(31),'a\0b','\uD800',null,42,{}])
    assert(model.buildQuery(term,'bind').rejected,'Invalid term accepted');
  assert(model.buildQuery('RAII','unknown').rejected,'Unknown mode accepted');
  assert(model.buildQuery("O'Reilly",'filter').rejected, 'Flawed blacklist did not reject apostrophe');
  assert(model.buildQuery('O’Reilly','filter').rejected===false, 'Blacklist must be exactly ASCII apostrophe');
  const bound = model.buildQuery("' OR 1=1 --",'bind');
  assert(bound.sql===model.sqlTemplate && !bound.sql.includes('OR 1=1'), 'Parameter entered SQL text');
  equal(bound.params, {$term:"' OR 1=1 --"}, 'Parameter value lost');

  const init = node ? require('../vendor/sqljs/sql-asm.js') :
    new Function(read('roadmap/vendor/sqljs/sql-asm.js')+';return initSqlJs;')();
  (async function () {
    const SQL = await init();
    const ordinary = model.execute(SQL,'RAII','concat');
    equal(ordinary.rows,[{id:1,title:'RAII',is_public:1}],'Ordinary real SELECT');
    assert(ordinary.error===null && /^\d+\.\d+\.\d+$/.test(ordinary.engineVersion),'Real engine version');
    for (const mode of model.modes) {
      equal(model.execute(SQL,'Нет такого урока',mode).rows,[],'Missing exact match');
      equal(model.execute(SQL,'Черновик A',mode).rows,[],'Direct private title lookup');
      assert(model.execute(SQL,'RAII%',mode).rows.length===0,'Equality silently changed to LIKE');
    }
    const apostrophe = model.execute(SQL,"O'Reilly",'concat');
    assert(apostrophe.error && apostrophe.rows.length===0,'SQL syntax error was fabricated/hidden');
    equal(model.execute(SQL,"O'Reilly",'bind').rows,[{id:3,title:"O'Reilly",is_public:1}], 'Bound apostrophe failed');
    const leaked = model.execute(SQL,"' OR 1=1 --",'concat');
    assert(leaked.error===null && leaked.rows.length===6 && leaked.rows.some(r=>r.is_public===0), 'Real concat injection did not reveal synthetic drafts');
    equal(model.execute(SQL,"' OR 1=1 --",'bind').rows,[],'Bound value changed predicate');
    for (const [mode,passes] of [['concat',2],['filter',2],['bind',4]]) {
      const checks = model.runChecks(SQL,mode);
      assert(checks.length===4 && checks.filter(c=>c.passed).length===passes,'Contract check verdict '+mode);
      assert(checks.every(c=>typeof c.label==='string' && Array.isArray(c.expectedRows)),'Check metadata');
      assert(checks.find(c=>c.id==='injection').unexpectedPrivate===(mode==='concat'),'Private result flag '+mode);
    }

    // Observe real DB lifetime and guard behavior without replacing SQL parsing.
    const track = {opened:0,closed:0,active:0,readonlyChecks:0};
    const trackedSQL = {Database:function () {
      const db = new SQL.Database(); track.opened++;
      const prepare = db.prepare.bind(db), close = db.close.bind(db);
      db.prepare = function (sql,params) {
        const stmt = prepare(sql,params), free = stmt.free.bind(stmt);
        track.active++; let released=false;
        stmt.free = function () {
          assert(!released,'Statement freed twice'); released=true; track.active--;
          return free();
        };
        return stmt;
      };
      db.close = function () {
        assert(track.active===0,'Prepared statement leaked to db.close');
        assert(db.exec('PRAGMA query_only;')[0].values[0][0]===1,'query_only guard missing');
        const heap = db.exec('PRAGMA hard_heap_limit;')[0].values[0][0];
        assert(heap>0 && heap<=model.limits.sqliteHeapBytes,'SQLite allocation budget missing');
        let refused=false;
        try { db.run("UPDATE lessons SET title='changed';"); }
        catch (error) { refused=/readonly|read.only/i.test(String(error)); }
        assert(refused,'Actual readonly update was not refused'); track.readonlyChecks++;
        assert(db.exec('SELECT COUNT(*) FROM lessons;')[0].values[0][0]===6,'Fixture mutated');
        track.closed++; return close();
      };
      return db;
    }};
    assert(!model.execute(trackedSQL,'RAII','bind').error,'Tracked normal query');
    assert(model.execute(trackedSQL,"O'Reilly",'concat').error,'Tracked syntax failure');
    assert(!model.execute(trackedSQL,"RAII'; DROP TABLE lessons;--",'concat').error,'One-statement boundary');
    assert(track.opened===3 && track.closed===3 && track.active===0 && track.readonlyChecks===3,'Real resource cleanup');

    const copied = model.execute(SQL,'TCP','bind');
    copied.allRows[0].title='modified outside'; copied.rows[0].title='changed outside';
    equal(model.execute(SQL,'RAII','bind').rows,[{id:1,title:'RAII',is_public:1}],'State shared between runs');
    assert(model.fixture[0].title==='RAII','Exported fixture mutated');
    const manyTerm="' OR 1=1 UNION ALL SELECT * FROM lessons UNION ALL SELECT * FROM lessons UNION ALL SELECT * FROM lessons --";
    assert(model.byteLength(manyTerm)<=120,'Bounded-row test input too long');
    const many = model.execute(SQL,manyTerm,'concat');
    assert(!many.error && many.rows.length===20 && many.truncated,'Returned rows not capped at20');
    const longCell = model.execute(SQL,"' UNION SELECT 99, printf('%0500d',0), 1 --",'concat');
    assert(!longCell.error && longCell.truncated && longCell.rows.every(r=>typeof r.title!=='string'||r.title.length<=200),'Cell output not capped');
    const blob = model.execute(SQL,"' UNION SELECT 99, x'010203', 1 --",'concat');
    assert(!blob.error && blob.rows[0].title.startsWith('BLOB'),'Blob display bound');
    const overBudget = model.execute(SQL,"' UNION SELECT 99, randomblob(20000000), 1 --",'concat');
    assert(overBudget.error && /memory/i.test(overBudget.error), 'SQLite allocation budget was not enforced');
    equal(model.execute(SQL,'RAII','bind').rows,[{id:1,title:'RAII',is_public:1}],
      'Allocation failure poisoned a later fresh run');
    const failedInit = model.execute({Database:function(){throw new Error('x'.repeat(500));}},'RAII','bind');
    assert(failedInit.error.length===200,'Diagnostics not capped at200');
    assert(model.execute(null,'RAII','bind').error,'Missing engine not structured');

    // The real bundle/protocol runs as a function here. Browser lifecycle and
    // cancellation need separate UI checks; this is not a browser-worker test.
    const bundle = {};
    new Function('window',read('roadmap/generated/security-sql-worker.data.js'))(bundle);
    const messages=[], scope={postMessage:value=>messages.push(value)};
    new Function('self',bundle.SECURITY_SQL_WORKER_SOURCE)(scope);
    await scope.onmessage({data:{id:1,type:'run',term:'RAII',mode:'bind'}});
    assert(messages[0].type==='ready' && messages[0].id===1,'Worker readiness boundary');
    assert(messages.at(-1).type==='result' && messages.at(-1).result.rows[0].title==='RAII','Worker real result');
    await scope.onmessage({data:{id:2,type:'checks',mode:'bind'}});
    assert(messages.at(-1).type==='checks' && messages.at(-1).checks.every(c=>c.passed),'Worker checks');
    assert(messages.filter(m=>m.type==='ready').length===1,'Readiness repeated for a reused worker');
    await scope.onmessage({data:{id:3,type:'run',mode:'bind',term:'x'.repeat(121)}});
    assert(messages.at(-1).result.query.rejected,'Worker input boundary');
    await scope.onmessage({data:{id:4,type:'run',mode:'concat',term:"O'Reilly"}});
    assert(messages.at(-1).type==='result' && messages.at(-1).result.error,'SQL syntax error protocol');
    await scope.onmessage({data:{id:5,type:'unknown',mode:'bind'}});
    assert(messages.at(-1).type==='error' && messages.at(-1).id===5,'Unknown command protocol');
    await scope.onmessage({data:{id:6,type:'run',mode:'bind',term:'TCP',sql:'DROP TABLE lessons;'}});
    assert(messages.at(-1).result.rows[0].title==='TCP','Extra arbitrary SQL field executed');
    log('PASS: real SQLite '+ordinary.engineVersion+'; three strategies,12 contract checks, UTF8/input bounds, readonly/fresh fixtures, statements/DB cleanup,20-row/200-cell limits, UMD and real bundled worker protocol');
  })().catch(error => {
    if (node) { console.error(error.stack||error); process.exitCode=1; }
    else { printerr(error.stack||error); imports.system.exit(1); }
  });
})();
