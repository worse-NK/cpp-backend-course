// Prepared packetpath model + existing controller smoke checks. No Linux networking.
// Run from the repository root: node roadmap/tools/test_packetpath.js (or gjs ...).
(function () {
  "use strict";
  const node=typeof process!=="undefined"&&process.versions&&process.versions.node;
  const read=node?p=>require("fs").readFileSync(p,"utf8"):p=>imports.byteArray.toString(imports.gi.GLib.file_get_contents(p)[1]);
  const output=node?message=>console.log(message):message=>print(message);
  function assert(value,message){if(!value)throw Error(message);}
  const win={};
  new Function("globalThis",read("roadmap/assets/visual-lab-models.js"))(win);
  const M=win.CourseLabModels,modes=["routed","snat","filtered","pmtu6"];
  let checked=0;
  for(const mode of modes){
    const model=M.packetpath(mode);
    assert(model.type==="packetpath"&&model.prepared,"Trace must be explicitly prepared");
    assert(model.program===null&&model.steps.length>=6,"Complete prepared sequence, not executable program");
    assert(JSON.stringify(model)===JSON.stringify(M.packetpath(mode)),"Deterministic scenario "+mode);
    for(const step of model.steps){
      assert(step.title&&step.text&&step.rule,"Missing explanation in "+mode);
      assert(Number.isInteger(step.line)&&step.line>=0&&step.line<model.code.length,"Invalid highlighted line "+mode);
      const s=step.state;
      assert(s.prepared&&s.mode===mode,"Prepared state identity "+mode);
      assert(["client","router","server"].includes(s.focus),"Current node "+mode);
      assert(s.events.length>=1&&s.events.at(-1).node===s.focus,"Event log follows current node "+mode);
      for(const count of Object.values(s.counters))assert(Number.isInteger(count)&&count>=0,"Invalid counter "+mode);
      for(const p of [s.before,s.after])if(p){
        assert(p.src&&p.dst&&p.hopLimit>0&&p.ipBytes>0,"Exact packet fields "+mode);
        assert(p.ethSrc===null||/^02(?::[0-9a-f]{2}){5}$/.test(p.ethSrc),"Prepared L2 source "+mode);
        assert((p.ethSrc===null)===(p.ethDst===null),"L2 pair is present or absent together "+mode);
        if(p.kind==="UDP")assert(p.ipBytes===p.ipHeaderBytes+8+p.payloadBytes,"UDP length accounting "+mode);
        else assert(p.kind==="ICMPv6 PTB"&&p.sport===null&&p.dport===null,"No UDP ports on external ICMPv6 packet");
      }
      checked++;
    }
    const first=model.steps[0].state,lan=model.steps[1].state.after;
    assert(first.before===null&&first.after.ethSrc===null,"Do not invent a frame before encapsulation");
    assert(lan.ethSrcName==="MAC-C"&&lan.ethDstName==="MAC-BR"&&lan.hopLimit===64,"First link targets router, not server");
    assert(lan.src===first.addresses.client&&lan.dst===first.addresses.server,"First frame retains endpoints");
    model.steps[0].state.after.src="changed only in one snapshot";
    assert(model.steps[1].state.before.src===first.addresses.client,"Snapshots must be independent");
  }
  let rejected=false;try{M.packetpath("arbitrary-network");}catch(error){rejected=error instanceof RangeError;}
  assert(rejected,"Unknown unprepared scenario must not run");
  for(const mode of ["routed","snat"]){
    const model=M.packetpath(mode),wan=model.steps.find(e=>e.state.stage==="WAN · egress").state;
    assert(wan.after.hopLimit===63&&wan.after.ethSrcName==="MAC-RWAN"&&wan.after.ethDstName==="MAC-S","WAN re-encapsulation "+mode);
    assert(wan.after.dst==="198.51.100.10"&&wan.after.sport===40000&&wan.after.dport===9000,"Request tuple "+mode);
    assert(wan.after.src===(mode==="snat"?"198.51.100.1":"192.0.2.10"),"NAT source distinction "+mode);
    assert(wan.after.payloadBytes===12&&wan.after.payloadText==="course7:ping"&&wan.after.ipBytes===40,"Prepared 12-byte ping matches course fixture");
    const end=model.steps.at(-1).state,p=end.after;
    assert(p.src==="198.51.100.10"&&p.dst==="192.0.2.10"&&p.sport===9000&&p.dport===40000&&p.hopLimit===63,"Reply endpoints/ports/TTL "+mode);
    assert(p.ethSrcName==="MAC-BR"&&p.ethDstName==="MAC-C","Reply LAN addresses "+mode);
    assert(p.payloadBytes===12&&p.payloadText==="course7:pong"&&p.ipBytes===40,"Prepared 12-byte pong matches course fixture");
    assert(end.counters.serverRequests===1&&end.counters.repliesToClient===1,"Explicit delivery observations "+mode);
  }
  const snat=M.packetpath("snat").steps;
  const translation=snat.find(e=>e.state.stage==="Router · SNAT").state;
  assert(translation.before.src==="192.0.2.10"&&translation.after.src==="198.51.100.1"&&translation.before.sport===translation.after.sport,"SNAT changes source, keeps port by assumption");
  const restored=snat.find(e=>e.state.stage==="Router · reverse NAT").state;
  assert(restored.hook.startsWith("prerouting")&&restored.before.dst==="198.51.100.1"&&restored.after.dst==="192.0.2.10"&&restored.after.hopLimit===64,"Reverse translation precedes reply forwarding");
  const filtered=M.packetpath("filtered").steps;
  assert(filtered.some(e=>e.state.stage==="Router · ingress"),"Filtered request is observed on ingress");
  assert(filtered.every(e=>e.state.focus!=="server"&&e.state.counters.wanRequests===0&&e.state.counters.serverRequests===0),"Forward drop must not invent WAN egress or server delivery");
  assert(filtered.at(-1).state.status==="dropped","Filtered terminal verdict");
  const pmtu=M.packetpath("pmtu6").steps;
  const tooBig=pmtu.find(e=>e.state.status==="too-big").state;
  assert(tooBig.after.ipBytes===1448&&tooBig.after.payloadBytes===1400&&tooBig.wanMtu===1400&&tooBig.counters.wanRequests===0,"Oversize packet drops before WAN transmit");
  assert(tooBig.after.hopLimit===64&&tooBig.hook.startsWith("до forward"),"Linux oversize check precedes FORWARD and hop-limit decrement");
  assert(!pmtu.slice(0,pmtu.findIndex(e=>e.state.status==="too-big")+1).some(e=>e.state.hook==="forward"),"Original oversize IPv6 packet must not appear at FORWARD");
  const ptb=pmtu.find(e=>e.state.after.kind==="ICMPv6 PTB").state.after;
  assert(ptb.icmpType===2&&ptb.icmpCode===0&&ptb.reportedMtu===1400&&ptb.dst==="2001:db8:7:1::10","PTB exact fields and recipient");
  assert(ptb.ipBytes===40+8+ptb.quote.quotedBytes&&ptb.ipBytes===1280&&ptb.quote.ipBytes===1448,"PTB quote differs from dropped original");
  const smaller=pmtu.find(e=>e.state.stage==="LAN · новый пакет").state.after;
  assert(smaller.payloadBytes===1352&&smaller.ipBytes===1400&&smaller.hopLimit===64,"Source forms a new smaller packet, not a router fragment");
  const last=pmtu.at(-1).state;
  assert(last.after.ipBytes===1400&&last.after.hopLimit===63&&last.counters.lanRequests===2&&last.counters.wanRequests===1&&last.counters.serverRequests===1&&last.counters.ptbToClient===1,"IPv6 retry conservation and receipt");

  // Reuse only the existing lightweight DOM fixture, not its hard-coded catalog tests.
  const fixture=read("roadmap/tools/test_visual_labs_ui.js");
  const fixtureStart=fixture.indexOf("function createDOM("),fixtureEnd=fixture.indexOf("const doc=createDOM()");
  assert(fixtureStart>=0&&fixtureEnd>fixtureStart,"Existing DOM fixture is available");
  const createDOM=new Function("read",fixture.slice(fixtureStart,fixtureEnd)+"return createDOM;")(read);
  const doc=createDOM(),listeners={},timers=new Map();let timerId=0;
  class Params {
    constructor(text=""){this.values=new Map(text.replace(/^\?/,"").split("&").filter(Boolean).map(part=>{const [key,...value]=part.split("=");return [decodeURIComponent(key),decodeURIComponent(value.join("="))];}));}
    get(key){return this.values.get(key)??null;}set(key,value){this.values.set(key,String(value));}
    toString(){return [...this.values].map(([key,value])=>encodeURIComponent(key)+"="+encodeURIComponent(value)).join("&");}
  }
  const entries=[{station:"station7-netlab",section:"netlab-packet-walk",scenario:"routed",file:"cpp_station7_linux_networks.html"},{station:"station7-netlab",section:"netlab-ipv6-pmtu",scenario:"pmtu6",file:"cpp_station7_linux_networks.html"}];
  win.COURSE_LABS=[{id:"packetpath",file:"visual_labs.html",title:"Путь пакета",summary:"Подготовленная модель",boundary:"Не Linux",scenarios:modes,entries,sources:[]}];
  win.courseLabHref=(lab,scenario)=>"visual_labs.html#lab="+lab+"&scenario="+scenario;
  win.addEventListener=(name,fn)=>listeners[name]=fn;
  const location={hash:""};
  new Function("window","document","location","setInterval","clearInterval","URLSearchParams",read("roadmap/assets/visual-labs.js"))(win,doc,location,(fn,ms)=>{timers.set(++timerId,{fn,ms});return timerId;},id=>timers.delete(id),Params);
  const get=id=>doc.getElementById(id);
  let rendered=0;
  for(const entry of entries)for(const mode of modes){
    location.hash="#lab=packetpath&scenario="+mode+"&from="+entry.station+"&section="+entry.section;listeners.hashchange();
    assert(doc.querySelectorAll("[data-mode]").length===4,"All packetpath modes available from both entry contexts");
    assert(get("returnLink").textContent.includes("7Б")&&get("returnLink").href===entry.file+"#section="+entry.section,"Exact return to 7Б context");
    const model=M.packetpath(mode);
    for(let i=0;i<model.steps.length;i++){
      get("labRange").oninput({target:{value:i}});
      const scene=get("labScene");
      assert(get("stepTitle").textContent===model.steps[i].title,"Step explanation rendered");
      assert(scene.querySelectorAll(".packet-node").length===3,"Three fixed topology nodes");
      assert(scene.querySelectorAll(".packet-node").filter(e=>e.getAttribute("aria-current")==="step").length===1,"Exactly one current node");
      assert(scene.querySelector(".packet-fields")&&scene.textContent.includes("До шага")&&scene.textContent.includes("После шага"),"Before/after packet table");
      assert(scene.textContent.includes("Подготовленная модель")&&!scene.innerHTML.includes("undefined")&&!scene.innerHTML.includes("NaN"),"Explicit boundary and complete rendering");
      rendered++;
    }
    assert(get("labNext").disabled,"Last-step control boundary");
    get("labReset").onclick();assert(get("labPrev").disabled,"Reset to first packet state");
    get("labNext").onclick();assert(!get("labPrev").disabled,"Generic step control");
    get("labPlay").onclick();assert(timers.size===1,"Generic autoplay");
    [...timers.values()][0].fn();get("labPrev").onclick();assert(timers.size===0,"Manual stepping stops autoplay");
  }
  output("PASS: packetpath 4 modes, "+checked+" state invariants, "+rendered+" rendered events, both contexts and generic controls; no network operations");
})();
