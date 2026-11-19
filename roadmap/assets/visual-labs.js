(function () {
  "use strict";
  const $=id=>document.getElementById(id),catalog=window.COURSE_LABS,M=window.CourseLabModels;
  const root=$("labRoot");
  if(!catalog||!M){root.textContent="Не загружены локальные файлы лабораторий. Открой страницу из каталога roadmap целиком.";return;}
  const esc=value=>String(value??"—").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const modeNames={unique:"Передать unique_ptr",shared:"shared_ptr и weak_ptr",cycle:"Сильный цикл","weak-cycle":"Слабая обратная связь",growth:"Буфер заполнен",reserved:"Есть запас",erase:"Удалить элемент",header:"Изменён заголовок",source:"Изменён .cpp",readme:"Изменён README",separate:"Раздельные load/store",mutex:"Один mutex на всю операцию",rmw:"Один fetch_add",fragmented:"Порции 1 + 2 + 1 + 3",combined:"Все байты сразу",oversize:"Недопустимая длина",retry:"Повтор без ключа",dedup:"Повтор с ключом",version:"Устаревший If-Match",left:"LEFT JOIN · условие в ON",where:"Условие перенесли в WHERE","count-star":"Заменили COUNT на COUNT(*)",inner:"INNER JOIN",commit:"A фиксирует место",rollback:"A откатывается",rc:"Снимки Read Committed",rr:"Снимок Repeatable Read",bounded:"Приём с ограничением",drain:"Закрыть приём на 7-м такте"};
  Object.assign(modeNames,{routed:"Маршрут без NAT",snat:"SNAT и обратный ответ",filtered:"Drop в forward",pmtu6:"IPv6 · MTU и PTB"});
  Object.assign(modeNames,{cxx20:"Временный · C++20",cxx23:"Временный · C++23",named:"Именованный · обе версии",parameter:"Ссылка на параметр · C++23","run-task":"Выполнить задачу","discard-task":"Удалить без выполнения"});
  let lab=null,mode="",context=null,model=null,cursor=0,timer=null,parameters={rate:8,workers:4,queue:8};
  function stationName(id){return id==="station7-netlab"?"7Б":id==="station9-sql"?"9A":id==="station9"?"9B":id.replace("station","");}
  function entryHref(item,e){return window.courseLabHref(item.id,e.scenario,e.station,e.section);}
  function introduction(item,scenario){
    const intro=item.introduction;
    if(!intro)return "";
    const variant=item.scenarioNotes&&item.scenarioNotes[scenario];
    return '<section class="lab-primer" id="labIntroduction" aria-labelledby="labIntroductionHeading">'+
      '<h2 id="labIntroductionHeading">Что будем разбирать</h2>'+
      '<div class="lab-primer-copy">'+intro.paragraphs.map(text=>'<p>'+esc(text)+'</p>').join("")+'</div>'+
      (variant?'<p class="lab-primer-scenario" id="labScenarioNote">'+esc(variant)+'</p>':"")+
      '<div class="lab-primer-instructions"><p><strong>Что выясняем.</strong> '+esc(intro.goal)+'</p>'+
      '<p><strong>С чего начать.</strong> '+esc(intro.action)+'</p></div>'+
      (item.id==="sql"||item.id==="vector"?'<button type="button" class="lab-jump-exercise" id="jumpToExercise">'+(item.id==="sql"?'Проследить одну строку':'Проверить свой прогноз об итераторе')+' ↓</button>':'')+'</section>';
  }
  function catalogPage(){
    stop();lab=null;model=null;document.title="Визуальные лаборатории · C++ / Backend";$("catalogLink").hidden=true;$("returnLink").href="cpp_backend_roadmap.html";$("returnLink").textContent="← К программе курса";
    window.CourseLabAtlas.mount(root,catalog,window.courseLabHref,stationName,esc);
  }
  function readRoute(){
    const focusedMode=document.activeElement&&document.activeElement.dataset.mode;
    if($("programDialog").open)$("programDialog").close();
    const p=new URLSearchParams(location.hash.slice(1));
    // Preserve old packet-path bookmarks using the registered local destination,
    // never a URL supplied in the fragment.
    const migrated=catalog.find(item=>item.id==="packetpath"&&item.id===p.get("lab")&&item.file!=="visual_labs.html");
    if(migrated){
      stop();
      const entry=migrated.entries.find(e=>e.station===p.get("from")&&e.section===p.get("section"));
      const scenario=migrated.scenarios.includes(p.get("scenario"))?p.get("scenario"):migrated.scenarios[0];
      location.replace(window.courseLabHref(migrated.id,scenario,entry&&entry.station,entry&&entry.section));
      return;
    }
    const requested=catalog.find(item=>item.id===p.get("lab")&&item.file==="visual_labs.html");
    if(!requested){catalogPage();return;}
    lab=requested;context=lab.entries.find(e=>e.station===p.get("from")&&e.section===p.get("section"))||null;
    const allowed=allowedModes();mode=allowed.includes(p.get("scenario"))?p.get("scenario"):(context&&allowed.includes(context.scenario)?context.scenario:allowed[0]);
    mount();
    if(focusedMode)root.querySelector('[data-mode="'+mode+'"]').focus();
  }
  function allowedModes(){
    if(lab.id==="network"&&context)return context.station==="station7"?lab.scenarios.slice(0,3):lab.scenarios.slice(3);
    if(lab.id==="ownership"&&context&&context.section==="ownership-graph")return lab.scenarios.filter(s=>s!=="unique");
    return lab.scenarios;
  }
  function changeMode(next){
    const p=new URLSearchParams();p.set("lab",lab.id);p.set("scenario",next);if(context){p.set("from",context.station);p.set("section",context.section);}location.hash=p.toString();
  }
  function mount(){
    stop();cursor=0;model=M[lab.id](mode,parameters);
    $("catalogLink").hidden=false;
    const back=context||lab.entries.find(e=>e.scenario===mode)||lab.entries[0];
    $("returnLink").href=back.file+"#section="+back.section;$("returnLink").textContent="← К разделу станции "+stationName(back.station);
    document.title=lab.title+" · Лаборатория C++ / Backend";
    root.innerHTML='<section class="lab-hero"><div class="lab-kicker">Лаборатория '+String(catalog.indexOf(lab)+1).padStart(2,"0")+' · C++ / Backend</div><h1>'+esc(lab.title)+'</h1><p>'+esc(lab.summary)+'</p></section>'+
      '<nav class="lab-modes" aria-label="Варианты эксперимента">'+allowedModes().map(id=>'<button class="lab-mode" data-mode="'+id+'" aria-pressed="'+(id===mode)+'">'+esc(modeNames[id]||id)+'</button>').join("")+'</nav>'+
      introduction(lab,mode)+
      '<div class="lab-tools" id="labTools" '+(lab.id!=="overload"&&!model.scheduler?'hidden':'')+'></div>'+
      '<div class="lab-workspace lab-bench"><div class="lab-column observation-column"><section class="lab-panel"><div class="lab-panel-head"><h2>Схема опыта</h2><span class="lab-meta" id="sceneStep"></span></div><div class="lab-scene" id="labScene" tabindex="0" aria-label="Схема состояния; широкую схему можно прокрутить горизонтально"></div></section>'+
      '<section class="lab-controls" aria-label="Управление экспериментом"><div class="lab-transport"><button class="lab-icon-button" id="labReset" title="К началу" aria-label="К началу">↤</button><button class="lab-icon-button" id="labPrev" title="Предыдущий шаг" aria-label="Предыдущий шаг">←</button><button class="lab-icon-button play" id="labPlay" title="Автовоспроизведение" aria-label="Автовоспроизведение">▷</button></div><div class="lab-scrub"><label for="labRange"><span>Начало</span><span id="rangeLabel"></span><span>Результат</span></label><input id="labRange" type="range" min="0" max="'+(model.steps.length-1)+'" value="0" aria-label="Шаг эксперимента"></div><button class="lab-next" id="labNext">Следующий шаг →</button></section>'+
      '<section class="lab-panel lab-insight"><div class="lab-insight-top"><span id="stepLabel"></span><span id="stepCount"></span></div><h3 id="stepTitle"></h3><p id="stepText"></p><div class="lab-rule" id="stepRule"></div></section></div>'+
      '<div class="lab-column evidence-column"><section class="lab-panel lab-code"><div class="lab-panel-head"><h2>Код и договор</h2><span class="lab-meta">'+esc(lab.id==="sql"||lab.id==="transactions"?"SQL":"СЦЕНАРИЙ")+'</span></div><div class="lab-code-body" id="labCode" tabindex="0" aria-label="Код и текущая строка"></div><div class="lab-code-footer"><span>'+esc(model.language)+'</span>'+(model.program?'<button id="openProgram">Полная программа ↗</button>':'')+'</div></section>'+
      '<section class="lab-panel"><div class="lab-panel-head"><h2>Журнал модели</h2><span class="lab-meta">Наблюдения, не stdout</span></div><div class="lab-journal" id="labJournal"></div></section></div></div>'+
      '<div class="lab-help"><span>← → — шаги · пробел — воспроизведение · журнал возвращает к событию</span><button id="toggleEvents" aria-expanded="false" aria-controls="labEvents">Показать все события</button></div><nav id="labEvents" class="lab-events" aria-label="События эксперимента" hidden></nav>'+
      (lab.id==="vector"?vectorChallenge(model):"")+
      (lab.id==="sql"?sqlRowExplorer(model):"")+
      '<aside class="lab-notes"><section><h2>Условия и границы</h2><p>'+esc(lab.boundary)+'</p>'+(lab.id==="sql"?'<a class="lab-note-link" href="sql_trainer.html#left">Написать свой запрос в SQL-тренажёре →</a>':'')+'</section><section><h2>Первоисточники</h2><div class="lab-sources">'+lab.sources.map(s=>'<a href="'+esc(s.url)+'" target="_blank" rel="noopener noreferrer">'+esc(s.title)+' ↗</a>').join("")+'</div><p><a href="'+esc(back.file+"#section="+back.section)+'">Вернуться к теории станции '+stationName(back.station)+' →</a></p></section></aside><div class="lab-sr" role="status" aria-live="polite" id="labAnnouncement"></div>';
    root.querySelectorAll("[data-mode]").forEach(b=>b.onclick=()=>changeMode(b.dataset.mode));
    if(lab.id==="vector")bindVectorChallenge(model);
    if(lab.id==="sql")bindSqlRowExplorer(model,mode);
    if($("jumpToExercise"))$("jumpToExercise").onclick=()=>{
      stop();const title=$(lab.id==="sql"?"sqlTraceTitle":"vectorChallengeTitle");
      title.focus({preventScroll:true});title.scrollIntoView({block:"start",behavior:"instant"});
    };
    $("labCode").innerHTML=model.code.map((line,i)=>'<div class="lab-code-line" data-code-line="'+i+'"><span class="lab-code-no" aria-hidden="true">'+(i+1)+'</span><span>'+esc(line)+'</span></div>').join("");
    if(lab.id==="overload"){
      $("labTools").innerHTML=[['rate','Приходят / с',0,12],['workers','Исполнителей',1,8],['queue','Мест в очереди',0,20]].map(([key,label,min,max])=>'<label>'+label+'<input data-parameter="'+key+'" type="range" min="'+min+'" max="'+max+'" value="'+parameters[key]+'"><output>'+parameters[key]+'</output></label>').join("");
      $("labTools").querySelectorAll("[data-parameter]").forEach(input=>input.oninput=()=>{stop();parameters[input.dataset.parameter]=Number(input.value);input.parentElement.querySelector("output").textContent=input.value;model=M.overload(mode,parameters);cursor=0;renderEvents();render();});
    }else if(model.scheduler){$("labTools").innerHTML='<div class="thread-buttons"><button id="threadA">Шаг потока A →</button><button id="threadB">Шаг потока B →</button></div><small>Выбор потока заменит будущие события начиная с текущего состояния.</small>';$("threadA").onclick=()=>schedule("A");$("threadB").onclick=()=>schedule("B");}
    $("labPrev").onclick=()=>go(cursor-1);$("labNext").onclick=()=>go(cursor+1);$("labReset").onclick=()=>go(0);$("labRange").oninput=e=>go(Number(e.target.value));$("labPlay").onclick=play;
    $("toggleEvents").onclick=()=>{const open=$("labEvents").hidden;$("labEvents").hidden=!open;$("toggleEvents").setAttribute("aria-expanded",String(open));$("toggleEvents").textContent=open?"Скрыть список событий":"Показать все события";};
    $("labEvents").onclick=e=>{const b=e.target.closest("[data-step]");if(b)go(Number(b.dataset.step));};
    $("labJournal").onclick=e=>{const b=e.target.closest("[data-step]");if(b)go(Number(b.dataset.step));};
    if($("openProgram"))$("openProgram").onclick=()=>{stop();$("programText").textContent=model.program;$("programDialog").showModal();};
    renderEvents();render();
  }
  function schedule(who){
    stop();const step=M.concurrencyStep(model.steps[cursor].state,who,mode);if(!step)return;
    model.steps=model.steps.slice(0,cursor+1);model.steps.push(step);cursor++;renderEvents();render();
  }
  const relText=(x,y,value,cl,anchor="start")=>'<text x="'+x+'" y="'+y+'" text-anchor="'+anchor+'" class="'+cl+'">'+esc(value)+'</text>';
  // Each path is a real link between one user and one task/pair/group.
  // A crossed endpoint has no row on its right; NULL is a row, not a cross.
  function relationOverview(s){
    const source=s.stage==="sources",report=s.stage==="groups"||s.stage==="result";
    const target=source?"Задачи":report?"Отчёт":s.stage==="where"?"После WHERE":"После JOIN";
    let body=relText(16,22,"Сотрудники","rel-heading")+relText(219,22,target,"rel-heading"),y=46;
    for(const [i,u] of s.users.entries()){
      const rows=source?s.tasks.filter(t=>t.owner===u.id).map(t=>({label:'Задача '+t.id,sub:t.done?'выполнена':'открыта'})):
        report?s.rows.filter(r=>r.id===u.id).map(r=>({label:'Количество: '+r.count})):
        s.pairs.filter(p=>p.user===u.id).map(p=>({label:p.task===null?'NULL':'Задача '+p.task,sub:p.task===null?'нет задачи':p.done?'выполнена':'открыта',nil:p.task===null}));
      const span=Math.max(1,rows.length),middle=y+(span-1)*42/2;
      body+='<g class="rel-person rel-u'+i+'" data-user="'+u.id+'">'+relText(16,middle+5,u.name,"rel-name")+'<circle cx="104" cy="'+middle+'" r="4"/>';
      if(!rows.length){
        body+='<path d="M110 '+middle+'h67" class="rel-stop-line"/><path d="M178 '+(middle-4)+'l8 8m0 -8 -8 8" class="rel-cross"/>'+relText(219,middle+5,source?"нет задач":"нет строки","rel-absent");
      }else rows.forEach((r,j)=>{
        const row=y+42*j;
        body+='<g class="rel-link'+(r.nil?' rel-null':'')+'"><path class="rel-thread" d="M109 '+middle+'C147 '+middle+' 165 '+row+' 204 '+row+'"/><circle cx="206" cy="'+row+'" r="3"/>'+relText(219,row+(r.sub?0:5),r.label,"rel-label")+(r.sub?relText(219,row+14,r.sub,"rel-note"):'')+'</g>';
      });
      body+='</g>';y+=span*42+8;
    }
    return '<figure class="relation-plate"><svg role="img" class="relation-map" viewBox="0 0 350 '+(y-10)+'" aria-label="'+esc('Связи строк: сотрудники → '+target+'. Числа и имена перечислены также в таблицах.')+'">'+body+'</svg></figure>';
  }
  function rowJourney(t,step,variant){
    const xs=[34,131,222,316],incoming=t.joined;
    const yAt=i=>incoming.length>1?53+i*44:68,mid=incoming.length>1?75:68;
    const track=(a,b,c,d,style="")=>'<path class="journey-path '+style+'" d="M'+a+' '+b+'C'+(a+22)+' '+b+' '+(c-22)+' '+d+' '+c+' '+d+'"/>';
    const point=(x,y,label,cl)=>'<g class="journey-mark '+cl+'"><rect x="'+(x-25)+'" y="'+(y-13)+'" width="50" height="26" rx="6"/>'+relText(x,y+5,label,"journey-label","middle")+'</g>';
    const cut=(x,y)=>'<g class="journey-cut" data-cut="1"><path d="M'+(x-6)+' '+(y-6)+'l12 12m0 -12 -12 12"/></g>';
    const rows=(incoming.length?incoming:[null]);
    let paths="",nodes=point(xs[0],mid,t.user.name,"source");
    rows.forEach((p,i)=>{
      const y=yAt(i),survives=p&&t.filtered.some(r=>r.task===p.task);
      paths+=track(xs[0]+25,mid,xs[1]-(p?25:7),y,p?'':'cut');
      if(!p){nodes+=cut(xs[1],y);return;}
      const val=p.task===null?'NULL':p.task,cl=p.task===null?'nil':'task';
      nodes+=point(xs[1],y,val,cl);
      if(step>0){paths+=track(xs[1]+25,y,xs[2]-(survives?25:7),y,survives?'kept':'cut');nodes+=survives?point(xs[2],y,val,cl):cut(xs[2],y);}
      if(step===2&&survives)paths+=track(xs[2]+25,y,xs[3]-25,mid,"kept");
    });
    if(step===2)nodes+=t.result?point(xs[3],mid,t.result.count,"total"):relText(xs[3],mid+4,"—","rel-absent","middle");
    const titles=["Строка","JOIN",variant==="where"?"WHERE":"Без WHERE","COUNT"];
    return '<svg role="img" class="row-journey" data-stage="'+step+'" viewBox="0 0 350 '+(incoming.length>1?122:99)+'" aria-label="'+esc('Путь строки: '+t.user.name+'. '+(step===2?(t.result?'В отчёте: '+t.result.count:'Нет строки в отчёте'):step===1?'После фильтра строк: '+t.filtered.length:'После соединения строк: '+incoming.length))+'">'+titles.map((v,i)=>relText(xs[i],22,v,i<=step+1?'journey-heading':'journey-heading future','middle')).join('')+paths+nodes+'</svg>';
  }
  function sqlRowExplorer(trace){
    const users=trace.steps[0].state.users;
    return '<section class="sql-trace" aria-labelledby="sqlTraceTitle"><h2 id="sqlTraceTitle" tabindex="-1">Куда попала строка сотрудника?</h2>'+
      '<p>Вера пока не получила ни одной задачи. В отчёте хочется видеть «Вера: 0», а не гадать, почему её имени там нет. Сравни два запроса на одних данных: шаг за шагом видно, когда возникает разница. Затем выбери Анну — у неё есть и открытая, и выполненная задача.</p>'+
      '<label for="sqlTraceUser">Чью строку проследить?</label> <select id="sqlTraceUser">'+users.map(u=>'<option value="'+u.id+'">'+esc(u.name)+'</option>').join("")+'</select><p id="sqlTraceInput"></p>'+
      '<div class="sql-trace-controls"><button id="sqlTracePrev" type="button">← Назад</button><strong role="status" id="sqlTraceStatus"></strong><button id="sqlTraceNext" type="button">Дальше →</button></div>'+
      '<div class="sql-trace-lanes"><article id="sqlTraceLeft"></article><article id="sqlTraceRight"></article></div></section>';
  }
  function bindSqlRowExplorer(trace,scenario){
    const baseline=scenario==="left"?trace:M.sql("left");
    const otherMode=scenario==="left"?"where":scenario;
    const other=scenario==="left"?M.sql("where"):trace;
    const select=$("sqlTraceUser"),names=["Соединение","Фильтр","Отчёт"];
    let step=0;
    select.value="3";
    const explorer=root.querySelector(".sql-trace");
    explorer.addEventListener("focusin",stop);
    function branch(t,variant){
      const name=esc(t.user.name),label={left:"Условие в ON",where:"Условие в WHERE",inner:"Только совпавшие пары", "count-star":"Считаем все строки"}[variant];
      const filtered=variant==="where",inner=variant==="inner",star=variant==="count-star";
      const code=step===0?(inner?"INNER":"LEFT")+" JOIN · "+(filtered?"по владельцу":"по владельцу и открытой задаче"):step===1?(filtered?"WHERE t.done = false":"Без WHERE"):star?"COUNT(*)":"COUNT(t.id)";
      let body,why;
      if(step<2){
        const rows=step===0?t.joined:t.filtered;
        body=rows.length?'<ul>'+rows.map(p=>'<li><strong>'+name+'</strong><span>'+ (p.task===null?'Задача: NULL · отметка: NULL':'Задача '+p.task+' · '+(p.done?'выполнена':'открыта'))+'</span></li>').join("")+'</ul>':'<div class="sql-trace-empty">Строк нет</div>';
        if(step===0)why=!rows.length?"Для этого человека пары нет. INNER JOIN не добавляет строку без задачи.":rows.some(p=>p.task===null)?"Пары не нашлось. LEFT JOIN сохранил человека; вместо данных задачи стоят NULL.":filtered?"Подошли все задачи этого человека, независимо от отметки о выполнении.":"Подошли только открытые задачи этого человека.";
        else if(!filtered)why="После соединения отдельного фильтра нет: состав строк не меняется.";
        else {
          const removed=t.joined.filter(p=>!rows.some(r=>r.task===p.task));
          why=removed.length?removed.map(p=>p.done===null?"У строки без задачи проверка NULL = false даёт неизвестный результат. WHERE оставляет только истину, поэтому строка исчезла.":"У задачи "+p.task+" отметка о выполнении равна true. Условие true = false не выполнено: этой пары больше нет.").join(" "):"Все полученные пары прошли проверку: у каждой задачи отметка о выполнении равна false.";
        }
      }else{
        body=t.result?'<div class="sql-trace-result"><strong>'+name+': '+t.result.count+'</strong></div>':'<div class="sql-trace-empty">Нет строки в отчёте</div>';
        why=!t.result?"К группировке не осталось ни одной строки этого человека. Здесь нет группы, которой можно было бы записать ноль.":star?"COUNT(*) считает каждую строку группы, даже если вместо номера задачи стоит NULL.":t.result.count===0?"Строка человека сохранилась, но в ней вместо номера задачи — NULL. COUNT(t.id) не включает NULL в подсчёт и возвращает число 0.":"COUNT(t.id) посчитал номера задач в оставшихся строках. У каждой такой задачи есть номер.";
      }
      return '<h3>'+label+'</h3><div class="sql-trace-operation">'+esc(code)+'</div>'+rowJourney(t,step,variant)+body+'<p>'+esc(why)+'</p>';
    }
    function draw(){
      const a=M.sqlRowTrail(baseline,Number(select.value)),b=M.sqlRowTrail(other,Number(select.value));
      $("sqlTraceInput").textContent=a.user.name+" в исходных таблицах: "+(a.tasks.length?a.tasks.map(t=>"задача "+t.id+" ("+(t.done?"выполнена":"открыта")+")").join("; "):"задач нет")+".";
      $("sqlTraceLeft").innerHTML=branch(a,"left");$("sqlTraceRight").innerHTML=branch(b,otherMode);
      $("sqlTraceStatus").textContent=(step+1)+" из 3 · "+names[step]+" · "+a.user.name;
      $("sqlTracePrev").disabled=step===0;$("sqlTraceNext").disabled=step===2;
    }
    select.onchange=draw;$("sqlTracePrev").onclick=()=>{step=Math.max(0,step-1);draw();};$("sqlTraceNext").onclick=()=>{step=Math.min(2,step+1);draw();};draw();
  }
  // Independent of playback: a reader can compare several old iterators at
  // the same mutation without rewinding the code for each prediction.
  function vectorChallenge(trace){
    const {before,kind}=M.vectorProbe(trace,"end");
    const options=before.values.map((v,i)=>'<option value="'+i+'">На элемент '+v+' (индекс '+i+')</option>').join("")+'<option value="end">За последним элементом: v.end()</option>';
    return '<section class="vector-exercise" aria-labelledby="vectorChallengeTitle"><h2 id="vectorChallengeTitle" tabindex="-1">Что станет с сохранённым итератором?</h2>'+
      '<p>Представь, что перед той же операцией мы сохранили итератор: он указывает на элемент или отмечает границу сразу за последним элементом (<code>end()</code>). На этой границе числа нет. Теперь '+(kind==="erase"?'удалим средний элемент, 20':'добавим число 30 в конец')+'. Выбери позицию и предскажи: останется ли старый итератор действительным?</p>'+
      '<label for="vectorTarget">Что запомнить до операции</label><select id="vectorTarget">'+options+'</select>'+
      '<div class="vector-snapshots"><div id="vectorBefore"></div><div id="vectorAfter" hidden></div></div>'+
      '<div class="vector-votes" role="group" aria-label="Прогноз"><button type="button" id="vectorYes">Останется действительным</button><button type="button" id="vectorNo">Станет недействительным</button></div>'+
      '<p class="vector-answer" id="vectorAnswer" role="status"></p></section>';
  }
  // Equal widths denote element slots, not bytes or measured addresses.
  // end() is a boundary line, never an extra occupied slot.
  function memoryTape(s,id,markers=[],lost=""){
    const x=24,w=68,n=s.values.length,edge=x+n*w,cap=x+s.capacity*w;
    const uid="mem-hatch-"+id;
    const txt=(a,b,text,cl,anchor="middle")=>'<text x="'+a+'" y="'+b+'" class="'+cl+'" text-anchor="'+anchor+'">'+esc(text)+'</text>';
    let drawing='<defs><pattern id="'+uid+'" width="7" height="7" patternUnits="userSpaceOnUse"><path d="M-2 2l4 -4M0 7l7 -7M5 9l4 -4" class="mem-hatch"/></pattern></defs>';
    const cursor=i=>markers.find(m=>m.i===i);
    for(let i=0;i<s.capacity;i++){
      const left=x+i*w,live=i<n,mark=live&&cursor(i);
      drawing+='<g class="mem-slot'+(mark?' tracked':'')+'" data-slot="'+i+'" data-occupied="'+live+'">'+
        '<path class="mem-cap" d="M'+left+' 56l10 -8h'+w+'l-10 8z"/>'+
        '<rect class="mem-face '+(live?'mem-live':'mem-spare')+'" x="'+left+'" y="56" width="'+w+'" height="44"/>'+
        (live?txt(left+w/2,86,s.values[i],"mem-value"):'<rect x="'+left+'" y="56" width="'+w+'" height="44" fill="url(#'+uid+')"/>')+
        (live?txt(left+w/2,43,'['+i+']',"mem-index"):i===n?txt(left+w/2,43,"запас","mem-index"):'')+'</g>';
    }
    drawing+='<path d="M'+cap+' 56l10 -8v44l-10 8z" class="mem-side"/>';
    drawing+='<g class="mem-end'+(cursor(n)?' tracked':'')+'"><path d="M'+edge+' 26v76"/>'+txt(edge+4,22,"end()","mem-end-label","start")+'</g>';
    for(const m of markers){
      const place=x+m.i*w+(m.i===n?0:w/2);
      drawing+='<g class="mem-cursor"><path d="M'+place+' 117v-12m-4 4 4 -5 4 5"/>'+txt(place,136,m.name,"mem-cursor-label")+'</g>';
    }
    if(lost)drawing+='<g class="mem-cut"><path d="M24 121h28m5 -4 8 8m0 -8 -8 8"/>'+txt(74,126,lost,"mem-cut-label","start")+'</g>';
    const alt='Буфер '+s.buffer+'. Размер '+n+', ёмкость '+s.capacity+'. Элементы: '+(s.values.join(', ')||'нет')+'. '+markers.map(m=>m.name+' → '+(m.i===n?'end()':s.values[m.i])).join('; ')+(lost?'. '+lost:'');
    return '<svg class="memory-tape" viewBox="0 0 350 '+(markers.length||lost?'148':'112')+'" role="img" aria-label="'+esc(alt)+'">'+drawing+'</svg>';
  }
  function vectorSnapshot(label,s,tracked,lost=false){
    return '<figure class="memory-plate"><figcaption><strong>'+label+' · буфер '+s.buffer+'</strong><span>size '+s.values.length+' / capacity '+s.capacity+'</span></figcaption>'+
      memoryTape(s,label==="До"?"before":"after",tracked<0?[]:[{i:tracked,name:"итератор"}],lost?"итератор недействителен":"")+'</figure>';
  }
  function bindVectorChallenge(trace){
    const select=$("vectorTarget");
    select.value=mode==="erase"?"1":mode==="reserved"?"end":"0";
    root.querySelector(".vector-exercise").addEventListener("focusin",stop);
    function draw(prediction){
      const {before,after,index,reallocated,kind,position,valid}=M.vectorProbe(trace,select.value);
      $("vectorBefore").innerHTML=vectorSnapshot("До",before,index);
      const revealed=typeof prediction==="boolean";
      $("vectorAfter").hidden=!revealed;
      $("vectorAfter").innerHTML=revealed?vectorSnapshot("После",after,valid?index:-1,!valid)+'<span class="vector-finding '+(valid?'kept':'lost')+'">'+(valid?'✓ Та же позиция доступна':'× Старый итератор недействителен')+'</span>':"";
      const answer=$("vectorAnswer");
      if(!revealed){answer.textContent="";return;}
      let why;
      if(reallocated)why="Для третьего элемента в буфере A не было места. Вектор сменил буфер: все старые итераторы, включая прежний end(), стали недействительными. Совпадение значений в новом буфере ничего не меняет.";
      else if(valid)why=kind==="erase"?"Этот элемент находится до места удаления. Его итератор остался действительным и по-прежнему указывает на "+before.values[index]+".":"Буфер не сменился, а этот элемент стоял до места вставки. Его итератор по-прежнему указывает на "+before.values[index]+".";
      else if(kind==="append")why="В буфере хватило места, но прежний end() обозначал границу сразу после 20. Теперь там элемент 30. Старый end() не стал итератором на 30: для новой границы нужно снова вызвать v.end().";
      else if(index===position)why="В той же позиции теперь стоит 30 вместо 20. Удаление сделало старый итератор недействительным. Чтобы продолжить обход с числа 30, используй новый итератор, который вернула erase.";
      else if(index===before.values.length)why="Прежний end() находился после места удаления. Этот итератор недействителен; границу укоротившегося вектора нужно получить заново через v.end().";
      else why="Число 30 осталось в векторе, но сдвинулось влево. Итераторы на удалённый элемент и на все позиции после него стали недействительными.";
      answer.textContent=(prediction===valid?"Верно. ":"Не совсем. ")+why;
    }
    select.onchange=()=>draw();$("vectorYes").onclick=()=>draw(true);$("vectorNo").onclick=()=>draw(false);draw();
  }
  function stop(){if(timer!==null)clearInterval(timer);timer=null;if($("labPlay")){$("labPlay").textContent="▷";$("labPlay").setAttribute("aria-label","Автовоспроизведение");}}
  function go(step){stop();cursor=Math.max(0,Math.min(model.steps.length-1,step));render();}
  function play(){if(timer!==null){stop();return;}if(cursor===model.steps.length-1)cursor=0;render();$("labPlay").textContent="Ⅱ";$("labPlay").setAttribute("aria-label","Пауза");timer=setInterval(()=>{if(cursor<model.steps.length-1){cursor++;render();}if(cursor===model.steps.length-1)stop();},2400);}
  function renderEvents(){
    $("labEvents").innerHTML=model.steps.map((s,i)=>'<button data-step="'+i+'"><span>'+String(i+1).padStart(2,"0")+'</span>'+esc(s.title)+'</button>').join("");$("labRange").max=model.steps.length-1;
  }
  function render(){
    const e=model.steps[cursor],s=e.state;
    $("stepLabel").textContent="Событие "+String(cursor+1).padStart(2,"0");$("stepCount").textContent=(cursor+1)+" / "+model.steps.length;$("sceneStep").textContent=modeNames[mode];
    $("stepTitle").textContent=e.title;$("stepText").textContent=e.text;$("stepRule").textContent=e.rule;
    const scene=$("labScene"), prior=scene.querySelector(".scene-detail");
    const cpp=window.CourseCppPlates?.render(lab.id,mode,s,model,cursor);
    const service=window.CourseServicePlates?.render(lab.id,mode,s,model,cursor);
    if(cpp){
      // The timeline and the structural drawing answer different questions.
      // Keep the reader's choice when stepping through the same experiment.
      scene.innerHTML=cpp+'<details class="scene-detail"'+(prior?.open?' open':'')+'><summary>Подробная схема текущего шага</summary>'+scenes[model.type](s)+'</details>';
    }else scene.innerHTML=service || scenes[model.type](s);
    $("labRange").value=cursor;$("labRange").setAttribute("aria-valuetext",(cursor+1)+": "+e.title);$("rangeLabel").textContent="Шаг "+(cursor+1)+" из "+model.steps.length;
    $("labPrev").disabled=cursor===0;$("labReset").disabled=cursor===0;$("labNext").disabled=cursor===model.steps.length-1;
    $("labCode").querySelectorAll("[data-code-line]").forEach(el=>{const active=Number(el.dataset.codeLine)===e.line;el.classList.toggle("active",active);if(active)el.setAttribute("aria-current","step");else el.removeAttribute("aria-current");});
    const active=$("labCode").children[e.line];if(active){const top=active.offsetTop;if(top<$("labCode").scrollTop||top+25>$("labCode").scrollTop+$("labCode").clientHeight)$("labCode").scrollTop=Math.max(0,top-100);}
    $("labJournal").innerHTML=model.steps.slice(0,cursor+1).map((item,i)=>item.note?'<button data-step="'+i+'" class="'+(i===cursor?'current':'')+'"><span>'+String(i+1).padStart(2,"0")+'</span><span>'+esc(item.note)+'</span></button>':"").join("")||'<span class="lab-meta">Здесь появятся наблюдения о состоянии.</span>';
    $("labJournal").scrollTop=$("labJournal").scrollHeight;
    $("labEvents").querySelectorAll("[data-step]").forEach(b=>{if(Number(b.dataset.step)===cursor)b.setAttribute("aria-current","step");else b.removeAttribute("aria-current");});
    if(model.scheduler){const n=mode==="mutex"?5:mode==="rmw"?1:3;for(const who of ["A","B"]){$("thread"+who).disabled=s.pc[who]>=n||s.blocked[who];$("thread"+who).textContent=s.pc[who]>=n?who+": завершён":s.blocked[who]?who+": ждёт mutex":"Шаг потока "+who+" →";}}
    $("labAnnouncement").textContent="Шаг "+(cursor+1)+". "+e.title;
  }

  function svg(label,body,height=370){return '<svg viewBox="0 0 1000 '+height+'" role="img" aria-label="'+esc(label)+'"><defs><marker id="labArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 10 5 0 10Z" fill="#769363"/></marker></defs>'+body+'</svg>';}
  function node(x,y,w,h,title,subtitle,status="ready"){return '<g class="node '+status+'"><rect x="'+x+'" y="'+y+'" width="'+w+'" height="'+h+'" rx="11"/><text x="'+(x+18)+'" y="'+(y+29)+'">'+esc(title)+'</text><text class="node-sub" x="'+(x+18)+'" y="'+(y+53)+'">'+esc(subtitle)+'</text></g>';}
  function edge(d,label,x,y,kind="strong"){return '<path d="'+d+'" class="edge '+kind+'" marker-end="url(#labArrow)"/>'+(label?'<text class="edge-label" x="'+x+'" y="'+y+'">'+esc(label)+'</text>':"");}
  function table(title,headers,rows){return '<div class="lab-table-wrap"><table class="lab-table"><caption>'+esc(title)+'</caption><thead><tr>'+headers.map(h=>'<th scope="col">'+esc(h)+'</th>').join("")+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(v=>'<td'+(v===null?' class="null"':'')+'>'+esc(v===null?"NULL":v)+'</td>').join("")+'</tr>').join("")+'</tbody></table></div>';}
  const scenes={
    temporaries(s){
      const owner=s.owner==="alive"?"Жив":s.owner==="destroyed"?"Уничтожен":"Ещё не создан";
      const borrow={waiting:"Ещё не получена",valid:"Доступ действителен",dangling:"Висячая ссылка — не использовать",ended:"Обход завершён"}[s.borrow];
      const label=s.mode==="parameter"?"Параметр values":s.mode==="named"?"Переменная batch":"Временный Batch";
      return '<div class="lifetime-version">'+esc(modeNames[s.mode])+'</div><div class="lifetime-cards"><section data-lifetime-owner="'+esc(s.owner)+'"><h3>'+esc(label)+'</h3><strong>'+esc(owner)+'</strong><p>Содержит список <code>1, 2, 3</code></p></section><div class="lifetime-borrow '+(s.borrow==="dangling"?'invalid':'')+'"><h3>Ссылка на список</h3><strong>'+esc(borrow)+'</strong><p>Не содержит своей копии чисел</p></div></div><ol class="lifetime-timeline" aria-label="Границы времени жизни">'+["Создание владельца","Получение ссылки","Подготовка обхода","Чтение элементов","Выход из цикла"].map((label,i)=>'<li'+(s.phase===i+1?' aria-current="step"':'')+' class="'+(s.phase>i+1?'passed':s.phase===i+1?'current':'future')+'">'+esc(label)+'</li>').join("")+'</ol><div class="lifetime-verdict '+(s.borrow==="dangling"?'invalid':'')+'">'+(s.iteration==="blocked"?'Обход остановлен: нельзя читать уничтоженный список.':s.values.length?'Прочитано из живого списка: '+s.values.join(", "):'До чтения элементов')+'</div><p class="lab-scene-caption">'+(s.mode==="parameter"?'Параметр по значению не сохраняется для вызывающего цикла.':s.mode==="cxx20"?'В этом выражении C++20 не продлевает жизнь Batch через вызов rows().':s.mode==="named"?'Владелец явно назван и охватывает цикл в обеих редакциях.':'Для этого временного Batch действует продление из C++23.')+' Это схема правил языка, не запуск программы браузером.</p>';
    },
    taskownership(s){
      const actors=[["sender","Отправитель","Локальный unique_ptr"],["queue","Очередь","Лямбда внутри обёртки"],["worker","Исполнитель","Локальная job"]];
      return '<div class="task-owner-route">'+actors.map(([id,name,detail])=>'<section'+(s.owner===id?' aria-current="step"':'')+'><h3>'+esc(name)+'</h3><p>'+esc(detail)+'</p><strong>'+(s.owner===id?'Владеет Payload':id==="sender"&&s.stage>1?'unique_ptr пуст':id==="queue"&&s.stage>2?'Очередь пуста':'Не владеет')+'</strong></section>').join("")+'</div><div class="task-payload '+(s.alive?'alive':'')+'"><h3>Данные Payload · 42</h3><strong>'+(s.alive?'Объект жив':s.stage===0?'Ещё не создан':'Объект уничтожен')+'</strong><p>Число вызовов команды: <b>'+s.ran+'</b></p></div><p class="lab-scene-caption">Стрелка чтения схемы — слева направо. Меняется владелец одних данных, а не их адрес или количество копий. Роли показаны в одном потоке; состояния очереди не являются обещанием потокобезопасности.</p>';
    },
    packetpath(s){
      const bad=s.status==="dropped"||s.status==="too-big";
      const actor=(id,title,details)=>'<section class="packet-node '+(s.focus===id?'active':'')+'" data-packet-node="'+id+'"'+(s.focus===id?' aria-current="step"':'')+'><h3>'+esc(title)+'</h3>'+details.map(([name,value])=>'<p><span>'+esc(name)+'</span><code>'+esc(value)+'</code></p>').join("")+'</section>';
      const link=(id,title,mtu)=>'<div class="packet-link '+(s.link===id?'active ':'')+(id==="wan"&&bad?'blocked':'')+'"><span>'+esc(title)+'</span><strong aria-hidden="true">'+(id==="wan"&&bad?'×':s.link===id?(s.direction==="request"?'→':'←'):'—')+'</strong><small>MTU '+mtu+'</small></div>';
      let body='<div class="packet-prepared"><span>Подготовленная модель</span>'+esc(s.boundary)+' Не выполняет команды или сетевые запросы.</div>';
      body+='<div class="packet-topology-scroll"><div class="packet-topology" role="group" aria-label="Client через LAN соединён с router, router через WAN соединён с server. Текущий узел: '+esc(s.focus)+'">'+actor("client","nl7-client",[["eth0",s.addresses.client]])+link("lan","LAN",s.lanMtu)+actor("router","nl7-router",[["br-lan",s.addresses.lan],["wan0",s.addresses.wan]])+link("wan","WAN",s.wanMtu)+actor("server","nl7-server",[["eth0",s.addresses.server]])+'</div></div>';
      body+='<div class="packet-verdict '+(bad?'bad':'')+'" data-packet-status="'+esc(s.status)+'"><span>'+esc(s.stage)+'</span><strong>'+esc(s.verdict)+'</strong></div>';
      const fields=p=>{
        if(!p)return Array(12).fill("не сформирован");
        const mac=(value,name)=>value?(name+" · "+value):"— · только IP-представление";
        return [p.kind,mac(p.ethSrc,p.ethSrcName),mac(p.ethDst,p.ethDstName),p.src,p.dst,String(p.hopLimit),p.ipBytes+" байт",p.kind==="UDP"?"UDP (17)":"ICMPv6 (58)",p.sport===null?"— · нет UDP-портов":p.sport+" → "+p.dport,p.payloadBytes===null?"— · цитата, не UDP payload":p.payloadBytes+" байт"+(p.payloadText?" · "+p.payloadText:""),p.icmpType===null?"—":p.icmpType+" / "+p.icmpCode,p.reportedMtu===null?"—":p.reportedMtu+" байт"];
      };
      const before=fields(s.before),after=fields(s.after),labels=["Пакет","L2 · источник","L2 · назначение","L3 · источник","L3 · назначение",s.family==="IPv6"?"L3 · Hop Limit":"L3 · TTL","L3 · полная длина","IP Protocol / Next Header","L4 · UDP src → dst","Данные UDP","ICMPv6 type / code","PTB · объявленная MTU"];
      const rows=labels.map((label,i)=>{
        const changed=before[i]!==after[i];
        return '<tr'+(changed?' class="packet-field-changed"':'')+'><th scope="row">'+esc(label)+(changed?'<small>изменено</small>':'')+'</th><td>'+esc(before[i])+'</td><td>'+esc(after[i])+'</td></tr>';
      }).join("");
      body+='<div class="lab-table-wrap packet-fields"><table class="lab-table"><caption>До и после текущего события · поля, не байтовый дамп</caption><thead><tr><th scope="col">Поле</th><th scope="col">До шага</th><th scope="col">После шага</th></tr></thead><tbody>'+rows+'</tbody></table></div>';
      body+='<dl class="packet-facts"><div><dt>Маршрут текущего направления</dt><dd>'+esc(s.route)+'</dd></div><div><dt>Точка обработки</dt><dd>'+esc(s.hook)+'</dd></div>'+(s.pmtu===null?'':'<div><dt>Оценка PMTU у client</dt><dd>'+s.pmtu+' байт</dd></div>')+'</dl>';
      if(s.nat)body+='<div class="packet-nat">'+table("Заданное NAT-сопоставление · порт сохранён по условию",["Направление","Адреса и порты"],[["Исходный запрос",s.nat.original],["После SNAT",s.nat.translated],["Ответ на WAN",s.nat.reply],["После reverse NAT",s.nat.restored]])+'</div>';
      if(s.after&&s.after.quote){const q=s.after.quote;body+='<p class="packet-quote"><strong>Внутри PTB — цитата:</strong> ['+esc(q.src)+']:'+q.sport+' → ['+esc(q.dst)+']:'+q.dport+'; исходная полная длина '+q.ipBytes+' байт. Записано '+q.quotedBytes+' байт цитаты.</p>';}
      body+='<div class="packet-counters" aria-label="Счётчики только этой модели"><span>Запросы LAN <strong>'+s.counters.lanRequests+'</strong></span><span>Запросы WAN <strong>'+s.counters.wanRequests+'</strong></span><span>Получено server <strong>'+s.counters.serverRequests+'</strong></span><span>Ответы client <strong>'+s.counters.repliesToClient+'</strong></span><span>PTB у client <strong>'+s.counters.ptbToClient+'</strong></span></div>';
      return body+'<p class="lab-scene-caption">MAC-C, MAC-BR, MAC-RWAN и MAC-S — фиксированные учебные имена с адресами в таблице. Порядок событий не является измерением времени. Изменённые поля отмечены текстом; «—» означает отсутствие этого поля или текущего L2-заголовка.</p>';
    },
    ownership(s){
      if(s.cycle){let body=node(180,55,240,88,"A : Node",s.aliveA?"сильных: "+s.countA:s.created?"объект уничтожен":"Ещё не создан",s.aliveA?"ready":"dead")+node(590,55,240,88,"B : Node",s.aliveB?"сильных: "+s.countB:s.created?"объект уничтожен":"Ещё не создан",s.aliveB?"ready":"dead");
        body+='<text class="scene-title" x="180" y="33">'+(s.externalA?"Есть внешняя a":"Внешней a нет")+'</text><text class="scene-title" x="590" y="33">'+(s.externalB?"Есть внешняя b":"Внешней b нет")+'</text>';
        if(s.linked&&s.aliveA&&s.aliveB){body+=edge("M420 90 H590","A.next · strong",450,76)+edge("M705 143 V245 H300 V143",s.weakBack?"B.back · weak":"B.back · strong",420,271,s.weakBack?"weak":"strong");}
        else if(s.weakBack&&s.aliveB&&!s.aliveA)body+=edge("M705 143 V245 H300 V143","back: A уже уничтожен",405,271,"weak");
        return svg("Узлы A и B: сильное владение и слабая обратная связь",body,310)+'<p class="lab-scene-caption">Сплошная связь удерживает объект; пунктирная — не увеличивает сильное владение.</p>';
      }
      let body="";const shared=s.control||mode==="shared";
      const owners=shared?["a","b","held"]:["a","b"];
      owners.forEach((name,i)=>{const active=s.owners.includes(name),y=25+i*101;body+=node(45,y,180,73,name,active?"владеет Item":s.declared.includes(name)?"пустой":"Не объявлен",active?"ready":"dead");if(active)body+=edge('M225 '+(y+36)+' C330 '+(y+36)+' 330 130 430 130',"",0,0);});
      body+=node(430,86,235,94,"Item",s.alive?"Объект жив":s.created?"Уничтожен":"Ещё не создан",s.alive?"ready":"dead");
      if(shared){body+=node(738,86,225,94,"Control block",s.control?"сильных: "+s.strong:s.created?"Освобождён":"Ещё не создан",s.control?"ready":"dead");if(s.control)body+=edge("M738 130 H665","",0,0,"weak");body+=node(738,242,225,74,"w",s.weak?"слабая ссылка":s.weakDeclared?"пустая":"Не объявлена",s.weak?"ready":"dead");if(s.weak)body+=edge("M850 242 V180","не удерживает Item",680,220,"weak");}
      else {body+=node(430,242,320,74,"observer",s.observer?(s.observerValid?"Доступ пока пригоден":"Объект уже уничтожен"):"Ещё не получен",s.observerValid?"ready":"dead");if(s.observer)body+=edge("M550 242 V180","не владеет",563,218,"weak");}
      return svg("Граф владения: "+s.strong+" сильных владельцев, Item "+(s.alive?"жив":"не существует"),body,340)+'<p class="lab-scene-caption">Это логические связи владения. Явных weak_ptr: '+s.weak+'. Внутреннее устройство счётчиков реализации не изображено.</p>';
    },
    vector(s){
      const pointers=s.pointer==="valid"?[{i:0,name:"p"}]:s.pointer==="all-valid"?[{i:0,name:"before"},{i:1,name:"at"},{i:2,name:"after"}]:s.erased?[{i:0,name:"before"},{i:1,name:"next"}]:[];
      let body='<figure class="memory-plate"><figcaption><strong>Буфер '+s.buffer+'</strong><span>size '+s.values.length+' / capacity '+s.capacity+'</span></figcaption>'+
        (s.oldBuffer?'<div class="mem-retired"><s>Буфер A</s><span>освобождён · p недействителен</span></div>':'')+
        memoryTape(s,"main",pointers)+(s.capacity>s.values.length?'<div class="mem-key"><i aria-hidden="true"></i>Запас памяти · элементов ещё нет в заштрихованных ячейках</div>':'')+'</figure>';
      const invalid=s.pointer==="invalid"||s.erased;
      body+='<div class="vector-pointer '+(invalid?'invalid':'')+'">'+(s.mode==="erase"?(s.pointer==="none"?"Итераторы ещё не получены":s.erased?'before → 10 · пригоден<br>at / after → недействительны<br>next → 30 · новый пригодный итератор':'before → 10 · at → 20 · after → 30'):s.pointer==="none"?'p ещё не получен':invalid?'p → старый буфер · не разыменовывать':'p → первый элемент · пригоден')+'</div><p class="vector-caption">Ячейка «запас» не содержит элемента vector. Логический номер элемента и пригодность старого доступа — разные вопросы.</p>';return body;},
    build(s){const positions={"types.hpp":[35,25],"core.cpp":[35,140],"main.cpp":[35,255],"core.o":[420,130],"main.o":[420,255],app:[785,190],"README.md":[35,375]};let body=edge("M245 65 H310 V165 H420","заголовок",305,112,"weak")+edge("M245 65 H310 V290 H420","",0,0,"weak")+edge("M245 175 H420","компиляция",275,160)+edge("M245 290 H420","компиляция",275,275)+edge("M630 165 H700 V225 H785","линковка",675,195)+edge("M630 290 H700 V225 H785","",0,0);const labels={ready:"Актуален",dirty:"Нужно обновить",changed:"Изменён",building:"Выполняется"};for(const [name,[x,y]] of Object.entries(positions))body+=node(x,y,210,76,name,labels[s.status[name]],s.status[name]);return svg("Граф зависимостей после изменения "+s.changed,body,470)+'<p class="lab-scene-caption">Стрелка идёт от входа к зависящему результату. README не входит в правила этого проекта.</p>';},
    concurrency(s){const actions=mode==="mutex"?["lock","чтение","локальный +1","запись","unlock"]:mode==="rmw"?["fetch_add(+1)"]:["load","локальный +1","store"];return '<div class="concurrent-header"><div class="counter-value"><small>Общий counter</small>'+s.value+'</div>'+(mode==="mutex"?'<span class="lock-state">Mutex: '+(s.lock?'владелец '+s.lock:'свободен')+'</span>':'')+'</div><div class="thread-grid">'+["A","B"].map(who=>'<section class="thread-card '+(s.last===who?'active':'')+'"><h3>Поток '+who+'<small>'+(s.blocked[who]?'Ждёт':s.pc[who]===actions.length?'Готов':'Следующий шаг '+(s.pc[who]+1))+'</small></h3>'+actions.map((a,i)=>'<div class="thread-action '+(i<s.pc[who]?'done':i===s.pc[who]?'current':'')+'"><span>'+(i<s.pc[who]?'✓':i===s.pc[who]?'→':'·')+'</span>'+a+'</div>').join("")+'<div class="thread-local">local = '+(s.locals[who]===null?'—':s.locals[who])+'</div></section>').join("")+'</div><p class="lab-scene-caption">В раздельном варианте обращения к counter атомарны. Выбирая порядок, ищи потерю увеличения; результат обычного int с data race так разбирать нельзя.</p>';},
    network(s){if(s.api){const right=s.direction==="right",path=right?"M260 125 H740":"M740 125 H260";let body=node(20,85,235,83,"Клиент","Знает только полученное")+node(745,85,235,83,"Сервис","Состояние на сервере")+(s.message?edge(s.lost?"M740 125 H500":path,"",0,0,s.lost?"weak":"strong"):"");body+='<text class="edge-label" x="500" y="95" text-anchor="middle">'+esc(s.message)+'</text>';if(s.lost)body+='<text x="488" y="140" fill="#a65d48" font-size="36">×</text>';return svg("Обмен запроса и ответа: "+s.message,body,205)+'<div class="api-actors"><section class="api-state"><h3>Клиент знает</h3>'+esc(s.client)+'</section><section class="api-state"><h3>На самом деле у сервиса</h3>'+esc(s.server)+(s.key?'<br>Результат K: '+(s.record?'сохранён':'ещё не записан'):'')+'</section></div>';}
      const bytes=arr=>arr.map(n=>'<span class="byte received">'+n.toString(16).padStart(2,"0").toUpperCase()+'</span>').join("");return '<div class="bytes-section"><div class="bytes-label"><span>Весь поток</span><span>получено '+s.received+' / '+s.wire.length+'</span></div><div class="bytes-row">'+s.wire.map((n,i)=>'<span class="byte '+(i<s.received?'received ':'')+((i===0||(i===4&&mode!=="oversize"))?'prefix':'')+'">'+n.toString(16).padStart(2,"0").toUpperCase()+'</span>').join("")+'</div></div><div class="bytes-section"><div class="bytes-label"><span>Буфер парсера</span><span>длина тела: '+(s.expected===null?'ещё не прочитана':s.expected)+'</span></div><div class="bytes-row">'+(s.buffer.length?bytes(s.buffer):'<span class="bytes-empty">Пусто</span>')+'</div></div><div class="bytes-section"><div class="bytes-label">Сообщения приложения</div><div class="messages">'+(s.messages.length?s.messages.map(v=>'<span class="message">'+esc(v||'пустое')+'</span>').join(""):'<span class="bytes-empty">Ещё нет готовых сообщений</span>')+'</div></div>'+(s.rejected?'<div class="protocol-error">Длина превышает предел. Дальнейшие байты этого входа не принимаются.</div>':'')+'<p class="lab-scene-caption">Байты показаны в hex: 41 = A, 42 = B. Префикс длины не входит в тело сообщения.</p>';},
    sql(s){
      const prev=$("labScene").querySelector(".relation-details");
      let body=relationOverview(s)+'<details class="relation-details"'+(prev&&prev.open?' open':'')+'><summary>Посмотреть строки таблиц</summary><div class="sql-sources">'+
        table("users",["id","name"],s.users.map(u=>[u.id,u.name]))+table("tasks",["id","owner_id","done"],s.tasks.map(t=>[t.id,t.owner,t.done?"true":"false"]))+'</div>';
      if(s.stage!=="sources")body+='<div class="sql-stage">Пары после '+(s.mode==="where"&&s.stage!=="join"?'WHERE':'соединения')+'</div>'+table("Результат сопоставления",["user","name","task_id","done"],s.pairs.map(p=>[p.user,p.name,p.task,p.done===null?null:String(p.done)]));
      if(s.stage==="groups"||s.stage==="result")body+='<div class="sql-stage">Одна строка на группу пользователя</div>'+table("Отчёт",["id","name","open_tasks"],s.rows.map(r=>[r.id,r.name,r.count]));
      return body+'</details>';
    },
    transactions(s){return '<div class="db-committed"><span>Зафиксированное '+(s.snapshot?'value':'available')+'<br>Для новой команды Read Committed</span><strong>'+s.database+'</strong></div><div class="db-session-grid"><section class="db-session"><h3>Сессия A</h3>'+esc(s.aStatus)+'<div class="db-local">'+(s.a===null?'—':s.a)+'</div></section><section class="db-session '+(s.waiting?'waiting':'')+'"><h3>Сессия B</h3>'+esc(s.bStatus)+'<div class="db-local">'+(s.b===null?'—':s.b)+'</div></section></div><div class="db-lock">'+(s.snapshot?'В ячейках сессий — прочитанные ими значения. Сохранённая копия не обновляется автоматически.':'Блокировка строки: '+(s.lock?'владелец '+s.lock:'свободна')+' · зафиксированных бронирований: '+s.winners)+'</div><p class="lab-scene-caption">'+(s.snapshot?'Обычный SELECT, без FOR UPDATE; транзакция A не изменяет данные.':'В ячейках сессий — их незавершённое новое значение, если оно есть. Пустое RETURNING — не SQL-ошибка.')+'</p>';},
    overload(s){return '<div class="vector-label"><code>'+({Serving:'Приём открыт',Draining:'Завершение принятых работ',Stopped:'Остановлен'}[s.phase]||esc(s.phase))+'</code><span>t = '+s.time+' с</span></div><div class="load-facts"><div class="load-fact"><strong>'+s.accepted+'</strong>Всего принято</div><div class="load-fact"><strong>'+s.completed+'</strong>Всего выполнено</div><div class="load-fact bad"><strong>'+s.rejected+'</strong>Всего отклонено</div></div><div class="bytes-label"><span>Очередь к следующему такту</span><span>'+s.pending+' / '+s.queue+'</span></div><div class="queue-slots">'+(s.queue?Array.from({length:s.queue},(_,i)=>'<span class="queue-slot '+(i<s.pending?'occupied':'')+'"></span>').join(""):'<span class="bytes-empty">Очередь отключена; остаются только места исполнителей.</span>')+'</div><div class="bytes-label"><span>За такт завершено '+s.lastCompleted+' из возможных '+s.workers+'</span><span>Принято '+s.lastAccepted+' · отказов '+s.lastRejected+'</span></div><div class="load-history" aria-label="Число ожидающих задач по секундам">'+s.history.map(h=>'<div class="load-bar" style="height:'+Math.max(2,h.pending/Math.max(1,s.queue)*80)+'px" title="Секунда '+h.time+': в очереди '+h.pending+'"><span>'+h.time+'</span></div>').join("")+'</div><div class="load-caption">Высота столбца — очередь после каждого такта. Это не график времени ответа.</div><div class="load-balance">'+s.accepted+' принято = '+s.completed+' выполнено + '+s.pending+' осталось</div>';}
  };
  $("closeProgram").onclick=()=>$("programDialog").close();
  window.addEventListener("hashchange",readRoute);
  document.addEventListener("visibilitychange",()=>{if(document.hidden)stop();});
  document.addEventListener("keydown",e=>{if(!model||!lab||$("programDialog").open||e.ctrlKey||e.metaKey||e.altKey||e.target.closest("input,select,textarea,.lab-scene,.lab-code-body,.lab-journal,.lab-events,.vector-exercise,.sql-trace"))return;if(e.key==="ArrowRight"){e.preventDefault();go(cursor+1);}else if(e.key==="ArrowLeft"){e.preventDefault();go(cursor-1);}else if(e.code==="Space"&&!e.target.closest("button,a,summary")){e.preventDefault();play();}});
  readRoute();
})();
