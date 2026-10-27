// Validate the local-only script configuration without executing HTTP requests.
const GLib = imports.gi.GLib;
const ByteArray = imports.byteArray;
const source = ByteArray.toString(GLib.file_get_contents('roadmap/examples/interview_gaps/capacity.js')[1])
    .replace(/^import .*;$/gm, '').replace('export const options', 'const options')
    .replace('export default function', 'function iteration');
const build = new Function('__ENV', 'http', 'check', source + '; return {options, iteration};');
const http = {expectedStatuses: s => s, setResponseCallback: () => {},
    get: () => {throw new Error('Network calls are not allowed in this test');}};
const config = build({}, http, () => {});
if (config.options.scenarios.reads.rate !== 5) throw new Error('default rate');
for (const env of [{RATE:'0'}, {RATE:'51'}, {RATE:'NaN'}, {RATE:'1.5'},
    {TARGET:'https://example.org/'}, {TARGET:'http://127.0.0.1:8080.evil/'}]) {
    let rejected = false;
    try { build(env, http, () => {}); } catch (_) { rejected = true; }
    if (!rejected) throw new Error('Invalid environment accepted');
}
print('PASS: capacity script syntax, defaults, rate bounds and target restrictions; no k6 runtime or HTTP execution');
