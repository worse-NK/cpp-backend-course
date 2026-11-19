/* Original diagram plates for the course index. The three named frames are
   illustrations of specific lab conditions, not a second simulation. */
(function(root) {
  "use strict";
  const families = [
    {name:"Программа и память", mark:"memory", ids:["lifetime","ownership","temporaries","taskownership","vector","build","concurrency"]},
    {name:"Путь по сети", mark:"wire", ids:["network","https-journey","network-setup","packetpath","tcp-delivery","vpn-tunnels"]},
    {name:"Данные и сервисы", mark:"record", ids:["sql","transactions","overload","distributed","security-sql","security"]}
  ];
  const plates = [
    {id:"tcp-delivery", mode:"reordered", tab:"TCP", code:"SEQ / ACK", title:"Байты с пропуском", note:"Конец файла уже на сервере. Подтверждение остановилось перед недостающей серединой."},
    {id:"vector", mode:"reserved", tab:"Память", code:"std::vector", title:"Граница сдвинулась", note:"Для числа 30 место уже было. Буфер тот же, но прежний end() больше не обозначает конец вектора."},
    {id:"distributed", mode:"lost-reply", tab:"Raft", code:"LOG / ACK", title:"Копия есть. Ответ ещё в пути", note:"Команда уже на дисках A и B. Пока ответ B не пришёл, лидер A знает только о своей копии."}
  ];
  const txt=(x,y,s,cls="")=>'<text x="'+x+'" y="'+y+'" class="'+cls+'">'+s+'</text>';
  const line=(d,cls)=>'<path d="'+d+'" class="'+cls+'"/>';
  const rect=(x,y,w,h,cls)=>'<rect x="'+x+'" y="'+y+'" width="'+w+'" height="'+h+'" class="'+cls+'"'+(cls==="hatch"?' fill="url(#atlasHatch)"':'')+'/>';
  const box=(x,y,w,h,top,front,side)=>'<g transform="translate('+x+' '+y+')">'+
    '<path d="M0 0l18 -13h'+w+'l-18 13z" class="'+top+'"/>'+
    '<path d="M'+w+' 0l18 -13v'+h+'l-18 13z" class="'+side+'"/>'+rect(0,0,w,h,front)+'</g>';
  function bytes() {
    let a = line("M42 144h393", "rule");
    ["ABCD","EFGH","IJKL"].forEach((s,i)=>{
      const x=46+126*i;
      a+=box(x,99,101,38,i===1?"ghost":"top",i===1?"hatch":"face",i===1?"ghost":"side");
      a+=txt(x+50,124,s,i===1?"value quiet":"value");
      a+=txt(x,165,["1001","1005","1009"][i],"coord");
    });
    return a+line("M172 80V58h64","pointer")+txt(243,62,"ACK 1005","label")+
      line("M172 178v7h100v-7","rule")+txt(222,206,"не пришли","legend");
  }
  function memory() {
    let a="";
    ["10","20","30",""].forEach((s,i)=>{
      const x=62+81*i;
      a+=box(x,103,78,44,i===3?"ghost":"top",i===3?"hatch":i===2?"new-face":"face",i===3?"ghost":"side");
      if (s)a+=txt(x+39,132,s,"value");
      a+=txt(x,171,"["+i+"]","coord");
    });
    return a+line("M224 89V66h-60","pointer")+txt(158,70,"старый end()","end-label")+
      line("M305 177v11h36","pointer")+txt(345,193,"end()","label");
  }
  function quorum() {
    const peer=(x,y,id,known)=>'<g transform="translate('+x+' '+y+')">'+
      '<path d="M-30 0v25c0 15 60 15 60 0V0" '+(known?'class="face"':'class="hatch" fill="url(#atlasHatch)"')+'/>'+
      '<ellipse rx="30" ry="10" class="'+(known?"top":"ghost")+'"/>'+txt(0,24,id,"peer")+'</g>';
    return line("M109 116L306 71","wire")+line("M305 88L179 117","reply")+
      line("M109 132L310 170","idle")+peer(80,108,"A",true)+peer(342,58,"B",true)+peer(342,156,"C",false)+
      txt(52,177,"лидер","label")+txt(189,75,"запись","legend")+txt(219,138,"ответ в пути","legend")+
      txt(340,211,"нет копии","legend");
  }
  function figure(index) {
    return '<svg class="atlas-engraving" viewBox="0 0 460 225" aria-hidden="true" focusable="false">'+
      '<defs><pattern id="atlasHatch" patternUnits="userSpaceOnUse" width="7" height="7"><path d="M-1 1l2 -2m-1 8l7 -7m-1 8l2 -2" stroke="#9ca9a1" stroke-width="1"/></pattern></defs>'+
      [bytes,memory,quorum][index]()+'</svg>';
  }
  const marks={
    memory:'<path d="M3 6h26v16H3zM11 6v16m9-16v16M5 3v3m8-3v3m9-3v3"/>',
    wire:'<path d="M4 8h9l7 12h8M4 20h8l7-12h9"/><circle cx="3" cy="8" r="2"/><circle cx="29" cy="20" r="2"/>',
    record:'<path d="M3 4h25v6H3zm3 9h22v5H6zm4 8h18v5H10z"/>'
  };
  const icon=key=>'<svg viewBox="0 0 32 30" class="atlas-mark" aria-hidden="true" focusable="false">'+marks[key]+'</svg>';
  const number=n=>String(n).padStart(2,"0");
  function mount(el, catalog, href, stationName, esc) {
    const listed=new Set(families.flatMap(f=>f.ids));
    const unknown=catalog.filter(l=>!listed.has(l.id));
    const groups=unknown.length?[...families,{name:"Другие лаборатории",mark:"record",ids:unknown.map(l=>l.id)}]:families;
    function entry(l) {return l.entries.find(e=>e.primary)||l.entries[0];}
    el.innerHTML='<div class="lab-atlas"><section class="atlas-cover" aria-labelledby="atlasHeading"><div class="atlas-type">'+
      '<p class="atlas-eyebrow"><i aria-hidden="true"></i> Атлас курса · C++ и backend</p><h1 id="atlasHeading">Визуальные <em>лаборатории</em></h1>'+
      '<p class="atlas-deck">Что происходит между строкой кода и результатом? Меняй условия и следи за тем, что обычно скрыто: памятью программы, байтами в сети и решениями сервера.</p>'+
      '<span class="atlas-caption">'+number(catalog.length)+' лабораторий · выбор по теме ниже ↓</span></div>'+
      '<div class="atlas-plate"><div class="plate-head"><span>Фрагмент опыта</span><div class="plate-switch" role="group" aria-label="Выбрать иллюстрацию">'+
      plates.map((p,i)=>'<button type="button" data-plate="'+i+'" aria-pressed="'+(i===0)+'">'+p.tab+'</button>').join("")+'</div></div>'+
      '<div id="atlasFrame" class="atlas-frame" aria-live="polite"></div></div></section><div class="atlas-index"><h2>Выбери лабораторию</h2>'+
      groups.map((g,i)=>'<section class="atlas-group" data-family="'+g.mark+'"><header><span class="atlas-group-number">'+number(i+1)+'</span>'+icon(g.mark)+'<h3>'+g.name+'</h3></header><div class="atlas-entries">'+
        g.ids.map(id=>catalog.find(l=>l.id===id)).filter(Boolean).map(l=>{
          const e=entry(l);
          return '<article class="catalog-card"><div class="atlas-item-no">'+number(catalog.indexOf(l)+1)+'</div><div><h4><a href="'+esc(href(l.id,l.scenarios[0]))+'">'+esc(l.title)+' <span aria-hidden="true">↗</span></a></h4><p>'+esc(l.summary)+'</p>'+
            '<a class="atlas-source" href="'+esc(e.file+"#section="+e.section)+'">Теория · станция '+esc(stationName(e.station))+' →</a></div></article>';
        }).join("")+'</div></section>').join("")+'</div></div>';
    const frame=el.querySelector(".atlas-frame");
    const buttons=el.querySelectorAll("[data-plate]");
    function show(i){
      const p=plates[i];
      frame.innerHTML='<figure><div class="atlas-print"><div class="print-label"><span>Рис. '+number(i+1)+'</span><span>'+p.code+'</span></div>'+figure(i)+'</div>'+
        '<figcaption><div><h2>'+p.title+'</h2><p>'+p.note+'</p></div><a href="'+esc(href(p.id,p.mode))+'">В лабораторию <span aria-hidden="true">↗</span></a></figcaption></figure>';
      buttons.forEach((b,j)=>b.setAttribute("aria-pressed",String(j===i)));
    }
    buttons.forEach((b,i)=>{b.onclick=()=>show(i);});
    show(0);
  }
  root.CourseLabAtlas={mount};
})(window);
