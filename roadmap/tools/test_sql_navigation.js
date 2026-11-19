// The genuine station reader mounted with isolated storage/history. Use its
// normal hash listener, not a slice of App with copied state indexes.
const GLib = imports.gi.GLib, BA = imports.byteArray;
const read = p => BA.toString(GLib.file_get_contents(p)[1]);
function assert(ok, msg) { if (!ok) throw Error(msg); }
const helper = read('roadmap/tools/test_station_reading_ui.js');
const boundary = helper.indexOf('let sectionLists = 0');
assert(boundary >= 0, 'Reading helper boundary changed');
const {loadStation, environment} = new Function(helper.slice(0, boundary) + ';return {loadStation,environment};')();
const env = environment(loadStation('station9-sql'), '#section=sql-trainer');
let view = env.render();
assert(view.node.props.initialSectionId === 'sql-trainer', 'Opens the real SQL trainer lesson');
function navigate(id) {
    env.win.location.hash = '#section=' + id; env.emit('hashchange');
    view = env.render(); env.preserved();
}
navigate('sql-null-basics');
assert(view.node.props.initialSectionId === 'sql-null-basics' && env.nav().props.active === 'queries', 'Hash selects the lesson and its subchapter');
navigate('sql-aggregate-basics');
assert(view.node.props.initialSectionId === 'sql-aggregate-basics' && env.nav().props.active === 'aggregation', 'Cross-subchapter navigation');
navigate('missing');
assert(view.node.props.initialSectionId === 'sql-aggregate-basics', 'Unknown hash leaves the lesson unchanged');
env.dispose();
print('PASS: embedded SQL trainer returns to theory by hash, switches subchapters and preserves progress');
