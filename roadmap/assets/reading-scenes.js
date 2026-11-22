/* Inline explanations for an ordinary reading page. All the state belongs to
 * this illustration: no changes to routes, learner storage or quiz state. */
(() => {
  "use strict";
  if (!window.React) return;
  const R = window.React, h = R.createElement;
  const phrases = (b, f) => b.columns.map((name, i) => name + ": " + f.values[i]).join("; ");
  const edgeText = (b, e) => b.columns[e[0]] + (e[2] === "weak" ? " ⇢ " : " → ") + b.columns[e[1]];
  const counter = (i, n) => (i + 1) + " / " + n;
  const code = (s) => s ? h("code", {className:"rs-code", translate:"no"}, s) : null;

  // An ownership edge attaches to a column, not to the text inside a cell.
  // A fixed lane per source keeps other arrows in place when one owner leaves.
  function Arcs({b, f, layered}) {
    const n = b.columns.length, x = i => 300 * (i + .5) / n;
    return h("svg", {viewBox:"0 0 300 43", preserveAspectRatio:"none", className:"rs-arcs",
      "aria-hidden":true, focusable:"false"}, (f.edges || []).map((e, j) => {
      const a = layered ? 300*(e[0]+.5)/(n-1) : x(e[0]);
      const z = layered ? 147+(e[0]-(n-2)/2)*15 : x(e[1]);
      const top = 6 + e[0]*7;
      return h("g", {key:j, className:e[2] === "weak" ? "rs-weak" : "rs-strong"},
        h("path", {d:"M"+a+(layered?" 1 V":" 40 V")+top+" H"+z+" V38", vectorEffect:"non-scaling-stroke"}),
        h("path", {className:"rs-tip", d:"M"+(z-4)+" 32 L"+z+" 39 L"+(z+4)+" 32", vectorEffect:"non-scaling-stroke"}));
    }));
  }
  function Board({b, f}) {
    const graph = b.frames.some(frame => frame.edges && frame.edges.length);
    const layered=graph && b.frames.every(frame=>(frame.edges||[]).every(e=>e[1]===b.columns.length-1));
    const last=b.columns.length-1;
    const cell=(c,i)=>h("div",{key:i,className:(f.focus||[]).includes(i)?"rs-cell rs-focus":"rs-cell"},
      h("dt",null,c),h("dd",null,f.values[i]));
    if(layered) return h("div",{className:"rs-model rs-graph rs-layered"},
      h("dl",{className:"rs-cells rs-n"+last},b.columns.slice(0,last).map(cell)),
      h(Arcs,{b,f,layered:true}),
      h("dl",{className:"rs-resource"},cell(b.columns[last],last)));
    return h("div", {className:"rs-model" + (graph ? " rs-graph" : "")},
      graph ? h(Arcs, {b, f}) : null,
      h("dl", {className:"rs-cells rs-n"+b.columns.length}, b.columns.map(cell)),
      graph ? h("small", {className:"rs-connections"}, (f.edges || []).map(e => edgeText(b, e)).join(" · ") || "Связей с объектом нет") : null);
  }
  function Snapshot({b, f, i}) {
    return h("div", {className:"rs-snapshot"},
      h("div", {className:"rs-snap-head"}, h("b", null, f.label), h("small", null, counter(i, b.frames.length))),
      code(f.code), h(Board, {b,f}), "output" in f ? h("div",{className:"rs-console"},
        h("span",null,f.output?"Вывод":"Вывод пока пуст"),h("samp",null,f.output)) : null);
  }
  function Compare({b}) {
    return h("div", {className:"rs-compare-grid"}, b.frames.map((f,i) =>
      h("div", {key:i, className:"rs-case"}, h(Snapshot, {b,f,i}), h("p", {className:"rs-note"}, f.note))));
  }
  function Matrix({b}) {
    return h("table", {className:"rs-matrix", role:"table"}, h("thead",{role:"rowgroup"},h("tr",{role:"row"},
      h("th",{scope:"col",role:"columnheader"},"Шаг"), b.columns.map((name,i)=>h("th",{key:i,scope:"col",role:"columnheader"},name)))),
      h("tbody",{role:"rowgroup"},b.frames.map((f,i)=>h(R.Fragment,{key:i},
        h("tr",{role:"row"},h("th",{scope:"row",role:"rowheader"},f.label),
          f.values.map((v,j)=>h("td",{key:j,role:"cell",className:(f.focus||[]).includes(j)?"rs-focus":""},
            h("small",{className:"rs-mobile-key","aria-hidden":true},b.columns[j]),v))),
        h("tr",{className:"rs-explain-row",role:"row"},h("td",{colSpan:b.columns.length+1,role:"cell"},code(f.code),f.note))))));
  }
  function Timeline({b}) {
    return h("ol", {className:"rs-timelist"}, b.frames.map((f,i) => {
      const a=b.axis, span=f.span;
      return h("li", {key:i},
        a ? h("div",{className:"rs-axis"},h("small",null,span[0]+"–"+span[1]+" "+a.unit),
          h("svg",{viewBox:"0 0 300 9", preserveAspectRatio:"none","aria-hidden":true,focusable:"false"},
            h("rect",{className:"rs-base",width:300,height:9}),
            h("rect",{x:300*(span[0]-a.min)/(a.max-a.min),width:300*(span[1]-span[0])/(a.max-a.min),height:9}))) : null,
        h("div",{className:"rs-time-content"},h("b",null,f.label),code(f.code),
          h("dl",{className:"rs-inline-data"}, b.columns.map((name,k)=>h("div",{key:k},h("dt",null,name),h("dd",null,f.values[k])))),
          h("p",{className:"rs-note"},f.note)));
    }));
  }
  // Render every snapshot at the same grid position. Only one is visible;
  // the tallest reserves its natural height, so changing state never moves
  // the text or the threshold which selects that very state.
  function Stack({b,at,decorative}) {
    return h("div", {className:"rs-stack", "aria-hidden":decorative || undefined}, b.frames.map((f,i)=>
      h("div",{key:i,className:"rs-layer","aria-hidden":i!==at || undefined,"data-shown":i===at?"yes":"no"},
        h(Snapshot,{b,f,i}))));
  }
  function Transcript({b,at,details}) {
    return h("ol", {className:"rs-beats"}, b.frames.map((f,i) =>
      h("li",{key:i,"aria-current":i===at?"step":undefined}, h("span",{className:"rs-beat-num","aria-hidden":true},String(i+1).padStart(2,"0")),
        h("h4",null,f.label),h("p",null,f.note),
        h("div",{className:details ? "rs-beat-detail" : "rs-print-detail"},code(f.code),h("span",null,phrases(b,f)),
          "output" in f ? h("span",null,f.output?"Вывод: "+f.output:"Вывод пока пуст") : null,
          (f.edges || []).length ? h("span",null,f.edges.map(e=>edgeText(b,e)).join(" · ")) : null))));
  }
  function Trace({b}) {
    const [at, set] = R.useState(0);
    return h(R.Fragment,null,h("div",{className:"rs-explorer"},
      h(Stack,{b,at}),h("p",{className:"rs-note","aria-live":"polite","aria-atomic":true},b.frames[at].note),
      h("div",{className:"rs-controls","aria-label":"Шаги схемы"},
        h("button",{type:"button",disabled:at===0,onClick:()=>set(i=>i-1)},"← Назад"),
        h("span",null,counter(at,b.frames.length)),
        h("button",{type:"button",disabled:at===b.frames.length-1,onClick:()=>set(i=>i+1)},"Дальше →"))),
      h("div",{className:"rs-print-all"},h(Transcript,{b,at:-1})));
  }
  function Story({b}) {
    const ref = R.useRef(null), stage = R.useRef(null), tail = R.useRef(null), [at,set] = R.useState(0);
    R.useLayoutEffect(()=>{
      let raf = 0;
      const track = ref.current, panel = stage.current, beats = track.querySelector(".rs-beats");
      const items = Array.from(beats.children);
      const update = () => {
        raf=0;
        const hgt=window.innerHeight, box=panel.getBoundingClientRect(), col=beats.getBoundingClientRect();
        const inset=parseFloat(getComputedStyle(panel).top)||0;
        const stacked=col.left<box.right-2;
        const flat=stacked && (box.height>hgt*.55 || hgt<440);
        if (track.classList.contains("rs-unpinned")!==flat) track.classList.toggle("rs-unpinned",flat);
        const guide=flat ? hgt*.42 : stacked ? Math.min(hgt*.86,inset+box.height+(hgt-box.height-inset)*.42) :
          Math.min(hgt*.72,inset+box.height*.52);
        let i=0;
        for(let j=1;j<items.length;j++){
          if(items[j].getBoundingClientRect().top+14>guide) break;
          i=j;
        }
        set(old=>old===i?old:i);
      };
      const schedule=()=>{if(!raf) raf=requestAnimationFrame(update);};
      const ro=window.ResizeObserver?new ResizeObserver(schedule):null;
      if(ro){ro.observe(track);ro.observe(panel);}
      window.addEventListener("scroll",schedule,{passive:true});window.addEventListener("resize",schedule);
      update();
      return ()=>{if(ro)ro.disconnect();window.removeEventListener("scroll",schedule);window.removeEventListener("resize",schedule);cancelAnimationFrame(raf);};
    },[b]);
    const jump=()=>{tail.current.focus({preventScroll:true});tail.current.scrollIntoView({block:"start",behavior:"instant"});};
    return h(R.Fragment,null,
      h("div",{className:"rs-guide"},h("span",null,"Листай вниз или вверх, чтобы сравнить шаги."),h("button",{type:"button",onClick:jump},"Пропустить схему")),
      h("div",{className:"rs-track",ref},h("div",{className:"rs-stage",ref:stage},h(Stack,{b,at,decorative:true})),
        h(Transcript,{b,at,details:true})),
      h("p",{tabIndex:-1,ref:tail,className:"rs-after"},b.after||"Конец пошагового разбора."));
  }
  window.CourseReadingScene = function CourseReadingScene({block:b}) {
    const ref=R.useRef(null);
    R.useEffect(()=>{
      // Only explicit direct-preview links opt in to positioning midway down
      // a lesson. Ordinary links, history, and progress keep their semantics.
      if(new URLSearchParams(location.search).get("scene")!==b.id) return;
      const id=requestAnimationFrame(()=>ref.current?.scrollIntoView({block:"start",behavior:"instant"}));
      return ()=>cancelAnimationFrame(id);
    },[b]);
    const view={scroll:Story,trace:Trace,compare:Compare,table:Matrix,timeline:Timeline}[b.mode];
    return h("figure",{ref,className:"reading-scene rs-"+b.mode,"data-scene":b.id,"data-no-terms":"",tabIndex:-1},
      h("figcaption",null,b.title),h("p",{className:"rs-intro"},b.intro),h(view,{b}),
      b.mode!=="scroll" && b.after ? h("p",{className:"rs-after"},b.after):null);
  };
})();
