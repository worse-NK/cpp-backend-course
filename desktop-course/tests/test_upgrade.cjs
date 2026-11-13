'use strict';
// Upgrade/data-format checks use artificial in-memory storage, never a reader profile.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const progress = require('../web/progress-core.js');
const root = path.resolve(__dirname, '../..');
const content = path.join(root, 'roadmap/content');
function storage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    get length() {return values.size;},
    key(index) {return [...values.keys()][index];},
    getItem(key) {return values.has(key) ? values.get(key) : null;},
    setItem(key, value) {values.set(key, String(value));},
    removeItem(key) {values.delete(key);},
  };
}
const before = {};
const stations = fs.readdirSync(content).filter(name => /^station.*\.json$/.test(name));
assert.equal(stations.length, 21);
for (const name of stations) {
  const station = JSON.parse(fs.readFileSync(path.join(content, name), 'utf8'));
  assert(progress.allowedKey(station.meta.storeKey), station.meta.storeKey);
  before[station.meta.storeKey] = JSON.stringify({['sec:' + station.theory[0].id]:true});
}
before.cpp_course_last_read_v1 = JSON.stringify({file:'cpp_station0_oop_basics.html',section:'why-oop',title:'Учебная закладка'});
before.cpp_course_text_size_v1 = 'large';
before['cpp-sql-lab:v1:expression'] = 'SELECT 42;';
const original = storage(before);
for (const previousVersion of ['1.0.0', '1.1.0']) {
  const snapshot = progress.exportSnapshot(original, {origin:'course://app',version:previousVersion});
  assert.equal(progress.validateSnapshot(snapshot), Object.keys(before).length);
  const updated = storage({unrelated:'preserve this value'});
  progress.importSnapshot(updated, snapshot);
  for (const [key, value] of Object.entries(before)) assert.equal(updated.getItem(key), value, previousVersion + ':' + key);
  assert.equal(updated.getItem('unrelated'), 'preserve this value');
}
const main = fs.readFileSync(path.join(root, 'desktop-course/app/main.cjs'), 'utf8');
assert(main.includes("path.join(app.getPath('appData'), 'cpp-backend-course-desktop')"));
assert(main.includes("'course://app/roadmap/cpp_backend_roadmap.html'"));
console.log(JSON.stringify({passed:true,stations:stations.length,preservedEntries:Object.keys(before).length,sourceVersions:['1.0.0','1.1.0'],personalProfileAccessed:false}));
