/* Run from repository root: gjs roadmap/tools/test_https_journey_model.js */
"use strict";
var M, assert, read;
if (typeof imports !== "undefined" && imports.gi) {
  var GLib = imports.gi.GLib, BA = imports.byteArray;
  read = function (path) { return BA.toString(GLib.file_get_contents(path)[1]); };
  (0, eval)(read("roadmap/assets/https-journey-model.js"));
  M = globalThis.HttpsJourney;
  assert = function (value, message) { if (!value) throw new Error(message); };
} else {
  M = require("../assets/https-journey-model.js");
  assert = function (value, message) { if (!value) throw new Error(message); };
}
var total = 0, phaseIds = M.phases.map(function (p) { return p.id; });
var sourceIds = M.sources.map(function (s) { return s.id; });
var nodes = ["client", "router", "resolver", "root", "tld", "authority", "server"];
M.scenarios.forEach(function (scenario) {
  var steps = M.getSteps(scenario.id), seen = [];
  assert(steps.length >= 12, "Scenario too short: " + scenario.id);
  assert(Object.isFrozen(steps), "Shared sequence must not be mutable");
  steps.forEach(function (step, index) {
    assert(seen.indexOf(step.id) < 0, "Duplicate step id " + step.id); seen.push(step.id);
    assert(phaseIds.indexOf(step.phase) >= 0, "Unknown phase " + step.phase);
    assert(step.title && step.summary && step.changed && step.visible, "Missing explanation " + step.id);
    assert(step.paragraphs.length && step.paragraphs.every(function (p) { return typeof p === "string" && p.length > 35; }), "Empty prose " + step.id);
    assert(step.sourceIds.length && step.sourceIds.every(function (id) { return sourceIds.indexOf(id) >= 0; }), "Unknown source " + step.id);
    assert(step.fields.length && step.fields.every(function (f) { return f.layer && f.title && f.items.every(function (row) { return row.length === 3 && row.every(function (s) { return typeof s === "string" && s.length; }); }); }), "Invalid inspector " + step.id);
    assert((step.from === null && step.to === null) || (nodes.indexOf(step.from) >= 0 && nodes.indexOf(step.to) >= 0), "Invalid actors " + step.id);
    assert((step.protocol === "local") === (step.from === null), "Local event drawn as packet " + step.id);
    var state = M.getState(scenario.id, index);
    assert(JSON.stringify(state) === JSON.stringify(M.getState(scenario.id, index)), "Nondeterministic state");
    if (step.phase === "tls" || step.phase === "http") assert(state.addressKnown && state.tcpReady, "TLS/HTTP before TCP " + step.id);
    if (step.protocol === "http") assert(state.tlsReady && !state.failed, "HTTP without authenticated TLS");
    total++;
  });
});
var normal = M.getSteps("normal"), byId = function (id) { return normal.find(function (s) { return s.id === id; }); };
assert(normal.length === 20, "Normal lesson expected to have 20 steps");
assert(normal.map(function (s) { return s.id; }).slice(1, 9).join(",") === "dns-query,dns-root-query,dns-root-referral,dns-tld-query,dns-tld-referral,dns-authority-query,dns-authority-answer,dns-answer", "DNS search ordering changed");
assert(!M.getState("normal", 7).addressKnown && M.getState("normal", 8).addressKnown, "Resolver knowledge confused with client knowledge");
assert(!M.getState("normal", 10).tcpReady && M.getState("normal", 11).tcpReady, "Both TCP peers ready too early");
assert(!M.getState("normal", 15).tlsReady && M.getState("normal", 16).tlsReady, "Authenticated client prematurely sends application data");
assert(M.getState("normal", 19).rendered && M.getState("normal", 19).tlsReady, "Normal final state");
function row(step, name) { return step.fields.reduce(function (out, f) { return out.concat(f.items); }, []).find(function (r) { return r[0] === name; }); }
assert(row(byId("tcp-syn"), "SEQ")[1] === "1000", "SYN sequence");
assert(row(byId("tcp-syn-ack"), "ACK")[1] === "1001", "SYN acknowledgment must add one");
assert(row(byId("tcp-ack"), "SEQ")[1] === "1001" && row(byId("tcp-ack"), "ACK")[1] === "9001", "Final ACK numbering");
assert(!byId("tls-server-hello").fields.some(function (f) { return f.items.some(function (r) { return r[0] === "ALPN"; }); }), "TLS1.3 ALPN answer misplaced in ServerHello");
assert(byId("tls-server-flight").fields[0].items[0][0] === "EncryptedExtensions", "EncryptedExtensions missing before Certificate");
var response = byId("http-response"), body = row(response, "Тело")[1];
assert(body === "<h1>Hello!</h1>" && body.length === Number(row(response, "Content-Length")[1]), "Response body byte count (ASCII) inconsistent");
assert(M.getSteps("cached").filter(function (s) { return s.protocol === "dns"; }).length === 0, "Local cache still sends DNS packets");
assert(M.getSteps("cached")[1].id === "dns-cache-hit" && M.getState("cached", 1).addressKnown, "Cache hit absent");
assert(M.getSteps("cached").some(function (s) { return s.id === "tls-certificate-check"; }), "Cached address bypassed identity checks");
var bad = M.getSteps("bad-cert"), badState = M.getState("bad-cert", 1000);
assert(bad.every(function (s) { return s.phase !== "http" && s.id !== "tls-client-finished"; }), "Certificate failure still sends HTTP or finishes TLS");
assert(bad[bad.length - 1].id === "tls-certificate-rejected" && badState.failed && !badState.rendered && !badState.tlsReady, "Certificate failure state");
assert(bad.find(function (s) { return s.id === "tls-server-flight"; }).fields[0].items[1][1] === "DNS-ID: other.example.com", "Bad certificate not shown in prior message");
assert(byId("tls-server-flight").fields[0].items[1][1] === "DNS-ID: notes.example.com", "Bad certificate mutated normal scenario");
assert(M.getSteps("unknown") === normal && M.getSteps("__proto__") === normal, "Invalid scenario fallback");
assert(JSON.stringify(M.getState("normal", NaN)) === JSON.stringify(M.getState("normal", 0)), "Invalid step fallback");
assert(JSON.stringify(M.getState("normal", -1)) === JSON.stringify(M.getState("normal", 0)), "Negative step clamp");
assert(JSON.stringify(M.getState("normal", 1e8)) === JSON.stringify(M.getState("normal", 19)), "Large step clamp");
assert(M.assumptions.some(function (s) { return s.indexOf("не выполняет TLS") >= 0; }), "Model boundary missing");
var output = "PASS: HTTPS journey — " + total + " step states across 3 scenarios; message order, cache, TCP numbering, TLS identity and HTTP body checked";
if (typeof print === "function") print(output); else console.log(output);
