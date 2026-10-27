// Click-to-assemble exercises: isolated hook state, no browser storage or network.
const GLib=imports.gi.GLib, BA=imports.byteArray;
const read=p=>BA.toString(GLib.file_get_contents(p)[1]);
function assert(value,message){if(!value)throw new Error(message);}
const app=read('roadmap/assets/station-app.js');
new Function(app);
const helper=app.slice(app.indexOf('  function prepareQuestions('),app.indexOf('  function Quiz(props)'));
let cells=[],cursor=0;
const h=(type,props,...children)=>({type,props:props||{},children:children.flat(Infinity)});
function useState(initial){const i=cursor++;if(!(i in cells))cells[i]=typeof initial==='function'?initial():initial;return[cells[i],v=>{cells[i]=v;}];}
const api=new Function('h','useState',helper+';return {prepareQuestions,assembledText,assemblyCorrect,AssemblyAnswer};')(h,useState);
function all(node,test){if(!node||typeof node!=='object')return[];return(test(node)?[node]:[]).concat(node.children.flatMap(n=>all(n,test)));}
function button(tree,label){return all(tree,n=>n.type==='button'&&n.children.includes(label))[0];}
const plan=JSON.parse(read('roadmap/content/checkpoints/station0.json'));
let tested=0;
for(const [module,entries]of Object.entries(plan.modules)){
  for(const original of entries.filter(q=>q.type==='assemble')){
    const before=JSON.stringify(original), q=api.prepareQuestions([original])[0];
    assert(JSON.stringify(original)===before,'Preparing assembly mutated source');
    assert(q.tokenOrder.length===q.tokens.length&&new Set(q.tokenOrder).size===q.tokens.length,'Pool lost tokens');
    assert(api.assemblyCorrect(q,q.answer),'Canonical assembly rejected');
    assert(!api.assemblyCorrect(q,[]),'Empty assembly accepted');
    assert(!api.assemblyCorrect(q,q.answer.slice(0,-1)),'Incomplete assembly accepted');
    cells=[]; let checked=null,locked=false;
    const render=()=>{cursor=0;return api.AssemblyAnswer({question:q,locked,onCheck:v=>{checked=v;locked=true;}});};
    let tree=render();
    assert(button(tree,'Проверить код').props.disabled,'Empty code must not be graded');
    const pool=()=>all(tree,n=>n.props.className==='assembly-pool')[0];
    for(const token of q.answer){
      const choice=pool().children.find(n=>n.props.key===token);
      assert(choice&&!choice.props.disabled,'Needed token missing or locked');
      choice.props.onClick();tree=render();
      assert(pool().children.find(n=>n.props.key===token).props.disabled,'Used token must not be reusable');
    }
    button(tree,'Убрать последний').props.onClick();tree=render();
    const last=q.answer[q.answer.length-1];
    pool().children.find(n=>n.props.key===last).props.onClick();tree=render();
    button(tree,'Проверить код').props.onClick();tree=render();
    assert(checked===true,'A correctly clicked assembly was graded incorrectly: '+module);
    assert(button(tree,'Проверить код').props.disabled&&button(tree,'Очистить').props.disabled,'Graded answer must lock');
    assert(all(tree,n=>n.props.className==='assembly-solution').length===1,'Feedback must reveal the complete constructed example');
    tested++;
  }
}
const repeated={tokens:['int','x',';',';'],answer:[0,1,2]};
assert(api.assemblyCorrect(repeated,[0,1,3]),'Equal tokens must be interchangeable');
assert(!api.assemblyCorrect(repeated,[1,0,2]),'Wrong order must fail');
const sample=api.prepareQuestions([{type:'assemble',tokens:['int','x',';'],answer:[0,1,2],before:'',after:''}])[0];
cells=[];cursor=0;let result=null;
let wrong=api.AssemblyAnswer({question:sample,locked:false,onCheck:v=>{result=v;}});
all(wrong,n=>n.props.className==='assembly-pool')[0].children[0].props.onClick();cursor=0;
wrong=api.AssemblyAnswer({question:sample,locked:false,onCheck:v=>{result=v;}});
button(wrong,'Проверить код').props.onClick();assert(result===false,'Incomplete clicked answer must not earn a point');
assert(tested===8,'Expected two syntax builders in each of four station0 subchapters');
print('PASS: 8 syntax builders, token shuffling, click/remove/undo, correct and wrong answers, feedback lock, interchangeable tokens');
