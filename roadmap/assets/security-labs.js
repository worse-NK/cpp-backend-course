(function () {
  'use strict';
  const $ = id=>document.getElementById(id);
  const model=window.SecurityLabs;
  if (!model) { $('result').textContent='Не загрузилась модель. Проверь наличие папки assets рядом со страницей.'; return; }
  let active='access', step=0;
  const context={station:'',section:''};
  const stateNames={pass:'Проверено',deny:'Причина отказа',unchecked:'Не проверено',include:'Включена',exclude:'Исключена'};
  function el(tag, cls, value) {
    const n=document.createElement(tag);
    if(cls)n.className=cls;
    if(value!==undefined)n.textContent=String(value);
    return n;
  }
  function table(headers,rows) {
    const t=el('table'), head=el('thead'), tr=el('tr'), body=el('tbody');
    for(const title of headers){const th=el('th','',title);th.setAttribute('scope','col');tr.append(th);}
    head.append(tr);t.append(head);
    for(const row of rows){const r=el('tr');for(const cell of row)r.append(el('td','',cell));body.append(r);}
    t.append(body);return t;
  }
  function parameters() {
    const result={};
    for(const part of (window.location.hash||'').replace(/^#/,'').split('&')) {
      const at=part.indexOf('=');
      if(at<0)continue;
      try{result[decodeURIComponent(part.slice(0,at))]=decodeURIComponent(part.slice(at+1));}catch(_){/* Invalid links use defaults. */}
    }
    return result;
  }
  function remember() {
    const hash='#lab=security&scenario='+active+'&step='+step+
      (context.station?'&from='+encodeURIComponent(context.station)+'&section='+encodeURIComponent(context.section):'');
    if(window.history&&window.history.replaceState)window.history.replaceState(null,'',hash);
  }
  function theoryLink() {
    const m=model.modules[active];
    let href='cpp_station15_security.html#section='+m.section;
    for(const lab of window.COURSE_LABS||[]) {
      if(lab.id!=='security')continue;
      const entry=lab.entries.find(e=>e.station===context.station&&e.section===context.section&&e.scenario===active);
      if(entry)href=entry.file+'#section='+encodeURIComponent(entry.section);
    }
    // The destination is selected only from our default section or catalog allowlist.
    href+='&fromLab=security';
    $('theory-link').setAttribute('href',href);
    $('lesson-return').setAttribute('href',href);
  }
  function resetOutput() {
    $('result').replaceChildren(el('p','','Нажми «Проверить решение». Изменение настройки само по себе ничего не выполняет.'));
    $('trace').replaceChildren();$('trace-empty').hidden=false;
    $('hops').replaceChildren();$('result-rows').replaceChildren();
    $('checks-summary').textContent='';$('checks-results').replaceChildren();
    $('after-run-next').hidden=true;
  }
  function facts() {
    const c=model.modules[active].cases.find(c=>c.id===$('case').value);
    let value='';
    if(active==='access') {
      const actions={get:'открыть карточку',list:'получить список',rename:'переименовать запись',change_owner:'сменить владельца'};
      value=`По условию запрос от Анны (7), на сайте выбран «Север» (10). Вход ${c.expired?'уже прекращён':'ещё действует'}. Просим ${actions[c.action]}${c.task?' '+c.task:''}.`;
      if(c.fields.length)value+=' Переданы поля: '+c.fields.join(', ')+'.';
    }
    if(active==='outbound')value=c.hops.map((h,i)=>`Переход ${i+1}: ${h.scheme}://${h.host}:${h.port}. DNS: ${h.answers.join(', ')}. Запланирован адрес ${h.selected}.`).join(' ');
    if(active==='tls')value=`Источник: ${c.issuer}. Имя: ${c.names}. Доверие ${c.trusted?'задано':'не задано'}; срок ${c.time?'подходит':'истёк'}; подтверждение ключа ${c.key?'есть':'не удалось'}.`;
    $('case-facts').textContent=value;
  }
  function goStep(index,focus) {
    step=Math.max(0,Math.min(4,index));
    const s=model.modules[active].stages[step];
    $('guide-index').textContent=String(step+1).padStart(2,'0');
    $('guide-title').textContent=s.title;$('guide-context').textContent=s.context;
    $('guide-action').textContent=s.action;$('guide-expectation').textContent=s.expectation;
    $('case').value=s.case;$('policy').value=s.policy;
    for(let i=0;i<5;i++) {
      const b=$('step-'+i);
      if(i===step)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');
    }
    $('previous').disabled=step===0;$('next').disabled=step===4;
    $('next').hidden=step===4;
    $('lesson-return').hidden=step!==4;
    $('next').textContent=step<4?'Дальше: '+model.modules[active].stages[step+1].title:'Разбор завершён';
    $('checks-section').hidden=step!==4;
    resetOutput();facts();remember();
    if(focus)$('guide-title').focus();
  }
  function openModule(id,index,focus) {
    active=Object.prototype.hasOwnProperty.call(model.modules,id)?id:'access';
    const m=model.modules[active];
    document.title=m.short+' · Лаборатория безопасности';
    $('title').textContent=m.title;$('intro').textContent=m.lead;
    $('context').replaceChildren(...m.context.map(p=>el('p','',p)));
    $('experiment-goal').textContent=m.goal;
    $('policy-label').textContent=m.policyLabel;
    $('dataset-title').textContent=m.datasetTitle;
    $('fixture-table').replaceChildren(table(m.headers,m.dataset));
    $('case').replaceChildren(...m.cases.map(c=>{const o=el('option','',c.label);o.value=c.id;return o;}));
    $('policy').replaceChildren(...m.policies.map(p=>{const o=el('option','',p[1]);o.value=p[0];return o;}));
    $('stages').replaceChildren(...m.stages.map((s,i)=>{
      const li=el('li'),b=el('button');b.type='button';b.id='step-'+i;
      b.append(el('span','',String(i+1).padStart(2,'0')),document.createTextNode(s.title));
      b.addEventListener('click',()=>goStep(i,true));li.append(b);return li;
    }));
    $('boundary').textContent=m.boundary;
    $('backend-control').hidden=active!=='tls';
    $('sources').replaceChildren(...m.sources.map(([title,url])=>{
      const a=el('a','',title+' ↗');a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a;
    }));
    for(const key of Object.keys(model.modules))$('lab-'+key).setAttribute('aria-pressed',String(key===active));
    theoryLink();goStep(index||0,false);
    // A different lab has a different task: do not scroll past its introduction.
    if(focus)$('title').focus();
  }
  function renderResult(r) {
    const comparison=el('p','comparison'+(r.correct?'':' mismatch'),r.correct?'Совпало с условием':'Не совпало с условием');
    $('result').replaceChildren(el('h3','',r.label),comparison,el('p','',r.expectation),el('p','',r.summary));
    $('trace-empty').hidden=true;
    $('trace').replaceChildren(...r.trace.map(t=>{
      const li=el('li',t.state);li.append(el('span','trace-state',stateNames[t.state]),el('h4','',t.title),el('p','',t.detail));return li;
    }));
    $('hops').replaceChildren(...(r.hops||[]).map(h=>{
      const div=el('div','tls-hop'+(h.encrypted?'':' plaintext'));
      div.append(el('h3','',h.title),el('p','',h.detail));return div;
    }));
    $('result-rows').replaceChildren();
    if(r.rows.length)$('result-rows').append(table(['Запись','Название','Команда'],r.rows.map(t=>[t.id,t.title,t.tenant_id===10?'Север (10)':'Юг (20)'])));
  }
  function run() {
    renderResult(model.evaluate(active,$('case').value,$('policy').value,$('backend').value));
  }
  function checkAll() {
    const results=model.checks(active,$('policy').value,$('backend').value);
    const passed=results.filter(r=>r.correct).length;
    $('checks-summary').textContent=`С условием совпало ${passed} из ${results.length}. Проверен только подготовленный набор этой модели.`;
    $('checks-results').replaceChildren(...results.map(r=>{
      const div=el('div','case-check'+(r.correct?'':' mismatch'));
      div.append(el('h3','',r.title),el('p','case-verdict',(r.correct?'Совпало. ':'Не совпало. ')+r.label),el('p','',r.expectation));return div;
    }));
  }
  for(const id of Object.keys(model.modules))$('lab-'+id).addEventListener('click',()=>openModule(id,0,true));
  $('model-form').addEventListener('submit',e=>{e.preventDefault();run();});
  for(const id of ['case','policy','backend'])$(id).addEventListener('change',()=>{resetOutput();facts();});
  $('check').addEventListener('click',checkAll);
  $('previous').addEventListener('click',()=>goStep(step-1,true));
  $('next').addEventListener('click',()=>goStep(step+1,true));
  $('reset').addEventListener('click',()=>{ $('backend').value='plaintext';goStep(0,true); });
  window.addEventListener('hashchange',()=>{
    const p=parameters();openModule(p.scenario,/^[0-4]$/.test(p.step||'')?Number(p.step):0,false);
  });
  const initial=parameters();context.station=initial.from||'';context.section=initial.section||'';
  openModule(initial.scenario,/^[0-4]$/.test(initial.step||'')?Number(initial.step):0,false);
  $('run').disabled=false;
}());
