(function (root) {
  'use strict';
  var $=function(id){return document.getElementById(id);};
  var esc=function(value){return String(value==null?'':value).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});};
  var config=JSON.parse($('network-lab-config').textContent), registry=root.NetworkLabModels||{}, model=registry[config.id];
  if(!model){$('intro-paragraphs').textContent='Данные лаборатории не загрузились. Открой страницу вместе с папкой assets или вернись к тексту учебника.';return;}
  var catalog=(root.COURSE_LABS||[]).find(function(lab){return lab.id===config.id;});
  var defaultBack=$('return-to-section').getAttribute('href');
  var colors={local:'#a9bfcc',tcp:'#8fc9ea',udp:'#8fc9ea',dns:'#c5b6ed',ip:'#98c6db',arp:'#edc78d',dhcp:'#c5b6ed',icmp:'#edc78d',vpn:'#a6d6ba',tls:'#a6d6ba',http:'#edc78d'};
  var tones=['normal','good','warn','bad'];
  var statusNames={waiting:'Ещё не отправлено',sent:'Отправлено',acked:'Подтверждено TCP',buffered:'Ждёт в буфере',missing:'Пока отсутствует',delivered:'Получено',blocked:'Передача остановлена'};
  var scenario=model.scenarios[0].id,index=0,view='network',panel='explain',context=null,timer=null;
  var reduced=root.matchMedia?root.matchMedia('(prefers-reduced-motion: reduce)'):{matches:false};
  function list(){return model.getSteps(scenario);}
  function tone(value){return tones.indexOf(value)>=0?value:'normal';}
  function color(step){return colors[step.protocol]||colors.local;}
  function isMessage(step){return !!(step.from&&step.to);}
  function nodeName(id){var node=model.getTopology(scenario).nodes.find(function(n){return n.id===id;});return node?node.title:String(id||'');}
  function direction(step){return step.direction||(isMessage(step)?nodeName(step.from)+' → '+nodeName(step.to):'Локальное действие');}
  function parse(){
    var p=new URLSearchParams(root.location.hash.slice(1)),selected=p.get('scenario');
    scenario=model.scenarios.some(function(s){return s.id===selected;})?selected:model.scenarios[0].id;
    context=catalog?(catalog.entries.find(function(e){return e.station===p.get('from')&&e.section===p.get('section');})||null):null;
    var phase=list().findIndex(function(s){return s.phase===p.get('phase');});
    var n=p.has('step')?Number(p.get('step')):Math.max(0,phase);
    index=Number.isFinite(n)?Math.max(0,Math.min(list().length-1,Math.floor(n))):0;
    view=p.get('view')==='sequence'?'sequence':'network';panel=p.get('panel')==='fields'?'fields':'explain';
  }
  function route(replace){
    var hash='#scenario='+encodeURIComponent(scenario)+'&step='+index+'&view='+view+'&panel='+panel;
    if(context)hash+='&from='+encodeURIComponent(context.station)+'&section='+encodeURIComponent(context.section);
    if(root.location.hash!==hash)root.history[replace?'replaceState':'pushState'](null,'',hash);
  }
  function stop(){if(timer!==null){root.clearInterval(timer);timer=null;}$('play').textContent='▶ Авто';$('play').setAttribute('aria-pressed','false');}
  function reveal(focus){if(focus)$('step-title').focus({preventScroll:true});document.querySelector('.workspace').scrollIntoView({block:'start',behavior:'auto'});}
  function go(next,options){options=options||{};if(!options.auto)stop();index=Math.max(0,Math.min(list().length-1,next));route(!!options.replace);render(!options.quiet);if(index===list().length-1)stop();}
  function pathIds(topology,from,to){
    var queue=[[from]],seen={};seen[from]=true;
    while(queue.length){var current=queue.shift(),last=current[current.length-1];if(last===to)return current;topology.links.forEach(function(link){var next=link.from===last?link.to:link.to===last?link.from:null;if(next&&!seen[next]){seen[next]=true;queue.push(current.concat(next));}});}
    return [from,to];
  }
  function points(topology,ids){return ids.map(function(id){return topology.nodes.find(function(n){return n.id===id;});}).filter(Boolean).map(function(n){return [n.x,n.y];});}
  function line(points){return points.map(function(p,i){return (i?'L ':'M ')+p[0]+' '+p[1];}).join(' ');}
  function half(points){
    var lengths=[],total=0;for(var i=1;i<points.length;i++){var length=Math.hypot(points[i][0]-points[i-1][0],points[i][1]-points[i-1][1]);lengths.push(length);total+=length;}
    var target=total/2,result=[points[0]];for(var j=1;j<points.length;j++){if(target>=lengths[j-1]){target-=lengths[j-1];result.push(points[j]);}else{var ratio=target/lengths[j-1];result.push([points[j-1][0]+(points[j][0]-points[j-1][0])*ratio,points[j-1][1]+(points[j][1]-points[j-1][1])*ratio]);break;}}return result;
  }
  var icons='<defs>'+[
    '<symbol id="net-laptop" viewBox="0 0 116 105"><path d="M12 10 79 0 79 61 12 72Z" fill="#203743" stroke="#85b3cb"/><path d="M17 14 73 6 73 57 17 66Z" fill="#2b4657" stroke="#a2cce2"/><path d="M23 21 66 15 66 50 23 56Z" fill="none" stroke="#a2cce2"/><path d="m12 72 67-11 29 22-69 16Z" fill="#3a5d72" stroke="#85b3cb"/><path d="m12 72 27 27 69-16v5l-70 17L12 78Z" fill="#203743" stroke="#85b3cb"/><path d="m25 76 48-8 19 14-49 10Z M34 74l17 15m-8-17 18 15m-9-16 17 14m-35-7 48-9m-41 15 48-9" fill="none" stroke="#a2cce2"/></symbol>',
    '<symbol id="net-router" viewBox="0 0 112 100"><path d="m8 48 57-14 39 21-60 17Z" fill="#3a5d72" stroke="#85b3cb"/><path d="m8 48 36 24v22L8 70Z" fill="#2b4657" stroke="#85b3cb"/><path d="m44 72 60-17v22L44 94Z" fill="#203743" stroke="#85b3cb"/><path d="M27 46V9m50 28V3M20 60l15 10M53 78l7-2m6-2 7-2m6-2 7-2m-43-15 18-5m-5-2 5 2-3 5" fill="none" stroke="#a2cce2"/><circle cx="94" cy="67" r="2.5" fill="#b1e3ca"/></symbol>',
    '<symbol id="net-server" viewBox="0 0 90 112"><path d="m12 12 42-10 25 16-43 12Z" fill="#3a5d72" stroke="#85b3cb"/><path d="m12 12 24 18v78l-24-19Z" fill="#2b4657" stroke="#85b3cb"/><path d="m36 30 43-12v78l-43 12Z" fill="#203743" stroke="#85b3cb"/><path d="m18 28 12 9m-12 7 12 9m-12 7 12 9m-12 7 12 9M44 40l27-7m-27 19 27-7m-27 19 27-7m-27 19 27-7m-27 19 27-7" fill="none" stroke="#a2cce2"/><circle cx="66" cy="90" r="2" fill="#b1e3ca"/></symbol>',
    '<symbol id="net-switch" viewBox="0 0 112 90"><path d="m8 25 57-14 39 21-60 17Z" fill="#3a5d72" stroke="#85b3cb"/><path d="m8 25 36 24v26L8 50Z" fill="#2b4657" stroke="#85b3cb"/><path d="m44 49 60-17v26L44 75Z" fill="#203743" stroke="#85b3cb"/><path d="m51 57 10-3v9l-10 3Zm16-4 10-3v9l-10 3Zm16-4 10-3v9l-10 3Z" fill="none" stroke="#a2cce2"/></symbol>',
    '<symbol id="net-cloud" viewBox="0 0 112 90"><path d="M26 66C2 64 3 35 23 32 23 4 65-2 76 24 111 17 122 65 91 70H27Z" fill="#223c4c" stroke="#85b3cb" stroke-width="2"/><circle cx="57" cy="43" r="17" fill="none" stroke="#a2cce2"/><path d="M40 43h34M57 26c-13 12-13 22 0 34m0-34c13 12 13 22 0 34" fill="none" stroke="#a2cce2"/></symbol>'
  ].join('')+'</defs>';
  function wrap(value,max){var lines=[''];String(value||'').split(' ').forEach(function(word){var last=lines.length-1;if(lines[last].length&&lines[last].length+word.length+1>max)lines.push(word);else lines[last]+=(lines[last]?' ':'')+word;});return lines;}
  function graph(step,animate){
    var topology=model.getTopology(scenario),paths=[],colorValue=color(step);
    if(isMessage(step)){var targets=step.broadcastTo&&step.broadcastTo.length?step.broadcastTo:[step.to];targets.forEach(function(to){var ids=step.via?[step.from].concat(step.via,[to]):pathIds(topology,step.from,to);var p=points(topology,ids);if(p.length>1)paths.push(step.lost?half(p):p);});}
    var title=isMessage(step)?direction(step)+': '+step.label:step.title;
    var html='<p class="scene-scroll-hint">Широкую схему можно прокрутить вбок. Пояснение шага — ниже.</p><svg class="network-svg" viewBox="0 0 '+topology.width+' '+topology.height+'" role="img" aria-labelledby="net-title net-desc"><title id="net-title">'+esc(title)+'</title><desc id="net-desc">Выбранные участники и логические пути. Схема не показывает все промежуточные устройства и не является захватом трафика.</desc>'+icons;
    for(var y=28;y<topology.height;y+=32)html+='<path class="grid-line" d="M0 '+y+'H'+topology.width+'"/>';
    for(var x=24;x<topology.width;x+=44)html+='<path class="grid-line" d="M'+x+' 0V'+topology.height+'"/>';
    topology.links.forEach(function(link){var p=points(topology,[link.from,link.to]);if(p.length!==2)return;html+='<path class="link" d="'+line(p)+'"/>';if(link.label&&Math.hypot(p[1][0]-p[0][0],p[1][1]-p[0][1])>210){var mx=(p[0][0]+p[1][0])/2,my=(p[0][1]+p[1][1])/2-17;html+='<text class="route-note" x="'+mx+'" y="'+my+'" text-anchor="middle">'+esc(link.label)+'</text>';}});
    paths.forEach(function(p){html+='<path class="link-active" d="'+line(p)+'"/>';});
    topology.nodes.forEach(function(node){var kind=['laptop','router','server','switch','cloud'].indexOf(node.kind)>=0?node.kind:node.kind==='dns'?'server':'server';var width=kind==='server'?82:106,height=kind==='server'?102:96;var active=step.from===node.id||(!step.lost&&(step.to===node.id||(step.broadcastTo||[]).indexOf(node.id)>=0));var titles=wrap(node.title,21),addresses=String(node.address||'').split(/\n| · /);html+='<g transform="translate('+(node.x-width/2)+' '+(node.y-height/2)+')">'+(active?'<ellipse class="node-halo" cx="'+width/2+'" cy="'+height*.55+'" rx="'+width*.72+'" ry="'+height*.68+'"/>':'')+'<use href="#net-'+kind+'" width="'+width+'" height="'+height+'"/>';titles.forEach(function(text,i){html+='<text class="node-name" x="'+width/2+'" y="'+(height+23+i*21)+'" text-anchor="middle">'+esc(text)+'</text>';});addresses.forEach(function(text,i){html+='<text class="node-address" x="'+width/2+'" y="'+(height+23+titles.length*21+i*18)+'" text-anchor="middle">'+esc(text)+'</text>';});html+='</g>';});
    paths.forEach(function(p){if(step.lost){var end=p[p.length-1];html+='<text class="loss-cross" x="'+end[0]+'" y="'+(end[1]+10)+'" text-anchor="middle">×</text>';}});
    if(animate&&!reduced.matches){
      var flights=[];
      if(paths.length>1){
        // One frame leaves the source. The switch then copies it to outgoing
        // branches. A shared prefix is animated once, not once per recipient.
        var seenEdges={};
        paths.forEach(function(p){for(var i=1;i<p.length;i++){var key=p[i-1].join(',')+'>'+p[i].join(',');if(!seenEdges[key]){seenEdges[key]=true;flights.push({points:[p[i-1],p[i]],begin:(i-1)*0.6,duration:0.6});}}});
      }else paths.forEach(function(p){flights.push({points:p,begin:0,duration:1.25});});
      flights.forEach(function(f){html+='<g aria-hidden="true" opacity="0"><rect x="-14" y="-9" width="28" height="18" rx="4" fill="'+colorValue+'" stroke="#e3f4ff"/><path d="m-10-5 10 7 10-7" fill="none" stroke="#18252f"/><animateMotion begin="'+f.begin+'s" dur="'+f.duration+'s" fill="freeze" path="'+line(f.points)+'"/><animate attributeName="opacity" values="1;1;0" keyTimes="0;0.9;1" begin="'+f.begin+'s" dur="'+f.duration+'s" fill="freeze"/></g>';});
    }
    html+='</svg>';if(isMessage(step))html+='<button class="scene-inspect" data-inspect="true" type="button">'+esc(step.label)+(step.lost?' · не доставлено':'')+' ↗</button>';
    $('scene').innerHTML=html;var button=$('scene').querySelector('[data-inspect]');if(button)button.addEventListener('click',inspect);
  }
  function sequence(){
    var html='<div class="network-sequence">',found=false;
    list().slice(0,index+1).forEach(function(step,i){if(!isMessage(step))return;found=true;html+='<button type="button" class="sequence-event" data-sequence-step="'+i+'" '+(i===index?'aria-current="step" ':'')+'style="--protocol-color:'+color(step)+'"><span class="sequence-number">'+String(i+1).padStart(2,'0')+'</span><span><span class="sequence-route">'+esc(direction(step))+'</span><span class="sequence-caption">'+esc(step.label)+(step.lost?' · не доставлено':'')+'</span></span></button>';});
    if(!found)html+='<p class="mechanism-note">Сетевых сообщений ещё нет. Пока участники выполняют местную подготовку.</p>';
    html+='<p class="mechanism-note">Порядок сообщений, не шкала измеренного времени. Локальные проверки объяснены в шагах, но не превращены в фиктивные пакеты.</p></div>';$('scene').innerHTML=html;
    $('scene').querySelectorAll('[data-sequence-step]').forEach(function(b){b.addEventListener('click',function(){go(Number(b.dataset.sequenceStep),{quiet:true});reveal(true);});});
  }
  function mechanisms(state){
    $('participant-state').innerHTML=(state.facts||[]).map(function(f){return '<div class="state-item '+(f.tone==='good'?'is-ready':f.tone==='warn'?'is-warn':f.tone==='bad'?'is-bad':'')+'"><span>'+esc(f.label)+'</span>'+esc(f.value)+'</div>';}).join('');
    $('mechanism-panels').innerHTML=(state.panels||[]).map(function(p){var body='';
      if(p.type==='table')body='<div class="mechanism-table-wrap" tabindex="0" aria-label="Таблица: '+esc(p.title)+'"><table class="mechanism-table"><thead><tr>'+(p.columns||[]).map(function(c){return '<th scope="col">'+esc(c)+'</th>';}).join('')+'</tr></thead><tbody>'+(p.rows||[]).map(function(row){return '<tr>'+row.map(function(c){return '<td>'+esc(c)+'</td>';}).join('')+'</tr>';}).join('')+'</tbody></table></div>';
      if(p.type==='packet')body='<div class="packet-stack">'+(p.layers||[]).map(function(layer){return '<div class="packet-layer tone-'+tone(layer.tone)+'"><strong>'+esc(layer.name)+'</strong><code>'+esc(layer.value)+'</code><small>'+esc(layer.detail)+'</small></div>';}).join('')+'</div>';
      if(p.type==='ranges')body=(p.rows||[]).map(function(row){return '<div class="range-row"><span class="range-label">'+esc(row.label)+'</span><div class="range-segments">'+(row.segments||[]).map(function(seg){var status=Object.prototype.hasOwnProperty.call(statusNames,seg.status)?seg.status:'waiting';return '<span class="range-segment status-'+status+'">'+esc(seg.label)+'<small>'+esc(seg.description||statusNames[status])+'</small></span>';}).join('')+'</div></div>';}).join('');
      if(p.type==='note')body='<p class="mechanism-note">'+esc(p.text)+'</p>';
      return '<section class="mechanism-panel"><h4>'+esc(p.title)+'</h4>'+body+(p.note?'<p class="mechanism-note">'+esc(p.note)+'</p>':'')+'</section>';
    }).join('');
  }
  function setupObservation() {
    var host=$('network-observation');
    if(!host)return null;
    var lease=config.id==='network-setup';
    var choices=lease?
      [['dhcp-offer','Предложение'],['dhcp-ack','Подтверждение'],['dhcp-announce','Использование']]:
      [['inner-office','На ноутбуке'],['outer-office','В интернете'],['gateway-decrypt','На VPN-шлюзе']];
    $('observation-title').textContent=lease?'Когда адрес становится своим?':'Какой адрес виден в этой точке?';
    var controls=$('observation-choices');
    controls.innerHTML=choices.map(function(c){return '<button type="button" data-observe="'+c[0]+'">'+c[1]+'</button>';}).join('');
    controls.querySelectorAll('[data-observe]').forEach(function(b){
      b.addEventListener('click',function(){
        var target=list().findIndex(function(s){return s.id===b.dataset.observe;});
        if(target>=0){panel='explain';go(target);}
      });
    });
    return function(step,state){
      host.hidden=lease?scenario!=='dhcp':scenario!=='split'&&scenario!=='full';
      if(host.hidden)return;
      var snap=state.observation,picture=$('observation-picture');
      controls.querySelectorAll('[data-observe]').forEach(function(b){
        if(b.dataset.observe===step.id)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');
      });
      if(!snap){
        picture.innerHTML='';
        $('observation-note').textContent='Сравни один запрос к офисной странице в трёх точках пути. Кнопка переключит весь разбор на соответствующий шаг.';
        return;
      }
      if(lease){
        var labels=['Адреса ещё нет','Адрес предложен','Аренда подтверждена','Адрес используется'];
        picture.innerHTML='<div class="lease-ticket" data-lease="'+snap.stage+'"><div><span>IPv4 ноутбука</span><strong>'+esc(snap.address||'—')+'</strong></div><b>'+labels[snap.stage]+'</b></div>';
      }else{
        var endpoints='<div class="lens-endpoints"><span><small>Источник</small><code>'+esc(snap.from)+'</code></span><i aria-hidden="true">→</i><span><small>Назначение</small><code>'+esc(snap.to)+'</code></span></div>';
        picture.innerHTML='<div class="vpn-envelope" data-outside="'+snap.outside+'"><strong>'+(snap.outside?'Внешний IPv4 · после домашнего NAT':'Внутренний IPv4 · офисный пакет')+'</strong>'+endpoints+
          (snap.outside?'<div class="vpn-udp"><span>Порты UDP: <code>'+esc(snap.udp)+'</code></span><b>Внутренний IP-пакет зашифрован</b></div>':'')+'</div>';
      }
      $('observation-note').textContent=snap.note;
    };
  }
  function details(step){
    $('step-title').textContent=step.title;
    $('explanation').innerHTML='<p class="step-summary">'+esc(step.summary)+'</p>'+step.paragraphs.map(function(p){return '<p>'+esc(p)+'</p>';}).join('')+'<div class="changed-box"><h4>Что изменилось</h4><p>'+esc(step.changed)+'</p></div><div class="visible-box"><h4>Что можно наблюдать</h4><p>'+esc(step.visible)+'</p></div><div class="step-sources">'+(step.sourceIds||[]).map(function(id){return model.sources.find(function(s){return s.id===id;});}).filter(Boolean).map(function(s){return '<a href="'+esc(s.url)+'" target="_blank" rel="noopener noreferrer">'+esc(s.title)+' ↗</a>';}).join('')+'</div>';
    $('fields').innerHTML='<p class="field-intro">Значимые поля выбранного сообщения, не полный байтовый дамп. Для местного действия здесь показаны проверяемые настройки, а не выдуманный сетевой пакет.</p>'+(step.fields||[]).map(function(f){return '<section class="field-layer"><h4>'+esc(f.title||f.layer)+'</h4><dl>'+f.items.map(function(item){return '<dt>'+esc(item[0])+'</dt><dd><span class="field-value">'+esc(item[1])+'</span><span class="field-meaning">'+esc(item[2])+'</span></dd>';}).join('')+'</dl></section>';}).join('');
    $('explanation').hidden=panel!=='explain';$('fields').hidden=panel!=='fields';document.querySelectorAll('[data-panel]').forEach(function(b){b.setAttribute('aria-pressed',String(b.dataset.panel===panel));});
  }
  function phases(step){
    $('phases').innerHTML=model.phases.map(function(p,i){var first=-1,last=-1;list().forEach(function(s,j){if(s.phase===p.id){if(first<0)first=j;last=j;}});var done=last>=0&&last<index;return '<button type="button" data-phase="'+esc(p.id)+'" class="phase '+(done?'is-done':'')+'" '+(p.id===step.phase?'aria-current="step" ':'')+(first<0?'disabled ':'')+'><span class="phase-number">'+(done?'✓':i+1)+'</span><span><strong>'+esc(p.title)+'</strong><small>'+esc(p.description||'')+'</small></span></button>';}).join('');
    $('phases').querySelectorAll('[data-phase]').forEach(function(b){b.addEventListener('click',function(){panel='explain';go(list().findIndex(function(s){return s.phase===b.dataset.phase;}));reveal(true);});});
  }
  function journal(){var messages=list().slice(0,index+1).map(function(step,i){return {step:step,index:i};}).filter(function(x){return isMessage(x.step);});$('journal-count').textContent='Событий передачи: '+messages.length;
    $('journal').innerHTML=messages.length?messages.map(function(x){return '<button type="button" class="journal-entry" data-journal-step="'+x.index+'" '+(x.index===index?'aria-current="step" ':'')+'style="--protocol-color:'+color(x.step)+'"><span class="entry-index">'+String(x.index+1).padStart(2,'0')+'</span><span class="entry-protocol">'+esc(x.step.protocol.toUpperCase())+'</span><span class="entry-label">'+esc(direction(x.step))+'<br>'+esc(x.step.label)+(x.step.lost?' · не доставлено':'')+'</span></button>';}).join(''):'<p class="journal-empty">На пройденных шагах сетевых сообщений пока не было.</p>';
    $('journal').querySelectorAll('[data-journal-step]').forEach(function(b){b.addEventListener('click',function(){panel='fields';go(Number(b.dataset.journalStep),{quiet:true});reveal(true);});});
  }
  function render(animate){var step=list()[index],state=model.getState(scenario,index);$('experiment').style.setProperty('--protocol-color',color(step));$('scenario').value=scenario;$('scenario-description').textContent=model.scenarios.find(function(s){return s.id===scenario;}).description;phases(step);if(view==='network')graph(step,animate);else sequence();details(step);mechanisms(state);journal();
    if(syncMtu) syncMtu(scenario);
    if(syncObservation) syncObservation(step,state);
    var back=context?context.file+'#section='+encodeURIComponent(context.section):defaultBack;$('return-to-section').href=back;$('return-to-theory').href=back;
    $('message-direction').textContent=direction(step);$('message-label').textContent=isMessage(step)?step.label:step.title;$('inspect-message').disabled=!(step.fields&&step.fields.length);
    $('step-counter').textContent='Шаг '+(index+1)+' из '+list().length;$('protocol-badge').textContent=step.protocol==='local'?'Местное действие':step.protocol.toUpperCase();$('range-label').textContent=$('step-counter').textContent;$('step-range').max=String(list().length-1);$('step-range').value=String(index);$('step-range').setAttribute('aria-valuetext',step.title);$('previous').disabled=index===0;$('reset').disabled=index===0;$('next').disabled=index===list().length-1;$('next').textContent=index===list().length-1?'Опыт завершён':'Следующий шаг →';$('play').disabled=index===list().length-1;document.querySelectorAll('[data-view]').forEach(function(b){b.setAttribute('aria-pressed',String(b.dataset.view===view));});$('announcement').textContent=$('step-counter').textContent+'. '+step.title+'. '+step.changed;
  }
  function inspect(){stop();panel='fields';route(false);render(false);document.querySelector('[data-panel="fields"]').focus({preventScroll:true});}
  function setupAckExperiment(experiment) {
    var receiver = experiment.initial(), blocks = experiment.blocks;
    $('tcp-order-bytes').innerHTML = blocks.map(function(b) {
      return b.text.split('').map(function(letter, n) {
        return '<span id="tcp-byte-' + (b.first + n) + '"><b>' + esc(letter) + '</b><small>' + (b.first + n) + '</small></span>';
      }).join('');
    }).join('');
    $('tcp-order-choices').innerHTML = blocks.map(function(b, i) {
      return '<button type="button" id="tcp-deliver-' + i + '" aria-label="Доставить ' + esc(b.text) +
        ', байты ' + b.first + '–' + b.last + '"><strong>' + esc(b.text) + '</strong><span>' +
        b.first + '–' + b.last + '</span></button>';
    }).join('');
    $('tcp-order-stream').innerHTML = blocks.map(function(b, i) {
      return '<li id="tcp-order-slot-' + i + '"><strong>' + esc(b.text) +
        '</strong><span id="tcp-order-state-' + i + '"></span></li>';
    }).join('');
    function show(reason) {
      blocks.forEach(function(b, i) {
        var tone = !receiver.received[i] ? (receiver.received.slice(i+1).some(Boolean) ? 'gap' : 'absent') : b.last < receiver.next ? 'continuous' : 'buffered';
        $('tcp-order-slot-' + i).setAttribute('data-arrival', tone);
        $('tcp-order-state-' + i).textContent = {absent:'Нет на сервере', gap:'Пропуск', continuous:'Без пропуска', buffered:'За пропуском'}[tone];
        for (var byte = b.first; byte <= b.last; ++byte) $('tcp-byte-' + byte).setAttribute('data-arrival', tone);
      });
      $('tcp-order-tape').setAttribute('data-edge', receiver.bytes);
      $('tcp-order-frontier').textContent = receiver.bytes === 12 ? 'Все 12 байтов подряд · далее 1013' : 'Ждём байт ' + receiver.next;
      $('tcp-order-ack').textContent = receiver.ack === null ? '—' : 'ACK ' + receiver.ack;
      $('tcp-order-reason').textContent = reason;
    }
    function reset() {
      receiver = experiment.initial();
      show('Ни одна часть ещё не пришла. Сервер ждёт байт ' + receiver.next + '; подтверждения данных файла пока не было.');
    }
    blocks.forEach(function(b, i) {
      $('tcp-deliver-' + i).addEventListener('click', function() {
        stop();
        receiver = experiment.deliver(receiver, i);
        var ack = 'ACK ' + receiver.ack + '. ';
        var reason = {
          duplicate: 'Копия ' + b.text + ' не добавила новых байтов. Номер подтверждения тот же.',
          gap: b.text + ' уже на сервере, но раньше в файле есть пропуск: ещё нужен байт ' + receiver.next + '. Сервер сохранил эти буквы на потом.',
          bridge: 'Сегмент ' + b.text + ' заполнил пропуск. Следующие буквы уже лежали в буфере, поэтому теперь от начала файла без пропуска есть ' + receiver.bytes + ' из 12 байтов.',
          advance: 'Сегмент ' + b.text + ' пришёл по порядку. От начала файла без пропуска получено ' + receiver.bytes + ' из 12 байтов.'
        }[receiver.effect];
        show(ack + reason);
      });
    });
    $('tcp-order-reset').addEventListener('click', function() { stop(); reset(); });
    $('try-tcp-order').addEventListener('click', function() {
      stop();
      var title = $('tcp-order-title');
      title.focus({preventScroll:true});
      title.scrollIntoView({block:'start',behavior:reduced.matches?'auto':'smooth'});
    });
    reset();
  }
  if(model.ackExperiment && $('tcp-order-choices')) setupAckExperiment(model.ackExperiment);
  function setupMtuExperiment(experiment) {
    var panel=$('mtu-probe'), state=null;
    $('mtu-choices').innerHTML=experiment.sizes.map(function(size){
      return '<button id="mtu-send-'+size+'" type="button" aria-pressed="false">'+size+' байт</button>';
    }).join('');
    function paint(){
      var pending=state && state.ptb==='in-flight', size=state ? state.size : 0;
      experiment.sizes.forEach(function(n){$('mtu-send-'+n).setAttribute('aria-pressed', String(size===n));});
      $('mtu-ruler').querySelectorAll('[data-cut]').forEach(function(cell){
        var n=Number(cell.dataset.cut);
        cell.setAttribute('data-fill',size<n?'empty':n>1400?'overflow':'fits');
      });
      $('mtu-lan').textContent=state?'Прошёл':'—';
      $('mtu-wan').textContent=!state?'—':state.wan?'Прошёл':'Отброшен';
      $('mtu-wan').setAttribute('data-verdict', !state?'':state.wan?'fits':'overflow');
      $('mtu-estimate').textContent=(state?state.estimate:1500)+' байт';
      $('mtu-math').textContent=state ? size+' = 40 (заголовок IPv6) + 8 (заголовок UDP) + '+state.payload+' (данные UDP), в байтах.' : '40 байт занимает заголовок IPv6, ещё 8 — заголовок UDP. Остальное место в пакете отведено данным.';
      $('mtu-result').textContent=!state?'Как думаешь, пройдёт ли пакет ровно в 1400 байт?':
        state.wan?(size===1400?'Ровно на границе: 1400 байт допустимы.':'Остался запас в один байт.')+' Пакет дошёл до сервера. Уведомления об ошибке нет; само по себе это не сообщает клиенту точный предел пути.':
        pending?'Одного лишнего байта хватило: маршрутизатор отбросил весь пакет, а не отрезал его конец. В ответ отправлено Packet Too Big («пакет слишком велик»). Пока оно в пути, клиент ещё не знает о пределе 1400.':
        'Клиент получил Packet Too Big, проверил, что уведомление относится к его пакету, и снизил оценку предела пути до 1400 байт. Исходный пакет не доставлен; новый мы ещё не отправляли.';
      $('mtu-deliver-ptb').setAttribute('aria-disabled',String(!pending));
    }
    experiment.sizes.forEach(function(size){$('mtu-send-'+size).addEventListener('click',function(){
      stop();state=experiment.send(size);paint();
    });});
    $('mtu-deliver-ptb').addEventListener('click',function(){
      if(!state||state.ptb!=='in-flight')return;
      stop();state=experiment.receivePtb(state);paint();
    });
    $('mtu-reset').addEventListener('click',function(){stop();state=null;paint();});
    panel.addEventListener('toggle',function(){if(panel.open)stop();});
    paint();
    return function(current){
      var visible=current==='pmtu6';
      if(!panel.hidden&&!visible){panel.open=false;state=null;paint();}
      panel.hidden=!visible;
    };
  }
  var syncMtu=model.mtuExperiment && $('mtu-probe') ? setupMtuExperiment(model.mtuExperiment) : null;
  var syncObservation=setupObservation();
  $('page-title').textContent=model.title;document.title=model.title+' · Сетевая лаборатория';$('lab-subtitle').textContent=model.summary;
  $('intro-paragraphs').innerHTML=model.introduction.paragraphs.map(function(p){return '<p>'+esc(p)+'</p>';}).join('');$('intro-goal').textContent=model.introduction.goal;$('intro-action').textContent=model.introduction.action;
  $('scenario').innerHTML=model.scenarios.map(function(s){return '<option value="'+esc(s.id)+'">'+esc(s.title)+'</option>';}).join('');
  $('assumptions').innerHTML=model.assumptions.map(function(p){return '<p>'+esc(p)+'</p>';}).join('');$('sources').innerHTML=model.sources.map(function(s){return '<article><a href="'+esc(s.url)+'" target="_blank" rel="noopener noreferrer">'+esc(s.title)+' ↗</a><p>'+esc(s.description)+'</p></article>';}).join('');
  $('next').addEventListener('click',function(){go(index+1);reveal(this.disabled);});$('previous').addEventListener('click',function(){go(index-1);reveal(this.disabled);});$('reset').addEventListener('click',function(){panel='explain';go(0);reveal(true);});$('step-range').addEventListener('input',function(){go(Number(this.value),{replace:true});});$('scenario').addEventListener('change',function(){stop();scenario=this.value;index=0;panel='explain';route(false);render(false);});$('inspect-message').addEventListener('click',inspect);
  document.querySelectorAll('[data-view]').forEach(function(b){b.addEventListener('click',function(){stop();view=b.dataset.view;route(false);render(false);});});document.querySelectorAll('[data-panel]').forEach(function(b){b.addEventListener('click',function(){stop();panel=b.dataset.panel;route(false);render(false);});});
  $('play').addEventListener('click',function(){if(timer!==null){stop();return;}if(index===list().length-1)return;$('play').textContent='Ⅱ Пауза';$('play').setAttribute('aria-pressed','true');timer=root.setInterval(function(){go(index+1,{auto:true,replace:true});},5000);});
  document.querySelectorAll('.start-button,.skip-link').forEach(function(a){a.addEventListener('click',function(e){e.preventDefault();stop();$('experiment').scrollIntoView({block:'start',behavior:reduced.matches?'auto':'smooth'});$('experiment').focus({preventScroll:true});});});
  root.addEventListener('hashchange',function(){stop();parse();render(false);});root.addEventListener('popstate',function(){stop();parse();render(false);});document.addEventListener('visibilitychange',function(){if(document.hidden)stop();});document.addEventListener('keydown',function(e){if(e.altKey||e.ctrlKey||e.metaKey||e.shiftKey||e.target.closest('button,a,input,select,textarea,summary,[contenteditable="true"],#scene,.mechanism-table-wrap,.ack-workbench'))return;if(e.key==='ArrowRight'){e.preventDefault();go(index+1);}if(e.key==='ArrowLeft'){e.preventDefault();go(index-1);}});
  parse();render(false);
}(typeof window==='undefined'?globalThis:window));
