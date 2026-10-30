// Read-only export of the production final-selection policy.
const GLib=imports.gi.GLib, BA=imports.byteArray;
const read=path=>BA.toString(GLib.file_get_contents(path)[1]);
const source=read('roadmap/assets/station-app.js');
const code=source.slice(source.indexOf('  function assessmentPriorityRefs('),source.indexOf('  // Training exposes'));
const helpers=new Function(code+';return {finalQuestions,assessmentPriorityRefs,assessmentFinalBudgets};')();
const dir=GLib.Dir.open('roadmap/content',0), names=[];
for(let name;(name=dir.read_name())!==null;) if(/^station\d+(?:-[a-z]+)?\.json$/.test(name)) names.push(name);
const report={purpose:'Reserved final questions; new chapter checkpoints must use other questions or new authored entries',stations:{}};
names.sort().forEach(name=>{
 const data=JSON.parse(read('roadmap/content/'+name));
 const plan=JSON.parse(read('roadmap/content/checkpoints/'+name));
 const checkpoints=Object.fromEntries(Object.entries(plan.modules).map(([id,entries])=>[id,entries.map(entry=>entry.bank?data.quizzes[entry.bank][entry.index]:entry)]));
 const final=helpers.finalQuestions(data.quizzes,data.substations,25,data.meta.number<=4,helpers.assessmentPriorityRefs(data.meta.id),helpers.assessmentFinalBudgets(data.meta.id),checkpoints);
 const reserved=final.map(q=>{const bank=data.quizzes.basic.includes(q)?'basic':'advanced';return {bank,index:data.quizzes[bank].indexOf(q)};});
 const modules={};
 data.substations.forEach(m=>{modules[m.id]={title:m.title,available:[]}; ['basic','advanced'].forEach(bank=>data.quizzes[bank].forEach((q,index)=>{if(q.substation===m.id&&!final.includes(q)) modules[m.id].available.push({bank,index});}));});
 report.stations[data.meta.id]={reserved,modules};
});
print(JSON.stringify(report,null,2));
