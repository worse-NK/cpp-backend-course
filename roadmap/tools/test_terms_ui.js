// DOM-model regression tests (not a live browser or a screenshot/layout test).
const GLib=imports.gi.GLib, BA=imports.byteArray;
const read=p=>BA.toString(GLib.file_get_contents(p)[1]);
const assert=(v,m)=>{if(!v)throw Error(m);};
const source=read('roadmap/tools/test_visual_labs_ui.js');
const factory=new Function('read',source.slice(source.indexOf('function createDOM('),source.indexOf('const doc=createDOM()'))+';return createDOM;')(read);

function dom(markup) {
  const doc=factory('roadmap/glossary.html');
  if(markup)doc.body.innerHTML=markup;
  const proto=Object.getPrototypeOf(doc.body), jobs=[], observers=[], winListeners={};
  class Text {
    constructor(value,parent){this.nodeValue=value;this.parentElement=parent;this.nodeType=3;}
    get textContent(){return this.nodeValue;} get children(){return [];}
    matches(){return false;} querySelectorAll(){return [];}
  }
  Object.defineProperty(proto,'children',{configurable:true,get(){return this.nodes.filter(n=>typeof n!=='string'&&n.nodeType!==3);}});
  Object.defineProperty(proto,'id',{configurable:true,get(){return this.attrs.id||'';},set(v){this.attrs.id=v;}});
  Object.defineProperty(proto,'className',{configurable:true,get(){return this.attrs.class||'';},set(v){this.attrs.class=v;}});
  Object.defineProperty(proto,'classList',{configurable:true,get(){return {contains:c=>this.className.split(' ').includes(c)};}});
  Object.defineProperty(proto,'dataset',{configurable:true,get(){return new Proxy({}, {
    get:(_,k)=>this.attrs['data-'+String(k).replace(/[A-Z]/g,c=>'-'+c.toLowerCase())],
    set:(_,k,v)=>{this.attrs['data-'+String(k).replace(/[A-Z]/g,c=>'-'+c.toLowerCase())]=String(v);return true;}
  });}});
  Object.defineProperty(proto,'href',{configurable:true,get(){return this.attrs.href||'';},set(v){this.attrs.href=v;}});
  Object.defineProperty(proto,'hash',{configurable:true,get(){return this.href.includes('#')?'#'+this.href.split('#')[1]:'';}});
  Object.defineProperty(proto,'isConnected',{configurable:true,get(){let p=this;while(p&&p!==doc.body)p=p.parentElement;return p===doc.body;}});
  proto.clear=function(){this.nodes.forEach(n=>{if(typeof n!=='string')n.parentElement=null;});this.nodes=[];};
  proto.append=function(...children){children.forEach(child=>{if(typeof child==='string')child=new Text(child,this);child.parentElement=this;this.nodes.push(child);});};
  proto.remove=function(){if(this.parentElement){this.parentElement.nodes=this.parentElement.nodes.filter(n=>n!==this);this.parentElement=null;}};
  proto.contains=function(node){for(let p=node;p;p=p.parentElement)if(p===this)return true;return false;};
  proto.focus=function(){doc.activeElement=this;if(doc.listeners.focusin)doc.listeners.focusin({target:this});};
  proto.scrollIntoView=function(){this.scrolled=true;};
  proto.getBoundingClientRect=function(){return this.box||{left:40,top:100,bottom:125,width:300,height:this.id==='course-term-popup'?240:25};};
  proto.matches=function(selector){
    const simple=(el,s)=>{
      const attrs=[...s.matchAll(/\[([\w-]+)(?:(\^?=)"([^"]*)")?\]/g)];
      const head=s.replace(/\[[^\]]+\]/g,''),tag=head.match(/^[\w-]+/);
      if(tag&&el.tagName!==tag[0].toUpperCase())return false;
      if([...head.matchAll(/\.([\w-]+)/g)].some(m=>!el.className.split(' ').includes(m[1])))return false;
      return attrs.every(([,k,op,v])=>k in el.attrs&&(!op||(op==='='?el.attrs[k]===v:el.attrs[k].startsWith(v))));
    };
    return selector.split(',').some(s=>{
      const parts=s.trim().split(/\s+/);let node=this;
      if(!simple(node,parts.pop()))return false;
      while(parts.length){const part=parts.pop();node=node.parentElement;while(node&&!simple(node,part))node=node.parentElement;if(!node)return false;}
      return true;
    });
  };
  const normalize=el=>{el.nodes=el.nodes.map(n=>typeof n==='string'?new Text(n,el):n);el.children.forEach(normalize);};
  const textNodes=el=>el.nodes.flatMap(n=>n.nodeType===3?[n]:textNodes(n));
  doc.querySelector=s=>doc.querySelectorAll(s)[0]||null;
  doc.getElementById=id=>doc.querySelectorAll('[id]').find(e=>e.id===id)||null;
  doc.createElement=tag=>new proto.constructor(tag);
  doc.readyState='complete';
  doc.createTreeWalker=element=>{normalize(element);const all=textNodes(element);let at=0;return {nextNode:()=>all[at++]||null};};
  doc.createRange=()=>{
    let first,from,last,to;
    return {
      setStart(n,i){first=n;from=i;},setEnd(n,i){last=n;to=i;},
      deleteContents(){
        normalize(doc.body);const all=textNodes(doc.body),start=all.indexOf(first),end=all.indexOf(last);
        assert(start>=0&&end>=start,'Range endpoints must be connected');
        if(first===last)first.nodeValue=first.nodeValue.slice(0,from)+first.nodeValue.slice(to);
        else {const tail=last.nodeValue.slice(to);first.nodeValue=first.nodeValue.slice(0,from);for(let i=start+1;i<end;i++)all[i].nodeValue='';last.nodeValue=tail;}
      },
      insertNode(anchor){const parent=first.parentElement,index=parent.nodes.indexOf(first),tail=new Text(first.nodeValue.slice(from),parent);first.nodeValue=first.nodeValue.slice(0,from);anchor.parentElement=parent;parent.nodes.splice(index+1,0,anchor,tail);}
    };
  };
  class Observer {constructor(callback){this.callback=callback;observers.push(this);}disconnect(){this.active=false;}observe(){this.active=true;}fire(){if(this.active)this.callback();}}
  const win={document:doc,MutationObserver:Observer,innerWidth:1280,innerHeight:800,requestAnimationFrame:f=>jobs.push(f),addEventListener:(k,f)=>winListeners[k]=f};
  const location={hash:''};
  return {doc,win,location,jobs,observers,winListeners,refresh(){observers.forEach(o=>o.fire());while(jobs.length)jobs.shift()();}};
}
const sentence=JSON.parse(read('roadmap/content/station0.json')).theory.find(s=>s.id==='why-oop').blocks[0].html;
const env=dom('<article data-terms-scope="lesson"><h2>Инвариант</h2><p class="section-lead">Что такое инвариант?</p><p class="theory-text">'+sentence+'</p><p class="theory-text"><b>RAII</b> (приём управления ресурсом: объект отвечает за его освобождение в своём деструкторе) помогает.</p><p class="theory-text">mutex (m1) и <a href="existing.html">DNS</a>.</p><pre><code>std::move(x); // инвариант</code></pre><p class="theory-text"><code>std::move</code> и <code>std::move(x)</code>.</p></article><button id="outside">Инвариант</button>');
new Function('window',read('roadmap/generated/terms.data.js'))(env.win);
new Function('globalThis',read('roadmap/assets/terms-core.js'))(env.win);
new Function('window','document','NodeFilter','MutationObserver',read('roadmap/assets/terms.js'))(env.win,env.doc,{SHOW_TEXT:4},env.win.MutationObserver);
const doc=env.doc, anchors=()=>doc.querySelectorAll('a[data-course-term]');
assert(anchors().filter(a=>a.dataset.courseTerm==='invariant').length===1,'One marker per term per lesson');
assert(!doc.querySelector('article').textContent.includes('условие, которому'),'Repeated approved inline definition should be replaced too');
assert(doc.querySelector('pre').textContent==='std::move(x); // инвариант','Never annotate source listings');
assert(doc.getElementById('outside').textContent==='Инвариант'&&!doc.getElementById('outside').children.length,'Never annotate answer/navigation buttons');
assert(anchors().some(a=>a.dataset.courseTerm==='raii'),'Support bold term followed by a definition outside the bold tag');
assert(doc.querySelector('article').textContent.includes('mutex (m1)'),'Preserve non-definition parentheses');
assert(doc.querySelector('a[href="existing.html"]').textContent==='DNS','Do not create nested links');
assert(anchors().filter(a=>a.dataset.courseTerm==='move').length===1,'Inline identifier allowed, but not a C++ expression');
const count=anchors().length;env.refresh();assert(anchors().length===count,'Enhancement must be idempotent');
const opener=anchors().find(a=>a.dataset.courseTerm==='invariant');
assert(opener.dataset.termDefinition===env.win.COURSE_TERMS.find(e=>e.id==='invariant').short,'Keep the short definition available for print CSS');
function click(target,overrides={}){const e={target,button:0,preventDefault(){this.prevented=true;},...overrides};doc.listeners.click(e);return e;}
assert(click(opener).prevented,'Ordinary activation opens the card');
let popup=doc.getElementById('course-term-popup');
assert(popup&&popup.getAttribute('role')==='dialog'&&!popup.getAttribute('aria-modal'),'Definition is a labelled non-modal dialog');
assert(opener.getAttribute('aria-expanded')==='true','Accessible expanded state');
assert(doc.activeElement.className==='term-popup-close','Move keyboard focus into the card');
const more=popup.querySelector('a');
assert(more.href==='glossary.html#term-invariant'&&more.target==='_blank','Deep glossary link preserves reading in the original tab');
assert(doc.getElementById('course-term-description').textContent===env.win.COURSE_TERMS.find(e=>e.id==='invariant').short,'Use short shared definition as text, not HTML');
doc.listeners.keydown({key:'Escape',preventDefault(){}});
assert(!doc.getElementById('course-term-popup')&&doc.activeElement===opener,'Escape closes and restores focus');
assert(opener.getAttribute('aria-expanded')==='false'&&!opener.getAttribute('aria-controls'),'Clear stale ARIA state');
click(opener);doc.getElementById('course-term-popup').querySelector('a').focus();doc.listeners.keydown({key:'Tab',shiftKey:false,preventDefault(){}});
assert(!doc.getElementById('course-term-popup')&&doc.activeElement===opener,'Tab out closes the card at its reading position');
click(opener);doc.listeners.keydown({key:'Tab',shiftKey:true,preventDefault(){}});
assert(!doc.getElementById('course-term-popup')&&doc.activeElement===opener,'Shift-Tab from the close button returns to the term');
assert(!click(opener,{ctrlKey:true}).prevented&&!doc.getElementById('course-term-popup'),'Ctrl-click keeps normal hyperlink behavior');
click(opener);doc.getElementById('outside').focus();assert(!doc.getElementById('course-term-popup'),'Leaving a non-modal dialog closes it without trapping focus');
click(opener);opener.box={left:1250,top:780,bottom:795};env.winListeners.resize();popup=doc.getElementById('course-term-popup');
assert(parseFloat(popup.style.left)<=894&&parseFloat(popup.style.top)<=550,'Clamp desktop card within viewport');
env.win.innerWidth=390;env.winListeners.resize();assert(popup.style.left==='16px'&&popup.style.bottom==='16px','Touch layout keeps card within the viewport');
env.win.innerWidth=1280;opener.box={left:10,top:-100,bottom:-70};env.winListeners.scroll();assert(!doc.getElementById('course-term-popup'),'Do not leave an unanchored card after scrolling away');
opener.box=null;click(opener);doc.querySelector('article').remove();env.refresh();assert(!doc.getElementById('course-term-popup'),'Navigation unmount closes stale definitions');

const glossary=dom(),gdoc=glossary.doc;
new Function('window','document','location',read('roadmap/assets/glossary.js'))(glossary.win,gdoc,glossary.location);
const input=gdoc.getElementById('term-search');input.value='инвариант';input.listeners.input();
assert(gdoc.querySelectorAll('.glossary-entry').some(e=>!e.hidden),'Search Russian terms and details');
input.value='zzzz-no-such-term';input.listeners.input();assert(!gdoc.getElementById('term-empty').hidden,'Visible empty state');
glossary.location.hash='#term-raii';glossary.winListeners.hashchange();
assert(input.value===''&&!gdoc.getElementById('term-raii').hidden&&gdoc.activeElement.id==='term-raii','Deep link clears conflicting filters and focuses the article');
assert(!gdoc.querySelector('.glossary-search').hidden,'Enable search only after controller initialization');
const rssSection=JSON.parse(read('roadmap/content/station7.json')).theory.find(s=>s.id==='linux-packet-to-handler');
const rssParagraph=rssSection.blocks.find(b=>(b.html||'').includes('Receive Side Scaling')).html;
for(const protectedMeaning of [true,false]){
  const fixture=dom('<article data-terms-scope="lesson"><p class="theory-text">'+(protectedMeaning?rssParagraph:rssParagraph.replace('data-no-terms',''))+'</p></article>');
  new Function('window',read('roadmap/generated/terms.data.js'))(fixture.win);
  new Function('globalThis',read('roadmap/assets/terms-core.js'))(fixture.win);
  new Function('window','document','NodeFilter','MutationObserver',read('roadmap/assets/terms.js'))(fixture.win,fixture.doc,{SHOW_TEXT:4},fixture.win.MutationObserver);
  const rssAnchors=fixture.doc.querySelectorAll('a[data-course-term]').filter(a=>a.dataset.courseTerm==='rss');
  assert(rssAnchors.length===(protectedMeaning?0:1),'Explicit opt-out must prevent network RSS from receiving the resident-memory definition');
}
print('PASS: definition replacement, protected code/buttons/links, network RSS opt-out, one marker, popup focus/Escape, modified click, mobile/edge placement, route cleanup, glossary search/deep links');
