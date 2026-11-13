// Structural/interaction test with the repository DOM model. Not rendered-browser QA.
const read = path => imports.byteArray.toString(imports.gi.GLib.file_get_contents(path)[1]);
const assert = (value, message) => { if (!value) throw Error(message); };
const helper = read("roadmap/tools/test_visual_labs_ui.js");
const createDOM = new Function("read", helper.slice(helper.indexOf("function createDOM("),
  helper.indexOf("const doc=createDOM()")) + ";return createDOM;")(read);
class Params {
  constructor(text = "") {
    this.values = new Map();
    const decode = part => { try { return decodeURIComponent(part.replace(/\+/g," ")); } catch (_) { return part; } };
    for (const piece of text.split("&").filter(Boolean)) {
      const [key,...value] = piece.split("=");
      const name = decode(key);
      if(!this.values.has(name))this.values.set(name,decode(value.join("=")));
    }
  }
  get(key) { return this.values.get(key) ?? null; }
}
function environment(hash="") {
  const document=createDOM("roadmap/distributed_lab.html");
  const proto=Object.getPrototypeOf(document.body);
  Object.defineProperty(proto,"id",{configurable:true,get(){return this.attrs.id||"";},set(v){this.attrs.id=String(v);}});
  Object.defineProperty(proto,"className",{configurable:true,get(){return this.attrs.class||"";},set(v){this.attrs.class=String(v);}});
  Object.defineProperty(proto,"lastElementChild",{configurable:true,get(){return this.children.at(-1)||null;}});
  proto.clear=function(){for(const node of this.children)node.parentElement=null;this.nodes=[];};
  proto.append=function(...nodes){for(const node of nodes){node.parentElement=this;this.nodes.push(node);}};
  proto.replaceChildren=function(...nodes){this.clear();this.append(...nodes);};
  document.createElement=tag=>new proto.constructor(tag);
  document.getElementById=id=>document.querySelectorAll("[id]").find(n=>n.id===id)||null;
  const listeners={},entries=[hash];let cursor=0;
  const window={location:{hash},addEventListener:(event,fn)=>listeners[event]=fn};
  window.history={
    replaceState:(_a,_b,value)=>{window.location.hash=value;entries[cursor]=value;},
    pushState:(_a,_b,value)=>{window.location.hash=value;entries.splice(cursor+1);entries.push(value);cursor++;},
    back:()=>{if(cursor>0){window.location.hash=entries[--cursor];listeners.popstate();}},
    forward:()=>{if(cursor<entries.length-1){window.location.hash=entries[++cursor];listeners.popstate();}}
  };
  new Function("window","globalThis","URLSearchParams",read("roadmap/assets/distributed-lab-model.js"))(window,window,Params);
  new Function("window","document",read("roadmap/assets/distributed-lab.js"))(window,document);
  const get=id=>{const node=document.getElementById(id);assert(node,"Missing element "+id);return node;};
  const click=id=>{
    const node=get(id);assert(!node.disabled,"Clicking disabled "+id);
    node.listeners.click({target:node,currentTarget:node,preventDefault(){}});
  };
  return {window,document,listeners,get,click,entries};
}
let visited=0;
for(const id of ["lost-reply","stale-read","workflow-recovery"]) {
  const env=environment("#scenario="+id+"&step=0"), scenario=env.window.CourseDistributedLab.scenarios.find(s=>s.id===id);
  assert(env.get("scenario-context").children.length===scenario.intro.length,"Complete introduction");
  scenario.intro.forEach((p,i)=>assert(env.get("scenario-context").children[i].textContent===p,"No shortened context"));
  assert(env.get("scenario-assumptions").children.length===scenario.assumptions.length,"Explicit assumptions");
  assert(env.get("theory-link").getAttribute("href")===scenario.theory,"Exact approved theory return");
  assert(env.get("scenario-"+id).getAttribute("aria-pressed")==="true","Current scenario accessible");
  assert(env.get("previous-step").disabled&&env.get("first-step").disabled,"Initial boundaries");
  for(let step=0;step<scenario.steps.length;step++) {
    env.click("event-step-"+step);
    assert(env.get("event-title").textContent===scenario.steps[step].title,"Current title "+id+"/"+step);
    assert(env.document.activeElement===env.get("event-title"),"Explicit step selection focus");
    assert(env.get("event-step-"+step).getAttribute("aria-current")==="step","Current event marker");
    assert(env.window.location.hash==="#scenario="+id+"&step="+step,"Deep-link reflects event");
    assert(env.get("participants").children.length===3,"Three real participants");
    assert(env.get("event-why").textContent===scenario.steps[step].why,"Unabridged causality");
    assert(env.get("prediction-answer").textContent===scenario.steps[step].answer,"Hidden self-check answer");
    assert(env.get("prediction-check").open===false,"New event does not spoil answer");
    assert(env.get("client-knowledge").textContent===scenario.steps[step].state.client,"Client knowledge not inferred magically");
    assert(env.get("lab-announcement").textContent.includes(scenario.steps[step].title),"Concise live announcement");
    const state=scenario.steps[step].state;
    assert(env.get("read-comparison").hidden===!state.result,"Read alternatives only where meaningful");
    if(state.result)assert(env.get("read-alternatives").children.length===2,"Exactly two alternative outcomes");
    visited++;
  }
  assert(env.get("next-step").disabled,"Last event boundary");
  env.click("first-step");assert(env.get("previous-step").disabled,"Reset returns to initial state");
  env.click("next-step");assert(env.window.location.hash.endsWith("step=1"),"Forward event");
  env.click("previous-step");assert(env.window.location.hash.endsWith("step=0"),"Previous event");
}
const e=environment("#scenario=stale-read&step=9");
assert(!e.get("read-comparison").hidden,"Native deep-link target has comparison");
e.click("next-step");
e.window.history.back();
assert(e.get("event-title").textContent.includes("Позднее чтение"),"History back restores exact event");
e.window.history.forward();
assert(e.get("event-title").textContent.includes("Срок истёк"),"History forward restores exact event");
e.click("scenario-workflow-recovery");
assert(e.get("event-title").textContent==="Анна покупает последнюю книгу","Switch begins with concrete situation");
assert(e.document.activeElement===e.get("scenario-title"),"Scenario switch focus");
assert(e.get("read-comparison").hidden,"No stale read comparison after scenario switch");
e.window.location.hash="#scenario=lost-reply&step=3";e.listeners.hashchange();
assert(e.get("event-title").textContent.includes("B сохранил"),"External hash change loads target");
let prevented=false;
e.document.listeners.keydown({target:e.document.body,key:"ArrowRight",preventDefault(){prevented=true;}});
assert(prevented&&e.window.location.hash.endsWith("step=4"),"Arrow navigation");
const region=e.document.querySelectorAll('[role="region"]')[0];
prevented=false;
e.document.listeners.keydown({target:region,key:"ArrowRight",preventDefault(){prevented=true;}});
assert(!prevented&&e.window.location.hash.endsWith("step=4"),"Horizontal table retains native scrolling");
e.get("prediction-check").open=true;e.click("next-step");
assert(!e.get("prediction-check").open,"Spoiler disclosure reset");
const invalid=environment("#scenario=%ZZ&step=999");
assert(invalid.window.location.hash==="#scenario=lost-reply&step=0","Invalid route canonicalized safely");
assert(invalid.get("theory-link").getAttribute("href").startsWith("cpp_station16_"),"No arbitrary return URL");
const script=read("roadmap/assets/distributed-lab.js");
assert(!/innerHTML|\beval\s*\(|\bfetch\s*\(|XMLHttpRequest|WebSocket|setInterval|setTimeout|localStorage/.test(script),"No HTML evaluation, networking, autoplay or score writes");
const markup=read("roadmap/distributed_lab.html");
assert(markup.indexOf("Покупатель нажал")<markup.indexOf('id="scenario-navigation"'),"Human situation precedes controls");
assert(markup.includes('role="status"')&&markup.includes('href="#experiment"'),"Live region and skip link");
assert(!markup.includes("maximum-scale")&&!markup.includes("user-scalable=no"),"Zoom preserved");
print("PASS: "+visited+" event views, complete introductions, accessible markers/focus, exact model state, self-checks, deep-links/back/forward, native table keys and isolated navigation. DOM model only; actual browser rendering not verified.");
