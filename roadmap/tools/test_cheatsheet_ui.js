// Behavior tests with a small DOM double: no browser, no stored user data.
const GLib = imports.gi.GLib, ByteArray = imports.byteArray;
const read = path => ByteArray.toString(GLib.file_get_contents(path)[1]);
function assert(ok, message) { if (!ok) throw new Error(message); }
class Element {
    constructor(text = '') { this.textContent = text; this.hidden = false; this.open = true; this.events = {}; this.attrs = {}; this.tabIndex = -1; }
    addEventListener(name, fn) { this.events[name] = fn; }
    focus() { this.focused = true; }
    scrollIntoView() { this.scrolled = true; }
    closest() { return this.group || null; }
    matches() { return !!this.isGroup; }
    setAttribute(name, value) { this.attrs[name] = value; }
    removeAttribute(name) { delete this.attrs[name]; }
}
const data = JSON.parse(read('roadmap/content/cheatsheet.json'));
const ids = {}, groups = [], nav = [];
data.stations.forEach(station => {
    const group = new Element(); group.isGroup = true; group.group = group;
    group.id = station.num === '5Б' ? 'station-5-linux' : station.num === '7Б' ? 'station-7-netlab' : /^\d+$/.test(station.num) ? 'station-' + station.num : station.num === '★' ? 'code-review' : 'std-functions';
    ids[group.id] = group;
    const title = new Element(station.title), summary = new Element(), toc = new Element(), pages = new Element();
    const sections = station.sections.map((part, i) => {
        const section = new Element(); section.group = group; ids[group.id + '-section-' + (i + 1)] = section;
        const items = part.items.map(item => new Element(Object.values(item).join(' ')));
        section.querySelector = () => new Element(part.h);
        section.querySelectorAll = () => items;
        return section;
    });
    group.querySelector = selector => ({ h2: title, summary, '.section-toc': toc, '.chapter-pagination': pages })[selector];
    group.querySelectorAll = () => sections;
    groups.push(group);
    const link = new Element(); link.hash = '#' + group.id; nav.push(link);
});
['reference-search', 'search-status', 'clear-search', 'expand-all', 'collapse-all'].forEach(id => { ids[id] = new Element(); });
ids['reference-search'].value = '';
const panel = new Element(), contents = new Element();
const documentEvents = {}, windowEvents = {};
const document = {
    getElementById: id => ids[id],
    querySelector: selector => selector === '.search-panel' ? panel : contents,
    querySelectorAll: selector => selector === '.reference-group' ? groups : selector === 'aside nav a' ? nav : [],
    addEventListener: (name, fn) => { documentEvents[name] = fn; }
};
const window = { matchMedia: () => ({matches: true}), addEventListener: (name, fn) => { windowEvents[name] = fn; } };
const location = { hash: '' };
new Function('document', 'window', 'location', read('roadmap/assets/cheatsheet.js'))(document, window, location);
assert(!panel.hidden && !contents.open, 'Search enhanced; mobile contents collapsed');
ids['collapse-all'].events.click();
assert(groups.every(group => !group.open), 'Collapse all');
const input = ids['reference-search']; input.value = 'ETag'; input.events.input();
assert(!ids['station-8'].hidden && ids['station-8'].open && groups[0].hidden, 'Search finds API and opens its group');
input.value = 'no-such-concept-xyz'; input.events.input();
assert(groups.every(group => group.hidden), 'No matches');
assert(ids['search-status'].textContent.includes('Ничего'), 'No-results status');
location.hash = '#station-7-section-5'; windowEvents.hashchange();
assert(input.value === '' && groups.every(group => !group.hidden), 'Navigation clears search');
assert(ids['station-7'].open && !groups[0].open, 'Navigation opens target and restores other collapse states');
assert(ids['station-7-section-5'].focused, 'Hash navigation focuses the section');
assert(nav.find(link => link.hash === '#station-7').attrs['aria-current'] === 'location', 'Current location is accessible');
ids['station-7'].open = false;
let prevented = false;
documentEvents.click({target: {closest: () => ({hash: location.hash})}, button: 0, preventDefault: () => { prevented = true; }});
assert(prevented && ids['station-7'].open, 'Repeated anchor reopens collapsed group');
location.hash = '#station-8'; windowEvents.hashchange();
location.hash = '#station-7-section-5'; windowEvents.hashchange();
assert(nav.find(link => link.hash === '#station-7').attrs['aria-current'] && !nav.find(link => link.hash === '#station-8').attrs['aria-current'], 'Back navigation restores location');
location.hash = '#station-5-linux-section-1'; windowEvents.hashchange();
assert(ids['station-5-linux'].open && ids['station-5-linux-section-1'].focused, 'Linux suffix uses its own stable anchor');
location.hash = '#station-7-netlab-section-1'; windowEvents.hashchange();
assert(ids['station-7-netlab'].open && ids['station-7-netlab-section-1'].focused, 'Network lab suffix uses its own stable anchor');
ids['expand-all'].events.click(); assert(groups.every(group => group.open), 'Expand all');
print('PASS: search, empty results, open-state restore, hash/deep links, back/repeated navigation, mobile contents');
