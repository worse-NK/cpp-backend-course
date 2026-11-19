/* Run from repository root: gjs roadmap/tools/test_network_routing_model.js */
"use strict";
var M;
if (typeof imports !== "undefined" && imports.gi) {
  var GLib = imports.gi.GLib, BA = imports.byteArray;
  (0, eval)(BA.toString(GLib.file_get_contents("roadmap/assets/network-routing-model.js")[1]));
  M = globalThis.NetworkLabModels.packetpath;
} else M = require("../assets/network-routing-model.js");
function assert(condition, message) { if (!condition) throw new Error(message); }
function text(value) { return typeof value === "string" && value.length > 0 && !/<\/?[a-z][^>]*>/i.test(value); }
function json(value) { return JSON.stringify(value); }
function frozen(value) { if (value && typeof value === "object") { assert(Object.isFrozen(value), "Mutable shared lesson data"); Object.keys(value).forEach(function (key) { frozen(value[key]); }); } }
function index(scenario, id) { var n = M.getSteps(scenario).findIndex(function (s) { return s.id === id; }); assert(n >= 0, "Missing step " + scenario + ":" + id); return n; }
function at(scenario, id) { return M.getState(scenario, index(scenario, id)); }
function metric(scenario, id) { return at(scenario, id).metrics; }
function packet(scenario, id) { return metric(scenario, id).packet; }
function size(p) { return (p.version === 6 ? 40 : 20) + 8 + p.payload; }
function row(step, name) { var rows = []; step.fields.forEach(function (f) { rows = rows.concat(f.items); }); return rows.find(function (r) { return r[0] === name; }); }
var phases = M.phases.map(function (p) { return p.id; }), sources = M.sources.map(function (s) { return s.id; }), count = 0;
assert(M.id === "packetpath", "Registry id changed");
var probe = M.mtuExperiment;
[[1399,1351,true],[1400,1352,true],[1401,1353,false]].forEach(function (test) {
  var before = probe.send(test[0]), after = probe.receivePtb(before);
  assert(before.payload === test[1] && before.lan && before.wan === test[2], "Wrong hop or UDP payload for " + test[0]);
  assert(before.estimate === 1500 && before.ptb === (before.wan ? "none" : "in-flight"), "Sender knew about undersized hop before PTB");
  assert(after.estimate === (before.wan ? 1500 : 1400) && after.wan === before.wan && after.size === before.size, "Feedback changed the original datagram");
  assert(probe.receivePtb(after) === after, "Impossible duplicate feedback advanced probe");
});
assert(M.scenarios.map(function (s) { return s.id; }).join(",") === "routed,snat,filtered,pmtu6,ttl", "Required scenarios missing");
assert(M.introduction.paragraphs.length >= 2 && M.introduction.paragraphs.every(text) && text(M.introduction.goal) && text(M.introduction.action), "Introduction missing");
assert(M.assumptions.length >= 9 && M.assumptions.every(text), "Model conditions missing");
M.sources.forEach(function (s) { assert(/^https:\/\/www\.rfc-editor\.org\/rfc\/rfc\d+\.html/.test(s.url) && text(s.title) && text(s.description), "Primary-source reference missing"); });
M.scenarios.forEach(function (scenario) {
  var steps = M.getSteps(scenario.id), topology = M.getTopology(scenario.id), seen = [];
  assert(steps.length >= 5, "Scenario without a complete explanation"); frozen(steps); frozen(topology);
  assert(topology.width === 880 && topology.height === 350 && topology.nodes.length === 3 && topology.links.length === 2, "Unexpected network shape");
  var nodes = topology.nodes.map(function (node) {
    assert(node.x >= 0 && node.x <= 880 && node.y >= 0 && node.y <= 350 && node.kind && node.title && node.address, "Invalid node"); return node.id;
  });
  topology.links.forEach(function (link) { assert(nodes.indexOf(link.from) >= 0 && nodes.indexOf(link.to) >= 0, "Dangling link"); });
  steps.forEach(function (step, n) {
    assert(seen.indexOf(step.id) < 0, "Duplicate step id"); seen.push(step.id);
    assert(phases.indexOf(step.phase) >= 0 && ["local", "ip", "icmp"].indexOf(step.protocol) >= 0, "Unknown phase or protocol");
    [step.title, step.summary, step.changed, step.visible, step.label].forEach(function (s) { assert(text(s), "Missing prose " + step.id); });
    assert(step.paragraphs.length >= 2 && step.paragraphs.every(function (s) { return text(s) && s.length >= 45; }), "Thin step explanation " + step.id);
    assert(step.fields.length && step.fields.every(function (f) { return text(f.layer) && text(f.title) && f.items.length && f.items.every(function (r) { return r.length === 3 && r.every(text); }); }), "Invalid packet inspector");
    assert(step.sourceIds.length && step.sourceIds.every(function (id) { return sources.indexOf(id) >= 0; }), "Unknown source");
    assert(step.protocol === "local" ? step.from === null && step.to === null : nodes.indexOf(step.from) >= 0 && nodes.indexOf(step.to) >= 0 && step.from !== step.to, "Invalid message endpoints");
    if (step.protocol !== "local") assert(topology.links.some(function (link) { return link.from === step.from && link.to === step.to || link.to === step.from && link.from === step.to; }), "Network event silently skipped a link");
    var state = M.getState(scenario.id, n), m = state.metrics;
    frozen(state); assert(json(state) === json(M.getState(scenario.id, n)), "Nondeterministic snapshot");
    assert(state.facts.length >= 3 && state.facts.every(function (f) { return text(f.label) && text(f.value) && ["normal", "good", "warn", "bad"].indexOf(f.tone) >= 0; }), "Invalid facts");
    state.panels.forEach(function (panel) {
      assert(text(panel.title), "Panel lacks title");
      if (panel.type === "packet") {
        assert(panel.layers.length >= 3 && panel.layers.every(function (layer) { return text(layer.name) && text(layer.value) && text(layer.detail); }), "Incomplete encapsulation panel");
      } else if (panel.type === "table") assert(panel.columns.every(text) && panel.rows.every(function (r) { return r.length === panel.columns.length && r.every(text); }), "Table mismatch");
      else if (panel.type === "note") assert(text(panel.text), "Empty note");
      else throw new Error("Unsupported panel " + panel.type);
    });
    if (m.packet) {
      assert(state.panels[0].type === "packet", "Current packet hidden");
      assert(row(step, "Источник IP")[1] === m.packet.src && row(step, "Получатель IP")[1] === m.packet.dst, "Inspector differs from diagram state");
      assert(row(step, "Источник MAC")[1] === m.packet.srcMac && row(step, "Получатель MAC")[1] === m.packet.dstMac, "Ethernet inspector stale");
      assert(Number(row(step, m.packet.version === 6 ? "Hop Limit" : "TTL")[1]) === m.packet.limit, "Hop limit inspector stale");
      assert(m.packet.limit >= 0 && m.packet.limit <= 255, "Invalid TTL/Hop Limit");
      if (m.packet.transport === "UDP") {
        assert(Number(row(step, "Размер IP-пакета")[1]) === size(m.packet), "Packet size arithmetic wrong");
        assert(Number(row(step, "Длина UDP")[1]) === m.packet.payload + 8, "UDP length arithmetic wrong");
      }
    }
    assert(!m.serverRead || m.requestDelivered, "Application read an undelivered request");
    assert(!m.clientRead || m.replyDelivered, "Client read an undelivered response");
    assert(!m.replyDelivered || m.serverRead, "Service replied before reading its request");
    if (scenario.id === "routed" || scenario.id === "snat") assert(!m.dropped, "Normal exchange unexpectedly dropped");
    if (scenario.id !== "snat") assert(!m.mapping, "NAT silently required for routing");
    count++;
  });
  assert(M.getState(scenario.id, -1) === M.getState(scenario.id, 0), "Negative index not clamped");
  assert(M.getState(scenario.id, NaN) === M.getState(scenario.id, 0), "NaN index not clamped");
  assert(M.getState(scenario.id, 1.8) === M.getState(scenario.id, 1), "Fractional index not floored");
  assert(M.getState(scenario.id, 9999) === M.getState(scenario.id, steps.length - 1), "Large index not clamped");
});
var first = packet("routed", "request-lan"), next = packet("routed", "request-wan");
assert(first.src === next.src && first.dst === next.dst && first.srcPort === next.srcPort && first.dstPort === next.dstPort, "Plain routing changes endpoint addresses");
assert(first.limit === 64 && next.limit === 63, "IPv4 TTL not decremented exactly once in chosen model");
assert(first.srcMac !== next.srcMac && first.dstMac !== next.dstMac, "Router forwarded old Ethernet frame");
assert(first.dstMac === "02:00:00:00:01:01" && next.dstMac === "02:00:00:00:02:20", "Wrong next-hop MAC");
assert(size(first) === 540 && size(next) === 540 && next.payload === 512, "IPv4 request sizes wrong");
assert(size(packet("routed", "reply-wan")) === 92 && packet("routed", "reply-lan").limit === 63, "Reply length or TTL wrong");
assert(metric("routed", "client-checks-reply").clientRead && metric("routed", "client-checks-reply").originalDelivered, "Routed exchange incomplete");
var beforeNat = packet("snat", "request-lan"), afterNat = packet("snat", "request-wan"), backNat = packet("snat", "reply-wan"), restored = packet("snat", "reply-lan");
assert(beforeNat.src === "192.0.2.10" && beforeNat.srcPort === 40000, "NAT source before translation wrong");
assert(afterNat.src === "198.51.100.1" && afterNat.srcPort === 52000 && afterNat.dst === "198.51.100.20" && afterNat.dstPort === 9000, "SNAT mapping wrong");
assert(backNat.dst === "198.51.100.1" && backNat.dstPort === 52000, "Server bypassed NAT return mapping");
assert(restored.dst === "192.0.2.10" && restored.dstPort === 40000 && restored.src === "198.51.100.20" && restored.srcPort === 9000, "Reverse translation wrong");
assert(metric("snat", "router-forward").mapping && afterNat.checksum.indexOf("UDP") >= 0, "Mapping/checksum explanation absent");
assert(M.getSteps("filtered").filter(function (s) { return s.from; }).length === 1, "Filtered request invented outgoing traffic");
assert(!metric("filtered", "no-reply").requestDelivered && !metric("filtered", "no-reply").replyDelivered && metric("filtered", "no-reply").dropped, "Filter delivered blocked traffic");
assert(metric("filtered", "no-reply").dropReason.indexOf("forward") >= 0, "Explicit forward policy lost");
assert(packet("ttl", "request-lan").limit === 1 && packet("ttl", "ttl-exhausted").limit === 0, "TTL1 path wrong");
assert(!metric("ttl", "ttl-conclusion").requestDelivered && !metric("ttl", "ttl-conclusion").replyDelivered, "TTL error counted as service response");
assert(packet("ttl", "time-exceeded").transport === "ICMP" && packet("ttl", "time-exceeded").limit === 64, "ICMP inherited expired TTL");
assert(M.getSteps("ttl").every(function (s) { return s.to !== "server"; }), "Expired packet reached server");
assert(size(packet("pmtu6", "request-lan")) === 1448 && packet("pmtu6", "request-lan").version === 6, "IPv6 initial size wrong");
assert(!metric("pmtu6", "packet-too-large").requestDelivered && metric("pmtu6", "packet-too-large").dropped, "Oversized IPv6 forwarded");
assert(packet("pmtu6", "packet-too-big").transport === "ICMPv6" && !metric("pmtu6", "packet-too-big").replyDelivered, "PTB confused with UDP reply");
assert(metric("pmtu6", "learn-pmtu").knownMtu === 1400, "PMTU not updated");
var small = packet("pmtu6", "new-smaller-probe");
assert(small.payload === 1352 && size(small) === 1400 && small.probe === 2 && metric("pmtu6", "new-smaller-probe").smallerProbeCreated, "UDP message silently truncated instead of new probe");
assert(!metric("pmtu6", "new-smaller-probe").originalDelivered && !metric("pmtu6", "new-smaller-probe").requestDelivered, "New probe already delivered");
assert(size(packet("pmtu6", "smaller-request-wan")) === 1400 && packet("pmtu6", "smaller-request-wan").limit === 63, "Smaller packet misses MTU or Hop Limit");
assert(metric("pmtu6", "client-checks-reply").clientRead && !metric("pmtu6", "client-checks-reply").originalDelivered, "PMTU recovery misreports original delivery");
assert(M.getSteps("pmtu6").filter(function (s) { return s.to === "server"; }).every(function (s) { return s.id === "smaller-request-wan"; }), "Original IPv6 or fake fragments reached server");
assert(M.getSteps("__proto__") === M.getSteps("routed") && M.getState("unknown", 0) === M.getState("routed", 0), "Unsafe scenario fallback");
var original = M.getSteps("routed")[0].title;
try { M.getSteps("routed")[0].title = "changed"; } catch (_) {}
assert(M.getSteps("routed")[0].title === original, "Caller modified shared lesson");
if (typeof print === "function") print("PASS: routing lab — " + count + " snapshots; routing, SNAT, filtering, IPv6 PMTU and TTL checked.");
else console.log("PASS: routing lab — " + count + " snapshots; routing, SNAT, filtering, IPv6 PMTU and TTL checked.");
