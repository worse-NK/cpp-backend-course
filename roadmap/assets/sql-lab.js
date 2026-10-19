(function () {
  'use strict';
  const $=id=>document.getElementById(id), lab=window.SqlLab;
  let worker=null,timer=null,url=null,job=0;
  function current(){return lab.exercises.find(e=>e.id===$('exercise').value) || lab.exercises[0];}
  function status(text,kind){$('status').textContent=text;$('status').className=kind || '';}
  function table(result,title){
    const box=document.createElement('div');box.className='table-scroll';
    const t=document.createElement('table'),cap=document.createElement('caption');cap.textContent=title;t.append(cap);
    const head=document.createElement('thead'),hr=document.createElement('tr');
    (result.columns || []).forEach(c=>{const th=document.createElement('th');th.scope='col';th.textContent=c;hr.append(th);});head.append(hr);t.append(head);
    const body=document.createElement('tbody');
    (result.values || []).forEach(row=>{const tr=document.createElement('tr');row.forEach(v=>{const td=document.createElement('td');td.textContent=v===null?'NULL':String(v);if(v===null)td.className='null';tr.append(td);});body.append(tr);});t.append(body);box.append(t);
    if(!(result.values || []).length){const p=document.createElement('p');p.textContent=result.missing?'Таблица удалена или недоступна.':'0 строк';box.append(p);}
    if(result.truncated){const p=document.createElement('p');p.textContent='Показаны первые 200 строк. Для проверки решения сократи результат по условию.';box.append(p);}
    return box;
  }
  function cancel(){job++;clearTimeout(timer);if(worker)worker.terminate();worker=null;if(url)URL.revokeObjectURL(url);url=null;$('run').disabled=false;$('check').disabled=false;$('query').readOnly=false;$('stop').hidden=true;}
  function save(){try{localStorage.setItem('cpp-sql-lab:v1:'+current().id,$('query').value);}catch(_){}}
  function choose(){
    cancel();const e=current();$('task-title').textContent=e.title;$('task-prompt').textContent=e.prompt;
    const index=lab.exercises.indexOf(e);
    $('previous').disabled=index===0;$('next').disabled=index===lab.exercises.length-1;
    $('exercise-position').textContent=(index+1)+' / '+lab.exercises.length;
    $('theory-link').href='cpp_station9_sql.html#section='+e.section;
    $('hint-text').textContent=e.hint;$('solution').textContent=e.solution;$('explanation').textContent=e.hint;
    $('hint').open=false;$('answer').open=false;$('state').open=false;
    $('query').value='';try{$('query').value=localStorage.getItem('cpp-sql-lab:v1:'+e.id)||'';}catch(_){}
    $('results').textContent='Напиши запрос и нажми «Выполнить». Данные будут исходными.';$('state-tables').replaceChildren();
    status('Упражнение '+(lab.exercises.indexOf(e)+1)+' из '+lab.exercises.length+'. Таблицы восстановятся при каждом запуске.');
  }
  function run(mode){
    save();cancel();const id=job,query=$('query').value;
    if(!query.trim()){status('Сначала напиши SQL-запрос.','error');$('query').focus();return;}
    $('results').textContent='Ожидаем результат этого запуска…';$('state-tables').replaceChildren();$('state').open=false;
    try {
      url=URL.createObjectURL(new Blob([window.SQL_LAB_WORKER_SOURCE],{type:'text/javascript'}));worker=new Worker(url);
    } catch(error){cancel();status('Браузер не разрешил локальный SQL-worker. Попробуй открыть курс через локальный HTTP-сервер. Запрос сохранён.','error');return;}
    $('run').disabled=true;$('check').disabled=true;$('query').readOnly=true;$('stop').hidden=false;status('Запускаем изолированную учебную базу…');
    function timeout(){if(job!==id)return;cancel();status('Превышен лимит времени. Запрос остановлен, учебные данные сброшены. Упрости запрос или добавь ограничение результата.','error');}
    timer=setTimeout(timeout,10000);
    worker.onmessage=function(event){
      if(job!==id)return;const m=event.data;
      if(m.type==='ready'){clearTimeout(timer);timer=setTimeout(timeout,3000);status('Выполняем запрос…');return;}
      cancel();$('results').replaceChildren();
      if(m.type==='error'){status(m.hint,'error');const pre=document.createElement('pre');pre.textContent=m.message;$('results').append(pre);$('state-tables').replaceChildren();return;}
      m.results.forEach((r,i)=>$('results').append(table(r,'Результат '+(i+1))));
      if(!m.results.length)$('results').textContent='Команды выполнены без таблицы результата. Посмотри состояние данных ниже.';
      $('state-tables').replaceChildren(...m.state.map(r=>table(r,r.name)));$('state').open=current().kind==='state';
      status(m.verdict?m.verdict.reason:'Запрос выполнен. Это ещё не проверка задания.',m.verdict?(m.verdict.ok?'success':'error'):'');
    };
    worker.onerror=function(){if(job!==id)return;cancel();status('SQL-движок завершился с ошибкой. Данные не затронуты; попробуй меньший запрос или перезагрузи страницу.','error');};
    worker.postMessage({query,exerciseId:current().id,mode});
  }
  lab.exercises.forEach((e,i)=>{const o=document.createElement('option');o.value=e.id;o.textContent=String(i+1).padStart(2,'0')+' · '+e.title;$('exercise').append(o);});
  $('schema').textContent=lab.schema;
  $('seed-tables').append(table({columns:['id','name'],values:[[1,'Анна'],[2,'Борис'],[3,'Вера']]},'users'),table({columns:['id','owner_id','title','done','priority'],values:[[10,1,'Написать тест',0,3],[11,1,'Обновить README',1,null],[12,2,'Проверить API',0,1]]},'tasks'));
  function fromHash(){const id=location.hash.slice(1);$('exercise').value=lab.exercises.some(e=>e.id===id)?id:lab.exercises[0].id;choose();}
  function step(offset){const next=lab.exercises[lab.exercises.indexOf(current())+offset];if(next){save();location.hash=next.id;}}
  $('previous').addEventListener('click',()=>step(-1));$('next').addEventListener('click',()=>step(1));
  $('exercise').addEventListener('change',()=>{location.hash=$('exercise').value;});window.addEventListener('hashchange',fromHash);
  $('run').addEventListener('click',()=>run('run'));$('check').addEventListener('click',()=>run('check'));
  $('stop').addEventListener('click',()=>{cancel();status('Запрос остановлен. Следующий запуск начнётся с исходных таблиц.');});
  $('reset').addEventListener('click',()=>{cancel();$('query').value='';save();status('Черновик очищен.');$('query').focus();});
  $('query').addEventListener('input',save);$('query').addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();run('run');}});
  window.addEventListener('pagehide',cancel);fromHash();
})();
