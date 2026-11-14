"use strict";
var M, assert;
if (typeof imports !== "undefined" && imports.gi) {
  var GLib = imports.gi.GLib, BA = imports.byteArray;
  (0, eval)(BA.toString(GLib.file_get_contents("roadmap/assets/network-vpn-model.js")[1]));
  M = globalThis.NetworkLabModels["vpn-tunnels"];
} else { M = require("../assets/network-vpn-model.js"); }
assert = function (value, message) { if (!value) throw new Error(message); };
function textOf(value) { return JSON.stringify(value); }
function find(id, step) { return M.getSteps(id).filter(function (s) { return s.id === step; })[0]; }
function stateAt(id, step) { return M.getState(id, M.getSteps(id).indexOf(find(id, step))); }
function has(value, text) { return textOf(value).indexOf(text) >= 0; }
function deepFrozen(value) { return !value || typeof value !== "object" || (Object.isFrozen(value) && Object.keys(value).every(function (key) { return deepFrozen(value[key]); })); }
assert(M && M.id === "vpn-tunnels", "VPN model registered");
assert(deepFrozen(M), "public metadata frozen");
assert(M.introduction.paragraphs[0].indexOf("Вы дома") === 0, "concrete understandable introduction");
var sources = M.sources.map(function (s) { return s.id; });
var phases = M.phases.map(function (p) { return p.id; });
var total = 0;
M.scenarios.forEach(function (scenario) {
  var steps = M.getSteps(scenario.id), topology = M.getTopology(scenario.id), ids = [], nodes = topology.nodes.map(function (n) { return n.id; });
  assert(steps.length >= 10, scenario.id + " substantive scenario");
  assert(deepFrozen(steps) && deepFrozen(topology), scenario.id + " frozen data");
  assert(topology.width === 880 && topology.height === 380, "topology dimensions");
  topology.links.forEach(function (link) { assert(nodes.indexOf(link.from) >= 0 && nodes.indexOf(link.to) >= 0, "real link actors"); });
  steps.forEach(function (step, index) {
    total += 1;
    assert(ids.indexOf(step.id) < 0, scenario.id + " unique step " + step.id); ids.push(step.id);
    assert(phases.indexOf(step.phase) >= 0, "known phase " + step.id);
    ["title", "summary", "changed", "visible", "protocol", "label"].forEach(function (key) { assert(typeof step[key] === "string" && step[key].length > 0, step.id + " " + key); });
    assert(step.paragraphs.length >= 1 && step.paragraphs.every(function (p) { return typeof p === "string" && p.length > 30; }), step.id + " prose");
    assert((step.from === null && step.to === null) || (nodes.indexOf(step.from) >= 0 && nodes.indexOf(step.to) >= 0), "known actor " + step.id);
    assert(step.sourceIds.length > 0 && step.sourceIds.every(function (id) { return sources.indexOf(id) >= 0; }), "read source IDs " + step.id);
    assert(step.fields.length > 0, "inspector " + step.id);
    step.fields.forEach(function (f) { assert(f.layer && f.title && f.items.length, "field shape"); f.items.forEach(function (row) { assert(row.length === 3 && row.every(function (v) { return typeof v === "string" && v.length; }), "field triple"); }); });
    var state = M.getState(scenario.id, index);
    assert(deepFrozen(state), "state frozen " + step.id);
    assert(textOf(state) === textOf(M.getState(scenario.id, index)), "state deterministic");
    assert(state.facts.length >= 3 && state.panels.length >= 1, "useful state " + step.id);
    state.facts.forEach(function (fact) { assert(["normal", "good", "warn", "bad"].indexOf(fact.tone) >= 0 && fact.label && fact.value, "fact contract"); });
    state.panels.forEach(function (p) { assert(["packet", "table", "note"].indexOf(p.type) >= 0 && p.title, "panel contract"); if (p.type === "packet") assert(p.layers.every(function (l) { return l.name && l.value && l.detail; }), "packet contract"); if (p.type === "table") assert(p.rows.every(function (row) { return row.length === p.columns.length; }), "table contract"); if (p.type === "note") assert(p.text, "note contract"); });
  });
  assert(M.getState(scenario.id, -99) === M.getState(scenario.id, 0), "lower clamp");
  assert(M.getState(scenario.id, Infinity) === M.getState(scenario.id, 0), "infinite index safe");
  assert(M.getState(scenario.id, 9999) === M.getState(scenario.id, steps.length - 1), "upper clamp");
});
assert(M.getSteps("__proto__") === M.getSteps("split") && M.getSteps("unknown") === M.getSteps("split"), "safe scenario fallback");
assert(M.getState(null, NaN) === M.getState("split", 0), "safe state fallback");
["split", "full"].forEach(function (id) {
  assert(find(id, "handshake-init").from === "client" && find(id, "handshake-response").from === "vpn", "normal handshake directions");
  assert(has(find(id, "handshake-response"), "первого корректного зашифрованного пакета"), "key confirmation qualification");
  assert(has(find(id, "inner-office").fields, "10.7.0.2 → 172.19.115.180"), "original inner addresses");
  assert(has(find(id, "outer-office").fields, "198.51.100.10 → 203.0.113.5"), "outer addresses");
  assert(!has(find(id, "outer-office").fields, "10.7.0.2 → 172.19.115.180"), "outer observer has no plaintext inner header");
  assert(has(find(id, "outer-office").visible, "не читаются"), "encrypted observer boundary explicit");
  assert(has(find(id, "gateway-decrypt").fields, "10.7.0.2 → 172.19.115.180"), "inner addresses unchanged after tunnel");
  assert(has(find(id, "office-response").fields, "172.19.115.180 → 10.7.0.2"), "reverse inner addresses");
  assert(has(find(id, "tunnel-response").fields, "203.0.113.5 → 198.51.100.10"), "reverse outer addresses");
  assert(has(find(id, "two-settings"), "операционная система") && has(find(id, "two-settings"), "AllowedIPs"), "route vs cryptokey routing");
});
assert(find("split", "public-direct").from === "home" && find("split", "public-direct").to === "public" && find("split", "public-direct").protocol === "ip", "split public route bypasses VPN");
assert(has(find("split", "public-direct").fields, "198.51.100.10 → 203.0.113.80"), "split website sees home exit");
assert(has(find("full", "public-full-route"), "IPv6 и DNS"), "full IPv4 scope not universal");
assert(has(find("full", "egress-snat").fields, "10.7.0.2 → 203.0.113.80") && has(find("full", "egress-snat").fields, "203.0.113.5 → 203.0.113.80"), "full explicit egress SNAT");
assert(has(find("full", "public-return-snat").fields, "203.0.113.80 → 10.7.0.2"), "reverse SNAT restores client");
assert(M.getSteps("missing-route").every(function (s) { return s.protocol !== "vpn"; }), "missing-route never sends tunnel control/data");
assert(find("missing-route", "physical-packet").to === "home" && find("missing-route", "physical-packet").protocol === "ip", "bad route uses physical interface");
assert(has(stateAt("missing-route", "home-drop"), "Офис не достигнут"), "failure not called success");
assert(has(find("missing-route", "repair-route"), "старый отброшенный пакет не оживает"), "fix does not resurrect packet");
assert(has(stateAt("expired-nat", "mapping-expires"), "Готовы") && has(stateAt("expired-nat", "mapping-expires"), "Запись удалена"), "NAT expiry distinct from key expiry");
assert(find("expired-nat", "incoming-to-old").to === "client" && find("expired-nat", "incoming-to-old").lost === true && find("expired-nat", "incoming-to-old").via[0] === "home", "expired mapping loses return flight at intermediate NAT, not laptop");
assert(has(find("expired-nat", "incoming-dropped"), "Ключи клиента в этом шаге не проверялись"), "NAT failure not authentication failure");
assert(has(find("expired-nat", "keepalive-out").fields, "40001 → 51820"), "outgoing new NAT mapping");
assert(has(find("expired-nat", "endpoint-learned"), "корректной аутентификации"), "endpoint update authenticated");
assert(has(find("expired-nat", "incoming-new-port").fields, "51820 → 40001"), "return to refreshed endpoint");
assert(has(find("expired-nat", "keepalive-boundary"), "не обещание обойти любой CGNAT"), "no universal NAT traversal claim");
var done = "PASS: VPN model, " + M.scenarios.length + " scenarios, " + total + " states; routes, inner/outer addresses, visibility, SNAT and NAT expiry checked.";
if (typeof print === "function") print(done); else console.log(done);
