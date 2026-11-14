#!/usr/bin/env gjs
/* Offline contract and protocol-invariant checks. Run from repository root. */
"use strict";
const GLib = imports.gi.GLib;
const ByteArray = imports.byteArray;
const path = "roadmap/assets/network-config-model.js";
const source = ByteArray.toString(GLib.file_get_contents(path)[1]);
(0, eval)(source);
const model = globalThis.NetworkLabModels["network-setup"];
let checks = 0;
function assert(value, message) {
  checks++;
  if (!value) throw new Error(message);
}
function same(a, b, message) { assert(JSON.stringify(a) === JSON.stringify(b), message); }
function isText(value) { return typeof value === "string" && value.trim().length > 0; }
function index(scenario, id) {
  const result = model.getSteps(scenario).findIndex(s => s.id === id);
  assert(result >= 0, "Missing step " + scenario + ":" + id);
  return result;
}
function item(scenario, id, label) {
  const found = model.getSteps(scenario)[index(scenario, id)].fields
    .reduce((out, group) => out.concat(group.items), []).find(row => row[0] === label);
  assert(Boolean(found), "Missing field " + id + ":" + label);
  return found[1];
}
function state(scenario, id) { return model.getState(scenario, index(scenario, id)); }
function stateText(scenario, id) { return JSON.stringify(state(scenario, id)); }
function frozen(value, location) {
  if (!value || typeof value !== "object") return;
  assert(Object.isFrozen(value), "Mutable data at " + location);
  Object.keys(value).forEach(key => frozen(value[key], location + "." + key));
}
assert(model && model.id === "network-setup", "Registry export missing");
assert(isText(model.title) && isText(model.summary), "Model identity text");
assert(model.introduction.paragraphs.length >= 2 && model.introduction.paragraphs.every(isText), "Concrete introduction");
assert(isText(model.introduction.goal) && isText(model.introduction.action), "Introduction goal and action");
same(model.scenarios.map(s => s.id), ["dhcp", "arp", "ipv6"], "Three intended scenarios");
const phases = new Set(model.phases.map(p => p.id));
const sourceIds = new Set(model.sources.map(s => s.id));
assert(phases.size === model.phases.length, "Unique phase IDs");
assert(sourceIds.size === model.sources.length, "Unique source IDs");
model.sources.forEach(s => assert(isText(s.title) && /^https:\/\/www\.rfc-editor\.org\/rfc\//.test(s.url) && isText(s.description), "Primary source record " + s.id));
assert(model.assumptions.length >= 8 && model.assumptions.every(isText), "Explicit model limits");
const allSteps = new Set();
const protocols = new Set(["local", "dhcp", "arp", "icmp", "ip", "dns"]);
model.scenarios.forEach(scenario => {
  const steps = model.getSteps(scenario.id), topology = model.getTopology(scenario.id);
  const nodes = new Set(topology.nodes.map(n => n.id));
  assert(steps.length >= 8 && steps.length <= 15, "Scenario length " + scenario.id);
  assert(topology.width === 880 && topology.height === 380, "Topology coordinate system");
  assert(nodes.size === topology.nodes.length, "Unique topology nodes");
  topology.nodes.forEach(n => {
    assert(isText(n.id) && isText(n.title) && isText(n.address), "Node text " + n.id);
    assert(["laptop", "router", "server", "dns", "switch"].includes(n.kind), "Supported node kind " + n.id);
    assert(n.x >= 0 && n.x <= topology.width && n.y >= 0 && n.y <= topology.height, "Node inside canvas " + n.id);
  });
  topology.links.forEach(link => assert(nodes.has(link.from) && nodes.has(link.to) && isText(link.label), "Valid topology link"));
  let previousPhase = -1;
  steps.forEach((s, position) => {
    assert(!allSteps.has(s.id), "Unique global step ID " + s.id);
    allSteps.add(s.id);
    ["id", "title", "summary", "changed", "visible", "label"].forEach(key => assert(isText(s[key]), "Step text " + s.id + ":" + key));
    assert(s.paragraphs.length >= 2 && s.paragraphs.every(isText), "Step explanation " + s.id);
    assert(phases.has(s.phase), "Known phase " + s.id);
    const currentPhase = model.phases.findIndex(p => p.id === s.phase);
    assert(currentPhase >= previousPhase, "Monotonic phase navigation " + s.id);
    previousPhase = currentPhase;
    assert(protocols.has(s.protocol), "Supported protocol " + s.id);
    if (s.protocol === "local") assert(s.from === null && s.to === null && !s.broadcastTo, "Local event must not imply packet " + s.id);
    else assert(nodes.has(s.from) && nodes.has(s.to), "Transmission endpoints " + s.id);
    if (s.broadcastTo) {
      assert(s.broadcastTo.length > 0 && new Set(s.broadcastTo).size === s.broadcastTo.length, "Distinct fan-out targets " + s.id);
      s.broadcastTo.forEach(n => assert(nodes.has(n) && n !== s.from, "Fan-out target " + s.id + ":" + n));
      assert(isText(s.direction), "Explain multi-recipient direction " + s.id);
    }
    assert(s.sourceIds.length > 0 && s.sourceIds.every(id => sourceIds.has(id)), "Relevant known sources " + s.id);
    assert(s.fields.length > 0, "Fields exist " + s.id);
    s.fields.forEach(group => {
      assert(isText(group.layer) && isText(group.title) && group.items.length > 0, "Inspector group " + s.id);
      group.items.forEach(row => assert(row.length === 3 && row.every(isText), "Explained inspector row " + s.id));
    });
    const snapshot = model.getState(scenario.id, position);
    assert(snapshot.facts.length >= 4, "Useful facts " + s.id);
    snapshot.facts.forEach(f => assert(isText(f.label) && isText(f.value) && ["normal", "good", "warn", "bad"].includes(f.tone), "Fact " + s.id));
    assert(snapshot.panels.length >= 2, "State panels " + s.id);
    snapshot.panels.forEach(panel => {
      assert(isText(panel.title), "Panel title");
      if (panel.type === "table") {
        assert(panel.columns.length > 0 && panel.columns.every(isText), "Table columns");
        panel.rows.forEach(row => assert(row.length === panel.columns.length && row.every(isText), "Table row dimensions"));
        assert(isText(panel.note), "Table limitation note");
      } else if (panel.type === "packet") {
        assert(panel.layers.length >= 2, "Layer comparison");
        panel.layers.forEach(layer => assert(isText(layer.name) && isText(layer.value) && isText(layer.detail), "Explained packet layer"));
        assert(isText(panel.note), "Packet note");
      } else assert(panel.type === "note" && isText(panel.text), "Supported note panel");
    });
    frozen(snapshot, scenario.id + ".state." + position);
    same(snapshot, model.getState(scenario.id, position), "Deterministic state " + s.id);
  });
  same(model.getState(scenario.id, -100), model.getState(scenario.id, 0), "Negative index clamps");
  same(model.getState(scenario.id, 10000), model.getState(scenario.id, steps.length - 1), "Large index clamps");
  same(model.getState(scenario.id, NaN), model.getState(scenario.id, 0), "Invalid index fallback");
  same(model.getState(scenario.id, 2.75), model.getState(scenario.id, 2), "Fraction index normalizes");
  frozen(steps, scenario.id + ".steps"); frozen(topology, scenario.id + ".topology");
});
frozen(model, "API");
same(model.getSteps("unknown"), model.getSteps("dhcp"), "Unknown scenario fallback");
same(model.getTopology("unknown"), model.getTopology("dhcp"), "Unknown topology fallback");
same(model.getState("unknown", 0), model.getState("dhcp", 0), "Unknown state fallback");

// The chosen initial DORA path is not four unicast hops.
const dora = model.getSteps("dhcp").filter(s => s.protocol === "dhcp");
same(dora.map(s => s.label), ["DHCPDISCOVER", "DHCPOFFER", "DHCPREQUEST", "DHCPACK"], "DORA ordering");
dora.forEach(s => {
  same(s.broadcastTo, s.from === "client" ? ["dhcp", "router"] : ["client", "router"], "Selected DHCP broadcast recipients " + s.id);
  assert(s.fields.some(f => f.items.some(row => row[0] === "BROADCAST" && row[1] === "1")), "Explicit broadcast flag");
  assert(s.fields.some(f => f.items.some(row => row[0] === "Получатель" && row[1] === "ff:ff:ff:ff:ff:ff")), "Ethernet broadcast");
});
assert(item("dhcp", "dhcp-request", "Requested IP Address") === "192.0.2.20", "Request selects offered IP");
assert(item("dhcp", "dhcp-request", "Server Identifier") === "192.0.2.2", "Request selects server, not gateway");
["dhcp-offer", "dhcp-ack", "dhcp-probe", "dhcp-check-complete"].forEach(id => assert(state("dhcp", id).facts[0].value === "ещё не используется", "No premature IPv4 use at " + id));
assert(state("dhcp", "dhcp-announce").facts[0].value === "192.0.2.20/24", "Use only after conflict check and announcement");
assert(item("dhcp", "dhcp-probe", "Sender IP") === "0.0.0.0", "Probe does not claim address");
assert(item("dhcp", "dhcp-probe", "Target IP") === "192.0.2.20", "Probe tests own candidate, not gateway");
assert(index("dhcp", "dhcp-probe") < index("dhcp", "dhcp-check-complete") && index("dhcp", "dhcp-check-complete") < index("dhcp", "dhcp-announce"), "Probe, wait and use separate");
assert(item("dhcp", "dhcp-lease-time", "T1").includes("передано явно"), "T1 example not universal half-lease claim");
assert(stateText("dhcp", "dhcp-configured").includes("192.0.2.53") && stateText("dhcp", "dhcp-configured").includes("192.0.2.1") && stateText("dhcp", "dhcp-configured").includes("192.0.2.2"), "Server, gateway and DNS distinct roles");

// Route first, then resolve only the next hop, then put remote IP inside gateway frame.
assert(index("arp", "arp-route") < index("arp", "arp-request"), "Route before ARP");
assert(item("arp", "arp-request", "Target IP") === "192.0.2.1", "ARP resolves gateway, not remote server");
assert(item("arp", "arp-send", "Назначение MAC") === "02:00:00:00:00:01", "First-hop frame to router");
assert(item("arp", "arp-send", "Назначение IP") === "203.0.113.20", "IP remains remote destination");
const neighborTable = state("arp", "arp-cache-store").panels.find(p => p.type === "table");
same(neighborTable.rows, [["192.0.2.1", "02:00:00:00:00:01", "соответствие сохранено"]], "Only local gateway in ARP cache");
assert(!model.getTopology("arp").nodes.some(n => n.address === "203.0.113.20"), "Remote server not drawn as LAN peer");
assert(model.getSteps("arp").filter(s => s.protocol === "arp").length === 2, "No forwarded ARP request on remote network");

// IPv6 address readiness, default route and neighbor identity are separate.
assert(!model.getSteps("ipv6").some(s => s.protocol === "arp" || s.protocol === "dhcp"), "No ARP or implicit DHCPv6 for SLAAC path");
assert(index("ipv6", "v6-dad-link-local") < index("ipv6", "v6-dad-link-local-complete") && index("ipv6", "v6-dad-link-local-complete") < index("ipv6", "v6-rs"), "Link-local DAD before used-source RS");
assert(item("ipv6", "v6-dad-link-local", "Источник → назначение").startsWith(":: → "), "DAD unspecified source");
assert(item("ipv6", "v6-dad-global", "Источник → назначение").startsWith(":: → "), "Global DAD unspecified source too");
assert(item("ipv6", "v6-dad-link-local", "Target Address") === "fe80::20", "Local candidate DAD target");
assert(item("ipv6", "v6-dad-global", "Target Address") === "2001:db8:7::20", "Separate global candidate DAD target");
assert(item("ipv6", "v6-ra", "Router Lifetime") === "1800 s" && item("ipv6", "v6-ra", "Preferred / Valid Lifetime") === "3600 s / 7200 s", "Router and address lifetimes differ");
assert(item("ipv6", "v6-ra", "A / L") === "1 / 1", "Explicit autonomous/on-link flags");
assert(state("ipv6", "v6-global-tentative").facts[1].value.includes("tentative"), "RA not automatic global readiness");
assert(state("ipv6", "v6-dad-global-complete").facts[1].value.includes("готов"), "Readiness only after full DAD wait");
assert(item("ipv6", "v6-neighbor-solicitation", "Target Address") === "fe80::1", "ND resolves next hop");
assert(item("ipv6", "v6-neighbor-solicitation", "Source Link-Layer Address") === "02:00:00:00:00:20", "Ordinary NS has source MAC option");
assert(state("ipv6", "v6-dad-global-complete").facts[3].value === "ещё неизвестен", "No invented MAC option in RA");
assert(state("ipv6", "v6-neighbor-advertisement").facts[3].value === "02:00:00:00:00:01", "NA supplies neighbor MAC");
assert(item("ipv6", "v6-ready", "DNS / сайт") === "не проверены", "Address success not invented DNS or web success");
const independentFlags = item("ipv6", "v6-separate-ra-effects", "L = 1");
assert(independentFlags.includes("on-link"), "On-link meaning separate from address creation");
assert(!/\b(?:fetch|XMLHttpRequest|WebSocket|setInterval|setTimeout)\s*\(/.test(source), "Offline model has no network/timing side effects");
print("network-config-model: " + checks + " checks passed; " + model.scenarios.length + " scenarios, " + allSteps.size + " steps");
