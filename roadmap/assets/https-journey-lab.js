(function (root) {
  'use strict';
  var model = root.HttpsJourney;
  if (!model || typeof document === 'undefined') return;
  var colors = {local:'#a9bfcc',dns:'#c5b6ed',tcp:'#8fc9ea',tls:'#a6d6ba',http:'#edc78d'};
  var names = {client:'Браузер',router:'Маршрутизатор',resolver:'DNS-резолвер',root:'Корневой DNS',tld:'DNS зоны .com',authority:'DNS example.com',server:'Сервер сайта'};
  var badges = {local:'В браузере',dns:'DNS',tcp:'TCP',tls:'TLS 1.3',http:'HTTP / TLS'};
  var scenario = 'normal', index = 0, view = 'network', panel = 'explain', timer = null, context = null;
  var reduced = root.matchMedia ? root.matchMedia('(prefers-reduced-motion: reduce)') : {matches:false};
  var el = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];}); };
  var steps = function () { return model.getSteps(scenario); };
  var color = function (step) { return colors[step.protocol] || colors.local; };
  var networkEvent = function (step) { return !!(step.from && step.to); };
  function revealDetails(focus) {
    if(focus)el('step-title').focus({preventScroll:true});
    document.querySelector('.workspace').scrollIntoView({block:'start',behavior:'auto'});
  }
  function parseHash() {
    var p = new URLSearchParams(root.location.hash.slice(1));
    var s = p.get('scenario');
    scenario = model.scenarios.some(function(x){return x.id===s;}) ? s : 'normal';
    var lab=(root.COURSE_LABS||[]).find(function(item){return item.id==='https-journey';});
    context=lab?(lab.entries.find(function(entry){return entry.station===p.get('from')&&entry.section===p.get('section');})||null):null;
    var phaseIndex=steps().findIndex(function(step){return step.phase===p.get('phase');});
    var n = p.has('step') ? Number(p.get('step')) : Math.max(0,phaseIndex);
    index = Number.isFinite(n) ? Math.max(0,Math.min(steps().length-1,Math.floor(n))) : 0;
    view = p.get('view') === 'sequence' ? 'sequence' : 'network';
    panel = p.get('panel') === 'fields' ? 'fields' : 'explain';
  }
  function writeHash(replace) {
    var hash = '#scenario='+scenario+'&step='+index+'&view='+view+'&panel='+panel;
    if(context)hash+='&from='+encodeURIComponent(context.station)+'&section='+encodeURIComponent(context.section);
    if (root.location.hash !== hash) root.history[replace?'replaceState':'pushState'](null,'',hash);
  }
  function stop() {
    if (timer !== null) { root.clearInterval(timer); timer=null; }
    el('play').textContent='▶ Авто'; el('play').setAttribute('aria-pressed','false');
  }
  function setStep(n, options) {
    options=options||{};
    index=Math.max(0,Math.min(steps().length-1,n));
    if (!options.auto) stop();
    writeHash(!!options.replace);
    render(!options.noAnimation);
    if(index===steps().length-1) stop();
  }
  function pathFor(from,to) {
    var paths={
      'client:resolver':'M 160 278 L 340 278 Q 360 278 360 258 L 360 158',
      'resolver:client':'M 360 158 L 360 258 Q 360 278 340 278 L 160 278',
      'client:server':'M 160 278 L 690 278',
      'server:client':'M 690 278 L 160 278',
      'resolver:root':'M 399 118 Q 445 90 490 108',
      'root:resolver':'M 490 108 Q 445 90 399 118',
      'resolver:tld':'M 399 118 Q 505 174 610 108',
      'tld:resolver':'M 610 108 Q 505 174 399 118',
      'resolver:authority':'M 399 118 Q 565 210 740 108',
      'authority:resolver':'M 740 108 Q 565 210 399 118'
    };
    return paths[from+':'+to] || '';
  }
  var defs = '<defs>'+
    '<symbol id="journey-laptop" viewBox="0 0 116 105"><path class="node-side" d="M12 10 79 0 79 61 12 72Z"/><path class="node-front" d="M17 14 73 6 73 57 17 66Z"/><path class="node-line" d="M23 21 66 15 66 50 23 56Z"/><path class="node-top" d="m12 72 67-11 29 22-69 16Z"/><path class="node-side" d="m12 72 27 27 69-16v5l-70 17L12 78Z"/><path class="node-line" d="m25 76 48-8 19 14-49 10Z M34 74l17 15m-8-17 18 15m-9-16 17 14m-35-7 48-9m-41 15 48-9"/></symbol>'+
    '<symbol id="journey-router" viewBox="0 0 112 100"><path class="node-top" d="m8 48 57-14 39 21-60 17Z"/><path class="node-front" d="m8 48 36 24v22L8 70Z"/><path class="node-side" d="m44 72 60-17v22L44 94Z"/><path class="node-line" d="M27 46V9m50 28V3M20 60l15 10M53 78l7-2m6-2 7-2m6-2 7-2"/><circle class="node-light" cx="94" cy="67" r="2.5"/><path class="node-line" d="m43 53 18-5m-5-2 5 2-3 5m-9 9-10-7m0 5v-5l5-1"/></symbol>'+
    '<symbol id="journey-server" viewBox="0 0 90 112"><path class="node-top" d="m12 12 42-10 25 16-43 12Z"/><path class="node-front" d="m12 12 24 18v78l-24-19Z"/><path class="node-side" d="m36 30 43-12v78l-43 12Z"/><path class="node-line" d="m18 28 12 9m-12 7 12 9m-12 7 12 9m-12 7 12 9M44 40l27-7m-27 19 27-7m-27 19 27-7m-27 19 27-7m-27 19 27-7"/><circle class="node-light" cx="66" cy="90" r="2"/></symbol>'+
    '<symbol id="journey-dns" viewBox="0 0 90 90"><path class="node-top" d="m7 20 43-13 33 18-45 15Z"/><path class="node-front" d="m7 20 31 20v17L7 37Z"/><path class="node-side" d="m38 40 45-15v18L38 57Z"/><path class="node-top" d="m7 45 31 19 45-15v18L38 82 7 62Z"/><path class="node-line" d="m14 31 15 9m-15 17 15 9m18-18 27-9m-27 34 27-9"/><circle class="node-light" cx="69" cy="33" r="2"/><circle class="node-light" cx="69" cy="59" r="2"/></symbol>'+
    '<symbol id="journey-record" viewBox="0 0 62 76"><path class="node-top" d="m9 12 26-8 19 12-28 9Z"/><path class="node-front" d="m9 12 17 13v45L9 56Z"/><path class="node-side" d="m26 25 28-9v46l-28 8Z"/><path class="node-line" d="m32 34 16-5m-16 14 16-5m-16 14 16-5"/></symbol>'+
    '<marker id="journey-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0 7 3.5 0 7" fill="none" stroke="context-stroke" stroke-width="1.3"/></marker></defs>';
  // Presentation attributes survive SVG <use> shadow trees in every target.
  defs=defs.replace(/class="node-(front|top|side|line|light)"/g,function(match,kind){
    var fills={front:'#2b4657',top:'#3a5d72',side:'#203743',line:'none',light:'#b1e3ca'};
    return match+' fill="'+fills[kind]+'"'+(kind==='light'?'':' stroke="'+(kind==='line'?'#a2cce2':'#85b3cb')+'" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"');
  });
  function device(id, icon, x, y, w, h, title, address, active, muted) {
    return '<g class="'+(muted?'node-muted':'')+'" transform="translate('+x+' '+y+')">'+
      (active?'<ellipse class="node-halo" cx="'+w/2+'" cy="'+h*.65+'" rx="'+(w*.78)+'" ry="'+(h*.7)+'"/>':'')+
      '<use href="#journey-'+icon+'" width="'+w+'" height="'+h+'"/>'+
      '<text class="node-name" x="'+w/2+'" y="'+(h+24)+'" text-anchor="middle">'+esc(title)+'</text>'+
      '<text class="node-address" x="'+w/2+'" y="'+(h+45)+'" text-anchor="middle">'+esc(address)+'</text></g>';
  }
  function drawNetwork(step,state,animate) {
    var dns=step.phase==='dns';
    var hierarchy=dns && scenario!=='cached';
    var from=step.from,to=step.to,path=pathFor(from,to);
    var active=function(id){return from===id||to===id||(!from&&id==='client');};
    var svg='<svg class="network-svg" viewBox="0 0 880 420" role="img" aria-labelledby="network-title network-description" style="--protocol-color:'+color(step)+'">'+
      '<title id="network-title">'+esc(networkEvent(step)?names[from]+' → '+names[to]+': '+step.label:step.title)+'</title>'+
      '<desc id="network-description">Клиент связан с DNS-резолвером и сервером через маршрутизатор. Резолвер отдельно спрашивает корневой, com и авторитетный DNS-серверы. Линии — логические пути, не все промежуточные устройства.</desc>'+defs;
    for(var gy=35;gy<410;gy+=32) svg+='<path class="grid-line" d="M 0 '+gy+' H 880"/>';
    for(var gx=24;gx<880;gx+=44) svg+='<path class="grid-line" d="M '+gx+' 0 V 420"/>';
    svg+='<rect class="zone" x="445" y="18" width="375" height="172" rx="22"/>'+
      '<text class="zone-label" x="464" y="42">ПОИСК В DNS · если готового ответа нет</text>'+
      '<path class="link" d="M160 278H690 M360 278V158 M399 118Q445 90 490 108 M399 118Q505 174 610 108 M399 118Q565 210 740 108"/>';
    if(path) svg+='<path class="link-active" d="'+path+'" marker-end="url(#journey-arrow)"/>';
    svg+=device('client','laptop',58,205,116,105,'Браузер','192.0.2.10',active('client'),false)+
      device('router','router',306,211,112,100,'Маршрутизатор','готовый маршрут',false,false)+
      device('resolver','dns',314,55,90,90,'DNS-резолвер','198.51.100.53',active('resolver'),!dns)+
      device('root','record',468,60,62,76,'Корень','делегирует .com',active('root'),!hierarchy)+
      device('tld','record',588,60,62,76,'.com','делегирует зону',active('tld'),!hierarchy)+
      device('authority','record',718,60,62,76,'example.com','запись A',active('authority'),!hierarchy)+
      device('server','server',686,205,90,112,'Сервер сайта','203.0.113.20',active('server'),dns);
    var screen=state.rendered?'Hello!':state.failed?'Стоп':'…';
    svg+='<text x="104" y="248" text-anchor="middle" fill="'+(state.failed?'#f2ada5':'#c4e7f7')+'" font-size="'+(state.rendered?10:14)+'" transform="rotate(-8 104 248)">'+screen+'</text>';
    if(path&&animate&&!reduced.matches) svg+='<g aria-hidden="true"><rect class="packet-envelope" x="-14" y="-9" width="28" height="18" rx="4"/><path class="packet-glyph" d="m-10-5 10 7 10-7"/><animateMotion dur="1.25s" repeatCount="1" fill="freeze" path="'+path+'"/></g>';
    svg+='</svg>';
    if(networkEvent(step)) svg+='<button type="button" class="scene-inspect" data-inspect="true" aria-label="Разобрать сообщение '+esc(step.label)+'"><span aria-hidden="true">▱</span> '+esc(step.label)+' <span aria-hidden="true">↗</span></button>';
    el('scene').innerHTML='<p class="scene-scroll-hint">Схему можно прокрутить вбок. Пояснение шага — ниже.</p>'+svg;
    var packet=el('scene').querySelector('[data-inspect]');
    if(packet)packet.addEventListener('click',showFields);
  }
  function drawSequence(list) {
    var columns={client:0,resolver:1,root:2,tld:2,authority:2,server:3};
    var html='<div class="sequence-wrap"><div class="sequence-actors"><span>Браузер</span><span>Резолвер</span><span>Иерархия DNS</span><span>Сайт</span></div>';
    if(!list.slice(0,index+1).some(networkEvent))html+='<p class="sequence-note">Сетевых сообщений ещё нет. На этом шаге браузер работает локально.</p>';
    list.slice(0,index+1).forEach(function(step,i){
      if(!networkEvent(step)) return;
      var a=columns[step.from],b=columns[step.to],left=Math.min(a,b)*25+12.5,width=Math.abs(b-a)*25;
      html+='<button type="button" class="sequence-row" data-sequence-step="'+i+'" '+(i===index?'aria-current="step" ':'')+'aria-label="Шаг '+(i+1)+': '+esc(names[step.from]+' → '+names[step.to]+', '+step.label)+'" style="--protocol-color:'+color(step)+'"><span class="sequence-arrow '+(b<a?'reverse':'')+'" style="margin-left:'+left+'%;width:'+width+'%"><span class="sequence-label">'+esc(step.label)+'</span></span></button>';
    });
    html+='<p class="sequence-note">Показаны уже пройденные сообщения. Расстояния между строками не означают измеренную задержку. Последовательность внутри блока TLS может объединять несколько сообщений.</p></div>';
    el('scene').innerHTML=html;
    el('scene').querySelectorAll('[data-sequence-step]').forEach(function(button){button.addEventListener('click',function(){setStep(Number(button.dataset.sequenceStep),{noAnimation:true});revealDetails(true);});});
  }
  function renderPhases(list,step) {
    var current=model.phases.findIndex(function(p){return p.id===step.phase;});
    el('phases').innerHTML=model.phases.map(function(p,n){
      var first=list.findIndex(function(s){return s.phase===p.id;});
      var count=list.filter(function(s){return s.phase===p.id;}).length;
      var shortTitles=['Начало','Адрес','Связь','Защита','Страница'];
      return '<button type="button" class="phase '+(n<current?'is-done':'')+'" data-phase="'+esc(p.id)+'" aria-label="Этап '+(n+1)+': '+esc(p.title)+'" '+(p.id===step.phase?'aria-current="step" ':'')+(first<0?'disabled ':'')+'><span class="phase-number">'+(n<current?'✓':n+1)+'</span><span><strong>'+esc(p.title)+'</strong><span class="phase-short" aria-hidden="true">'+shortTitles[n]+'</span><small>'+count+' '+(count===1?'шаг':count>=2&&count<=4?'шага':'шагов')+'</small></span></button>';
    }).join('');
    el('phases').querySelectorAll('[data-phase]').forEach(function(b){b.addEventListener('click',function(){panel='explain';setStep(list.findIndex(function(s){return s.phase===b.dataset.phase;}));revealDetails(true);});});
  }
  function renderDetails(step) {
    el('step-title').textContent=step.title;
    var sources=(step.sourceIds||[]).map(function(id){return model.sources.find(function(s){return s.id===id;});}).filter(Boolean);
    el('explanation').innerHTML='<p class="step-summary">'+esc(step.summary)+'</p>'+(step.paragraphs||[]).map(function(p){return '<p>'+esc(p)+'</p>';}).join('')+
      '<div class="changed-box"><h4>Что изменилось</h4><p>'+esc(step.changed)+'</p></div>'+
      '<div class="visible-box"><h4>Что видно наблюдателю в сети</h4><p>'+esc(step.visible)+'</p></div>'+
      '<div class="step-sources">'+sources.map(function(s){return '<a href="'+esc(s.url)+'" target="_blank" rel="noopener noreferrer">'+esc(s.title)+' ↗</a>';}).join('')+'</div>';
    var fields=step.fields||[];
    el('fields').innerHTML='<p class="field-intro">Здесь выбранные поля и смысл сообщения, а не полный байтовый пакет. Если содержимое зашифровано, оно показано после расшифрования участником обмена.</p>'+fields.map(function(layer){return '<section class="field-layer"><h4>'+esc(layer.title||layer.layer)+'</h4><dl>'+layer.items.map(function(item){return '<dt>'+esc(item[0])+'</dt><dd><span class="field-value">'+esc(item[1])+'</span><span class="field-meaning">'+esc(item[2])+'</span></dd>';}).join('')+'</dl></section>';}).join('')+
      (!fields.length?'<p class="field-intro">На этом шаге браузер работает локально. Нового сетевого сообщения нет.</p>':'');
    el('explanation').hidden=panel!=='explain'; el('fields').hidden=panel!=='fields';
    document.querySelectorAll('[data-panel]').forEach(function(b){b.setAttribute('aria-pressed',String(b.dataset.panel===panel));});
  }
  function renderState(state) {
    var rows=[['Адрес сайта',state.address,state.addressKnown],['Соединение TCP',state.transport,state.tcpReady],['Защита TLS',state.security,state.tlsReady]];
    el('participant-state').innerHTML=rows.map(function(x){return '<div class="state-item '+(x[2]?'is-ready':'')+'"><span>'+esc(x[0])+'</span>'+esc(x[1])+'</div>';}).join('')+'<div class="page-status '+(state.rendered?'is-ready':'')+(state.failed?' is-failed':'')+'"><span>В браузере</span><strong>'+esc(state.page)+'</strong></div>';
  }
  function renderJournal(list) {
    var messages=list.slice(0,index+1).map(function(step,i){return {step:step,i:i};}).filter(function(x){return networkEvent(x.step);});
    var count=messages.length,tail=count%100;
    el('journal-count').textContent=count+' '+(tail>=11&&tail<=14?'сообщений':count%10===1?'сообщение':count%10>=2&&count%10<=4?'сообщения':'сообщений');
    el('journal').innerHTML=messages.length?messages.map(function(x){return '<button type="button" class="journal-entry" data-journal-step="'+x.i+'" '+(x.i===index?'aria-current="step" ':'')+'style="--protocol-color:'+color(x.step)+'"><span class="entry-index">'+String(x.i+1).padStart(2,'0')+'</span><span class="entry-protocol">'+esc(x.step.protocol.toUpperCase())+'</span><span class="entry-label">'+esc(names[x.step.from]+' → '+names[x.step.to])+'<br>'+esc(x.step.label)+'</span></button>';}).join(''):'<p class="journal-empty">На пройденных шагах сетевых сообщений пока не было.</p>';
    el('journal').querySelectorAll('[data-journal-step]').forEach(function(b){b.addEventListener('click',function(){panel='fields';setStep(Number(b.dataset.journalStep),{noAnimation:true});revealDetails(true);});});
  }
  function render(animate) {
    var list=steps(),step=list[index],state=model.getState(scenario,index);
    var back=context?context.file+'#section='+encodeURIComponent(context.section):'cpp_station7_networking.html#section=url-to-service';
    el('return-to-section').href=back;el('return-to-theory').href=back;
    el('return-to-section').textContent=context?'← Вернуться к теме':'← К сетевой главе';
    el('return-to-theory').textContent=context?'Вернуться к теме в учебнике →':'Разобрать путь запроса в учебнике →';
    el('experiment').style.setProperty('--protocol-color',color(step));
    el('scenario').value=scenario;
    el('scenario-description').textContent=model.scenarios.find(function(s){return s.id===scenario;}).description;
    renderPhases(list,step);
    if(view==='sequence')drawSequence(list);else drawNetwork(step,state,animate);
    renderDetails(step); renderState(state); renderJournal(list);
    el('message-direction').textContent=networkEvent(step)?names[step.from]+' → '+names[step.to]:'Локальное действие · без нового сообщения';
    el('message-label').textContent=networkEvent(step)?step.label:step.title;
    el('inspect-message').disabled=!(step.fields&&step.fields.length);
    el('step-counter').textContent='Шаг '+(index+1)+' из '+list.length;
    el('protocol-badge').textContent=badges[step.protocol]||step.protocol;
    el('range-label').textContent='Шаг '+(index+1)+' из '+list.length;
    el('step-range').max=String(list.length-1);el('step-range').value=String(index);
    el('step-range').setAttribute('aria-valuetext',step.title);
    el('previous').disabled=index===0;el('reset').disabled=index===0;
    el('next').disabled=index===list.length-1;
    el('next').textContent=index===list.length-1?(state.failed?'Проверка остановлена':'Страница открыта ✓'):'Следующий шаг →';
    el('play').disabled=index===list.length-1;
    document.querySelectorAll('[data-view]').forEach(function(b){b.setAttribute('aria-pressed',String(b.dataset.view===view));});
    el('announcement').textContent='Шаг '+(index+1)+'. '+step.title+'. '+step.changed;
  }
  function showFields() { stop();panel='fields';writeHash(false);render(false);document.querySelector('[data-panel="fields"]').focus({preventScroll:true}); }
  el('next').addEventListener('click',function(){setStep(index+1);revealDetails(this.disabled);});
  el('previous').addEventListener('click',function(){setStep(index-1);revealDetails(this.disabled);});
  el('reset').addEventListener('click',function(){panel='explain';setStep(0);el('step-title').focus({preventScroll:true});});
  el('step-range').addEventListener('input',function(){setStep(Number(this.value),{replace:true});});
  el('inspect-message').addEventListener('click',showFields);
  el('scenario').addEventListener('change',function(){stop();scenario=this.value;index=0;panel='explain';writeHash(false);render(false);});
  document.querySelectorAll('[data-view]').forEach(function(b){b.addEventListener('click',function(){stop();view=b.dataset.view;writeHash(false);render(false);});});
  document.querySelectorAll('[data-panel]').forEach(function(b){b.addEventListener('click',function(){stop();panel=b.dataset.panel;writeHash(false);render(false);});});
  el('play').addEventListener('click',function(){
    if(timer!==null){stop();return;}
    if(index>=steps().length-1)return;
    el('play').textContent='Ⅱ Пауза';el('play').setAttribute('aria-pressed','true');
    timer=root.setInterval(function(){setStep(index+1,{auto:true,replace:true});},5000);
  });
  document.querySelector('.start-button').addEventListener('click',function(e){e.preventDefault();stop();scenario='normal';index=0;view='network';panel='explain';writeHash(false);render(false);el('experiment').scrollIntoView({behavior:reduced.matches?'auto':'smooth',block:'start'});el('experiment').focus({preventScroll:true});});
  document.querySelector('.skip-link').addEventListener('click',function(e){e.preventDefault();el('experiment').scrollIntoView({behavior:'auto',block:'start'});el('experiment').focus({preventScroll:true});});
  root.addEventListener('hashchange',function(){stop();parseHash();render(false);});
  root.addEventListener('popstate',function(){stop();parseHash();render(false);});
  document.addEventListener('visibilitychange',function(){if(document.hidden)stop();});
  document.addEventListener('keydown',function(e){
    if(e.altKey||e.ctrlKey||e.metaKey||e.shiftKey)return;
    if(e.target.closest('button,a,input,select,textarea,summary,[contenteditable="true"],#scene'))return;
    if(e.key==='ArrowRight'){e.preventDefault();setStep(index+1);}
    if(e.key==='ArrowLeft'){e.preventDefault();setStep(index-1);}
  });
  el('assumptions').innerHTML=model.assumptions.map(function(p){return '<p>'+esc(p)+'</p>';}).join('');
  el('sources').innerHTML=model.sources.map(function(s){return '<article><a href="'+esc(s.url)+'" target="_blank" rel="noopener noreferrer">'+esc(s.title)+' ↗</a><p>'+esc(s.description)+'</p></article>';}).join('');
  parseHash();render(false);
}(typeof window==='undefined'?globalThis:window));
