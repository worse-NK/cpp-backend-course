/* Views of the existing teaching traces. No timers, requests or extra model state. */
(function (global) {
  "use strict";
  const esc = v => String(v).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const past = (trace, i) => trace.steps.slice(0, i + 1);
  const blank = v => v == null ? "—" : esc(v);
  const figure = (kind, title, body, note) =>
    '<figure class="svc-plate svc-' + kind + '" data-service-plate="' + kind + '"><figcaption>' +
    esc(title) + '</figcaption>' + body + '<p class="svc-note">' + esc(note) + '</p></figure>';
  const label = v => '<div class="svc-label">' + esc(v) + '</div>';
  const stat = (title, value, hint, mark = "") => '<div class="svc-stat '+mark+'"><span>' +
    esc(title) + '</span><strong>' + blank(value) + '</strong><small>' + esc(hint) + '</small></div>';
  const empty = v => '<p class="svc-empty">' + esc(v) + '</p>';

  function concurrency(mode, s, trace, cursor) {
    const ops = mode === "mutex" ? ["lock","читать","прибавить","записать","unlock"] :
      mode === "rmw" ? ["fetch_add"] : ["load","прибавить","store"];
    const thread = w => stat("Поток " + w, s.locals[w], s.blocked[w] ? "ждёт замок" :
      s.pc[w] === ops.length ? "закончил" : "далее: " + ops[s.pc[w]], "svc-local");
    const strip = '<div class="svc-registers">' + thread("A") +
      stat("Общий", s.value, "counter", "svc-shared") + thread("B") + '</div>';
    const history = past(trace, cursor);
    const rows = history.slice(1).map((step,i) => {
      const st = step.state, prev = history[i].state, who = st.last;
      if (!who) return "";
      const op = ops[prev.pc[who]];
      const action = st.pc[who] === prev.pc[who] ? "ждёт замок" :
        op === "fetch_add" ? "fetch_add: " + prev.value + " → " + st.value :
        op === "lock" ? "взял замок" : op === "unlock" ? "вернул замок" :
        op === "прибавить" ? "+1 у себя" :
        op === "store" || op === "записать" ? "записал " + st.value : "прочитал " + st.locals[who];
      const mark = '<span class="svc-event svc-who-' + who + '"><span class="svc-sr">Поток '+who+': </span>' + esc(action) + '</span>';
      return '<li class="svc-beat"><span>' + (who==="A"?mark:"") +
        '</span><b aria-label="Общий счётчик: '+st.value+'">'+st.value+'</b><span>'+
        (who==="B"?mark:"")+'</span></li>';
    });
    const note = mode === "rmw" ? "Один вызов fetch_add увеличивает общий счётчик, а потоку возвращает прежнее значение." :
      mode === "mutex" ? "Оба потока используют один замок. Пока один держит его, другой не может прочитать счётчик под этим замком." :
      s.pc.A === ops.length && s.pc.B === ops.length && s.value === 1 ? "Оба потока записали единицу: каждый прибавил к своей копии нуля. В общем счётчике осталось одно увеличение вместо двух." :
      "Чтение копирует число из середины в поток. Прибавление меняет только эту копию; общий счётчик меняется при записи.";
    return figure("threads", "У каждого потока своя копия", strip +
      (mode==="mutex"?label(s.lock?"Замок у потока "+s.lock:"Замок свободен"):"") + label("Последние ходы · A / счётчик / B") +
      (rows.length ? '<ol class="svc-beats" start="'+Math.max(1,rows.length-3)+'">'+rows.slice(-4).join("")+'</ol>' :
        empty("Нажми «Шаг потока A» или «Шаг потока B», чтобы увидеть первое действие.")), note);
  }

  const hex = n => n.toString(16).padStart(2,"0").toUpperCase();
  function stream(mode, s) {
    const consumed = s.received - s.buffer.length;
    const cells = s.wire.map((n,i) => {
      const prefix = i === 0 || (mode !== "oversize" && i === 4);
      const phase = i < consumed ? "разобран" : i < s.received ? "в буфере" : "не прочитан";
      return '<span class="svc-byte '+(prefix?"prefix ":"")+
        (i < consumed ? "svc-parsed" : i < s.received ? "svc-buffer" : "svc-future")+'"><b>'+hex(n)+'</b><small>'+
        (prefix?'длина':esc(String.fromCharCode(n)))+'</small><span class="svc-sr">'+phase+'</span></span>';
    }).join("");
    let start = 0;
    const readings = s.chunks.map((size,i) => {
      const count = Math.min(size,Math.max(0,s.received-start));
      start += size;
      return count ? '<span class="svc-brace svc-read" data-size="'+count+'" aria-label="Чтение '+(i+1)+': байт — '+count+'">№'+(i+1)+'</span>' : "";
    }).join("");
    const records = s.messages.map((msg,i) => '<span class="svc-brace svc-record" data-size="'+(msg.length+1)+'" aria-label="Запись '+(i+1)+': '+esc(msg)+'">'+esc(msg||"пусто")+'</span>').join("");
    const grid = h => '<div class="svc-byte-grid" data-width="'+s.wire.length+'">'+h+'</div>';
    const state = s.rejected ? "Отказ: длина "+s.expected+" больше допустимых 5." :
      s.expected === null ? (s.buffer.length ? "Следующим будет прочитан байт длины." : "Парсер ждёт начало следующей записи.") :
      "Байтов для текущего тела: "+Math.min(s.buffer.length,s.expected)+" из "+s.expected+".";
    return figure("stream","Где заканчивается чтение, а где — запись",label("Байты из примера · слева направо")+grid(cells)+
      label("Что уже прочитали из сокета")+(readings?grid(readings):empty("Ещё не читали"))+
      label("Какие записи уже разобрали")+(records?grid(records):empty(s.rejected?"Запись отклонена":"Пока ни одной"))+
      '<p class="svc-inline"><b>Буфер:</b> '+(s.buffer.length?s.buffer.map(hex).join(" "):"пуст")+' · '+esc(state)+'</p>',
      "На двух полосах одни и те же позиции. В каждой записи первый байт задаёт длину, остальные — её текст. Полоса чтения может оборваться посреди записи.");
  }

  function exchange(mode,s,trace,cursor) {
    const messages = past(trace,cursor).filter(e => e.state.message);
    const events = messages.map((e,i) => {
      const st = e.state, timeout = st.lost && i > 0 && messages[i-1].state.lost;
      const direction = timeout ? "У клиента" : st.lost ? "Ответ потерян" : st.direction === "right" ? "Запрос" : "Ответ";
      return '<li class="svc-exchange-row'+(st.lost?' svc-lost':'')+'"><span>'+esc(direction)+'</span>'+
        (timeout?'<i class="svc-clock" aria-hidden="true">◷</i>':
        '<span class="svc-route svc-to-'+(st.lost?'lost':st.direction)+'" aria-hidden="true"><i class="edge '+(st.lost?'weak':'strong')+'"></i></span>')+
        '<strong>'+esc(st.message)+'</strong></li>';
    }).join("");
    const facts = '<div class="svc-facts"><div><b>Что знает клиент</b><span>'+esc(s.client)+'</span></div><div><b>Что хранит сервис</b><span>'+
      esc(s.server)+(s.key?'; результат K '+(s.record?'сохранён':'ещё не записан'):'')+'</span></div></div>';
    return figure("http", mode === "version" ? "Два редактора, одна версия задачи" : "Отправить ответ не значит доставить его",
      '<div class="svc-endpoints"><span>Клиент</span><span>Сервис</span></div>'+
      (events?'<ol class="svc-exchange">'+events+'</ol>':empty("Пока обмена на схеме нет. Сделай следующий шаг."))+facts,
      mode === "version" ? "Оба редактора начали с v7. Смотри, совпадает ли версия из очередного запроса с версией на сервере." :
      "Стрелка вправо — команда сервису, влево — ответ клиенту. Крестик отмечает потерю ответа в этом примере, а не отмену операции.");
  }

  function transactions(mode,s,trace,cursor) {
    if(s.snapshot) {
      const reads = past(trace,cursor).filter(e => e.line===2 || e.line===8);
      const read = (i,n) => '<div class="svc-select"><b>'+n+' SELECT</b><strong>'+blank(reads[i]?.state.a)+
        '</strong><small>'+(reads[i]?"прочитано":"ещё не выполнен")+'</small></div>';
      const rule = mode==="rr"?"В этой транзакции A оба SELECT читают один снимок.":"Для каждого SELECT в A берётся новый снимок.";
      return figure("versions","Какую версию строки видит A",
        '<div class="svc-db-head"><span>Сейчас зафиксировано в базе</span><strong>'+s.database+'</strong></div>'+
        label("Два чтения сессии A")+'<div class="svc-version-track">'+read(0,"Первый")+
        '<span class="svc-commit '+(s.b===null?'':'did-commit')+'">'+
        (s.b===null?"B: ещё нет записи":"B: COMMIT<br>110")+'</span>'+
        read(1,"Второй")+'</div>',rule+" Здесь A сама ничего не записывает.");
    }
    const forB = s.waiting && !s.lock ? "блокировка снята; UPDATE ещё не завершён" : s.bStatus;
    const who = (id,v,status) => '<div class="svc-session">'+label("Сессия "+id)+'<b>'+esc(status)+'</b><span>'+
      (v===null?'Нет незавершённой записи':'Незавершённая запись: '+v)+'</span></div>';
    return figure("reservation","Кто получил последнее место",
      '<div class="svc-db-head"><span>Свободных мест по зафиксированным данным</span><strong>'+s.database+'</strong></div>'+
      '<div class="svc-sessions">'+who("A",s.a,s.aStatus)+who("B",s.b,forB)+'</div>'+
      '<div class="svc-inline"><b>Блокировка строки:</b> '+(s.lock?"у сессии "+s.lock:"свободна")+
      ' · <b>Подтверждённых броней:</b> '+s.winners+'</div>',
      "Число 0 в незавершённой записи означает «мест больше нет». Бронь становится подтверждённой после COMMIT, а не сразу после UPDATE.");
  }

  function load(mode,s) {
    const high = Math.max(s.queue,s.rate,1);
    const strip = (name,key,tone) => {
      let marks = "";
      for(let t=1;t<=10;t++) {
        const h = s.history[t-1], x = (t-1)*10+2;
        if(!h)continue;
        const val = h[key], height = 46*val/high;
        marks += val ? '<rect x="'+x+'" y="'+(50-height)+'" width="6" height="'+height+'"/>' :
          '<line x1="'+x+'" x2="'+(x+6)+'" y1="50" y2="50"/>';
      }
      const boundary = mode==="drain" && s.time>=7 ? '<path class="svc-shutdown" d="M60 1V54"/>' : "";
      return '<div class="svc-series '+tone+'"><div class="svc-series-title"><b>'+esc(name)+'</b><strong>'+
        (s.time?s.history[s.history.length-1][key]:"—")+'</strong></div><svg viewBox="0 0 100 55" preserveAspectRatio="none" aria-hidden="true">'+
        '<path class="svc-grid" d="M0 4H100 M0 27H100 M0 50H100"/>'+marks+boundary+'</svg></div>';
    };
    const status = s.phase==="Serving"?"приём открыт":s.phase==="Draining"?"разбираем остаток":"приём закрыт, очередь пуста";
    return figure("load","Что происходит с очередью и отказами",label("Секунда "+s.time+" · "+status)+
      '<div class="svc-chart">'+strip("Ждут в конце секунды","pending","svc-queue")+strip("Отказы за секунду","rejected","svc-refused")+
      '<div class="svc-axis" aria-hidden="true">'+Array.from({length:10},(_,i)=>'<span>'+(i+1)+'</span>').join("")+'</div></div>'+
      '<div class="svc-inline"><b>За последнюю секунду:</b> принято '+s.lastAccepted+', выполнено '+s.lastCompleted+
      '. <b>За весь опыт:</b> принято '+s.accepted+' = выполнено '+s.completed+' + ждут '+s.pending+'; отказов '+s.rejected+'.</div>',
      'Одинаковая высота на обеих шкалах означает одно и то же число задач: от 0 до '+high+'. Черта вместо столбца означает ноль; пустое место — секунда ещё не наступила.'+
      (mode==="drain" && s.time>=7?' Пунктир — закрытие приёма перед седьмой секундой.':''));
  }
  global.CourseServicePlates = Object.freeze({render(id,mode,state,trace,cursor) {
    if(id==="concurrency") return concurrency(mode,state,trace,cursor);
    if(id==="network") return state.api ? exchange(mode,state,trace,cursor) : stream(mode,state);
    if(id==="transactions") return transactions(mode,state,trace,cursor);
    if(id==="overload") return load(mode,state);
    return "";
  }});
})(typeof window==="undefined"?globalThis:window);
