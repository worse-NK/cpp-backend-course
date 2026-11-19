/* Draw from the teaching model's snapshots; never execute the displayed C++. */
(function (root) {
  "use strict";
  const esc = value => String(value).replace(/[&<>"']/g, c =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const plate = (id, title, diagram, note) =>
    '<figure class="cpp-plate" data-cpp-plate="'+id+'"><figcaption>'+esc(title)+'</figcaption>'+
    diagram+'<p class="cpp-plate-note">'+esc(note)+'</p></figure>';

  // Named slips explain *why* the strong count has this value; a weak edge
  // is shown separately, never as another slip in the balance.
  function account(object, alive, created, count, holders) {
    const status = alive ? "жив" : created ? "уничтожен" : "ещё не создан";
    const slips = holders.map((name,i) => (i?'<span class="cpp-plus" aria-hidden="true">+</span>':'')+
      '<code class="cpp-slip">'+esc(name)+'</code>').join("");
    return '<div class="cpp-account" data-object="'+object+'" data-alive="'+alive+'">'+
      '<div class="cpp-object"><b>'+object+'</b><small>'+status+'</small></div>'+
      '<div class="cpp-balance">'+(slips || '<span class="cpp-empty">нет владельцев</span>')+
      '</div><div class="cpp-total"><b>'+count+'</b><small>всего</small></div></div>';
  }
  function ownership(mode,s) {
    let diagram, note;
    if (s.cycle) {
      const toA=[], toB=[];
      if(s.externalA) toA.push("a");
      if(s.externalB) toB.push("b");
      if(s.linked && s.aliveB && !s.weakBack) toA.push("B.back");
      if(s.linked && s.aliveA) toB.push("A.next");
      diagram=account("A",s.aliveA,s.created,s.countA,toA)+account("B",s.aliveB,s.created,s.countB,toB);
      note=s.linked && s.weakBack && s.aliveB
        ? (s.aliveA?"B.back наблюдает A. Слабая связь не прибавляет долю к строке A.":"B.back ещё существует в B, но A уже уничтожен. Слабая связь его не удержала.")
        : !s.externalA && !s.externalB && s.aliveA ? "Имена a и b больше не удерживают узлы. Прочитай оставшиеся имена в двух строках: каждый узел удерживается полем другого."
        : s.linked && s.aliveA ? "В каждой строке собраны владельцы одного узла. Поле A.next принадлежит A, но удерживает B, поэтому учитывается в строке B."
        : "Каждая строка отвечает на свой вопрос: кто удерживает A и кто удерживает B? Имена появятся рядом с тем узлом, которым они владеют.";
    } else {
      diagram=account("Item",s.alive,s.created,s.strong,s.owners);
      note=mode==="unique" ? (s.observer ? (s.observerValid?"observer видит Item, но в счёт не входит: он не отвечает за удаление объекта.":"observer не обнулился. Живого Item для чтения больше нет.") : "Имя в середине строки указывает, кто сейчас отвечает за удаление Item.")
        : s.weak ? (s.alive?"w не участвует в сумме. Если w.lock() вернёт непустой shared_ptr, в сумме появится ещё один владелец.":"У Item не осталось владельцев. Слабая w ещё существует, но w.lock() уже вернёт пустой shared_ptr.")
        : "Каждая плашка — один shared_ptr, который удерживает тот же Item. Сумма считает владельцев, а не копии объекта.";
    }
    return plate("ownership","Кто удерживает объект",diagram,note);
  }

  const lifetimeKeys={
    owner:{waiting:["idle","—","ещё нет"],alive:["live","●","жив"],destroyed:["end","×","уничтожен"]},
    borrow:{waiting:["idle","—","ссылки ещё нет"],valid:["valid","↗","ссылка пригодна для чтения"],dangling:["bad","!","ссылка не даёт доступа к живому списку"],ended:["end","×","обход закончен"]}
  };
  function band(label, trace, cursor, f) {
    const cells=trace.steps.map((step,i)=>{
      const [tone,sign,title]=i>cursor?["future","","ещё не пройдено"]:f(step.state, i);
      return '<td class="cpp-cell cpp-cell-'+tone+'"'+(i===cursor?' data-now=""':'')+
        ' aria-label="Шаг '+(i+1)+': '+esc(title)+'" title="'+esc(title)+'">'+sign+'</td>';
    }).join("");
    return '<tr><th scope="row">'+esc(label)+'</th>'+cells+'</tr>';
  }
  function historyTable(trace,cursor,rows) {
    return '<table class="cpp-score"><thead><tr><th scope="col">Шаг</th>'+
      trace.steps.map((_,i)=>'<th scope="col"'+(i===cursor?' aria-current="step"':'')+'>'+(i+1)+'</th>').join("")+
      '</tr></thead><tbody>'+rows+'</tbody></table>';
  }
  function temporaries(mode,s,t,i) {
    const name=mode==="parameter"?"values":mode==="named"?"batch":"Batch";
    const rows=band(name,t,i,v=>lifetimeKeys.owner[v.owner])+band("Ссылка",t,i,v=>lifetimeKeys.borrow[v.borrow])+
      band("Чтение",t,i,(v,n)=>{
        const prev=n?t.steps[n-1].state.values.length:0;
        if(v.values.length>prev) return ["read",String(v.values[prev]),"прочитано число "+v.values[prev]];
        if(v.iteration==="blocked")return ["bad","!","чтение недопустимо"];
        return ["idle","·","на этом шаге число не читали"];
      });
    const note=s.borrow==="dangling" ? "× в строке владельца и ! в строке ссылки: списка уже нет. В строке чтения не появится ни одного числа." :
      s.iteration==="finished" ? "Числа 1, 2 и 3 появились до крестика в строке владельца: на каждой итерации список ещё существовал." :
      "Читай по столбцам: ● — владелец жив, ↗ — по ссылке можно читать. Число появится в нижней строке в тот шаг, когда его прочитают.";
    return plate("temporaries","Переживёт ли список чтение?",historyTable(t,i,rows),note);
  }
  function taskownership(mode,s) {
    const items=[["sender","payload"],["queue","queue → p"],["worker","job → p"]];
    const row=items.findIndex(([key])=>s.owner===key);
    const state=s.alive?"жив":s.stage===0?"ещё не создан":"уничтожен";
    const names='<div class="cpp-ports">'+items.map(([key,label])=>
      '<div class="cpp-port" data-connected="'+(s.owner===key)+'"><code>'+label+'</code><i aria-hidden="true"></i></div>').join("")+'</div>';
    const fromY=21+row*42;
    const wire='<svg class="cpp-wire" viewBox="0 0 100 126" preserveAspectRatio="none" aria-hidden="true" focusable="false">'+
      (row===-1?'':'<path d="M0 '+fromY+' C50 '+fromY+' 50 63 95 63"/><path d="M82 56 L96 63 L82 70"/>')+'</svg>';
    const target='<div class="cpp-target" data-alive="'+s.alive+'"><b>Payload</b><span>'+ (s.alive?'id = 42':state)+'</span></div>';
    const diagram='<div class="cpp-patchbay" data-holder="'+s.owner+'">'+names+wire+target+'</div>';
    const note=s.stage===0?"Справа место для одного Payload. Линия появится от имени того указателя, который примет владение.":
      s.owner==="sender"?"payload пока единственный владелец. Справа изображены сами данные, а не копия указателя.":
      s.owner==="queue"?"p — указатель, захваченный командой в очереди. Линия началась в другом месте, но пришла к тем же данным.":
      s.owner==="worker"?(s.ran?"Вызов job() уже закончился, но линия осталась: захваченный указатель всё ещё удерживает Payload.":"Теперь команду хранит job, а не очередь. Указатель внутри команды по-прежнему удерживает тот же Payload."):
      s.ran?"Обёртка освободила команду. Вместе с командой уничтожен захваченный указатель, и Payload больше нет.":
      "Очередь очистили, не вызывая команду. Владение закончилось: Payload уничтожен, хотя работа так и не выполнилась.";
    return plate("taskownership","Один Payload, разные владельцы",diagram,note);
  }
  function build(mode,s,t,i) {
    const products=["core.o","main.o","app"];
    const row=(name)=>band(name,t,i,(v,n)=>{
      const status=v.status[name];
      if(status==="building")return ["read","▶",name==="app"?"идёт линковка":"идёт компиляция"];
      if(status==="dirty")return ["queued","!","ожидает обновления"];
      if(n && t.steps[n-1].state.status[name]==="building")return ["live","✓","получен новый результат"];
      return ["idle","·","результат актуален, команды нет"];
    });
    const work=t.steps.slice(0,i+1).some(step=>products.some(k=>step.state.status[k]==="building"));
    const note=i===t.steps.length-1 && !work ? "Ни одного ▶: README.md не входит в правила этого примера. Старые объектные файлы и программа остались актуальными.":
      "Одна строка — один результат сборки. Точка — он актуален, ! — нужно обновить, ▶ — выполняется команда, ✓ — команда завершилась.";
    return plate("build","Какие файлы пришлось пересобрать?",historyTable(t,i,products.map(row).join("")),note);
  }
  const drawers={ownership,temporaries,taskownership,build};
  root.CourseCppPlates={render(id,mode,state,trace,cursor){
    return Object.prototype.hasOwnProperty.call(drawers,id)?drawers[id](mode,state,trace,cursor):"";
  }};
})(globalThis);
