/* gjs roadmap/tools/test_cpp_lab_plates.js, from the repository root. */
const GLib=imports.gi.GLib, BA=imports.byteArray;
const load=p=>(0,eval)(BA.toString(GLib.file_get_contents("roadmap/assets/"+p+".js")[1]));
load("visual-lab-models"); load("lab-cpp-plates");
const M=globalThis.CourseLabModels, P=globalThis.CourseCppPlates;
const check=(v,why)=>{if(!v)throw Error(why)};
const modes={ownership:["unique","shared","cycle","weak-cycle"],temporaries:["cxx20","cxx23","parameter","named"],
  taskownership:["run-task","discard-task"],build:["source","header","readme"]};
function draw(id,mode,n){
  const trace=M[id](mode),i=n<0?trace.steps.length+n:n;
  return P.render(id,mode,trace.steps[i].state,trace,i);
}
let snapshots=0;
for(const [id,variants] of Object.entries(modes))for(const mode of variants){
  const t=M[id](mode),before=JSON.stringify(t.steps);
  t.steps.forEach(({state},i)=>{
    const out=P.render(id,mode,state,t,i);
    check(out.includes('data-cpp-plate="'+id+'"')&&!/undefined|NaN/.test(out),id+"/"+mode+"/"+i);
    if(id==="temporaries"||id==="build"){
      // Unvisited columns reveal neither work scheduled nor values read.
      const future=(out.match(/class="cpp-cell cpp-cell-future"/g)||[]).length;
      check(future===(t.steps.length-1-i)*3,"Disclosed a future snapshot "+mode+"/"+i);
    }
    if(id==="ownership"){
      const slips=(out.match(/<code class="cpp-slip">/g)||[]).length;
      check(slips===(state.cycle?state.countA+state.countB:state.strong),"Incorrect owner balance: "+mode+"/"+i);
    }
    if(id==="taskownership"){
      check(out.includes('data-holder="'+state.owner+'"'),"Wrong holder");
      const connected=(out.match(/data-connected="true"/g)||[]).length;
      check(connected===Number(state.alive),"Dangling or duplicated connection");
    }
    snapshots++;
  });
  check(JSON.stringify(t.steps)===before,"Renderer mutated model: "+id+"/"+mode);
}
check(!P.render("not-a-lab","",{},null,0),"Unknown lab claimed");
check(draw("ownership","cycle",-1).includes("B.back</code>")&&draw("ownership","cycle",-1).includes("A.next</code>"),"Lost cycle");
check(!draw("ownership","weak-cycle",2).includes("B.back</code>"),"Weak edge counted");
check(draw("ownership","shared",-2).includes("w.lock() уже вернёт пустой"),"Weak tail omitted");
check(draw("taskownership","run-task",-2).includes('data-holder="worker"'),"Calling releases callable");
check(draw("taskownership","discard-task",-1).includes('data-holder="none"'),"Discard retained resources");
for(const m of ["parameter","cxx20"]) check(!draw("temporaries",m,-1).includes("прочитано число"),"Dangling read depicted");
for(const m of ["named","cxx23"]) check(draw("temporaries",m,-1).includes("прочитано число 3"),"Valid read missing");
for(const [m,jobs] of [["header",3],["source",2],["readme",0]]) {
  const count=(draw("build",m,-1).match(/>▶<\/td>/g)||[]).length;
  check(count===jobs,"Wrong work total for "+m);
}
print(snapshots+" C++ plate snapshots, 13 scenarios: OK");
