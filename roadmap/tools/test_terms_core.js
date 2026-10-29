// Content/matching regressions. These do not claim pixel-level browser testing.
const GLib=imports.gi.GLib, BA=imports.byteArray;
const read=p=>BA.toString(GLib.file_get_contents(p)[1]);
const assert=(v,m)=>{if(!v)throw Error(m);};
globalThis.window=globalThis;
new Function(read('roadmap/generated/terms.data.js'))();
new Function(read('roadmap/assets/terms-core.js'))();
const model=CourseTermsCore.create(COURSE_TERMS);
assert(CourseTermsCore.create([]).scan('anything').length===0,'An empty catalog must not loop on an empty regex');
// The UI scans the combined text of DOM nodes, not raw HTML markup.
const first=JSON.parse(read('roadmap/content/station0.json')).theory.find(s=>s.id==='why-oop').blocks.map(b=>b.html||'').find(text=>/инвариант/i.test(text)).replace(/<[^>]*>/g,'');
const invariant=model.scan(first).find(m=>m.id==='invariant');
assert(invariant&&invariant.definitionEnd>invariant.end,'The reported definition should become a small card');
assert(first.slice(invariant.end,invariant.definitionEnd)===' (условие допустимого состояния объекта)','Remove exactly the current approved explanation');
const originalDefinition='инвариантом (условием, которому должно удовлетворять допустимое состояние объекта)';
assert(model.scan(originalDefinition)[0].definitionEnd===originalDefinition.length,'Keep the original inflected definition supported');
assert(model.scan('инвариантного').length===0,'Do not mark a substring inside an unknown inflection');
assert(!model.scan('public').some(m=>m.id==='undefined-behavior'),'UB must not match inside public');
assert(model.scan('NRVO')[0].id==='nrvo','RVO must not capture NRVO');
assert(model.scan('std::move')[0].id==='move','Escape punctuation in names');
assert(model.scan('stdXXmove').length===0,'Dots must not become regex wildcards');
const unknown=model.scan('Инвариант (этот комментарий не является определением)')[0];
assert(unknown.definitionEnd===unknown.end,'Never remove arbitrary parentheses');
const unrelated=model.scan('NULL (запрет отсутствующего значения)')[0];
assert(unrelated.definitionEnd===unrelated.end,'Do not collapse NOT NULL into the meaning of NULL');
assert(model.scan('ABI (набором двоичных соглашений о взаимодействии скомпилированных частей программы)')[0].definitionEnd>3,'Support inflected definition variants');
const nested=CourseTermsCore.create([{id:'demo',forms:['Термин'],inlineDefinitions:['определение (с уточнением)'],short:'x'}]).scan('Термин (определение (с уточнением)) далее')[0];
assert(nested.definitionEnd==='Термин (определение (с уточнением))'.length,'Balance nested parentheses');
for(const entry of COURSE_TERMS) {
  assert(model.entries.get(entry.id).short===entry.short,'Popup uses the shared definition');
  for(const definition of entry.inlineDefinitions) {
    const form=entry.forms.find(f=>model.scan(f)[0]?.id===entry.id);
    assert(form,'No unambiguous name for '+entry.id);
    const input=form+' ('+definition+')';
    const match=model.scan(input).find(m=>m.id===entry.id&&m.start===0);
    assert(match&&match.definitionEnd===input.length,'Approved definition not recognized: '+entry.id);
  }
}
print('PASS: shared definitions, word boundaries, NRVO/RVO, safe parenthesis removal, all approved variants');
