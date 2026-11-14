/* Run from repository root: gjs roadmap/tools/test_network_tcp_model.js */
"use strict";
var M, assert, read;
if (typeof imports !== "undefined" && imports.gi) {
  var GLib = imports.gi.GLib, BA = imports.byteArray;
  read = function (path) { return BA.toString(GLib.file_get_contents(path)[1]); };
  (0, eval)(read("roadmap/assets/network-tcp-model.js"));
  M = globalThis.NetworkLabModels["tcp-delivery"];
} else {
  M = require("../assets/network-tcp-model.js");
}
assert = function (condition, message) { if (!condition) throw new Error(message); };
var sourceIds = M.sources.map(function (item) { return item.id; });
var phaseIds = M.phases.map(function (item) { return item.id; });
var statuses = ["waiting", "sent", "acked", "buffered", "missing", "delivered", "blocked"];
var count = 0;
function isText(text) { return typeof text === "string" && text.length > 0 && !/<\/?[a-z][^>]*>/i.test(text); }
function field(step, name) {
  var rows = [];
  step.fields.forEach(function (section) { rows = rows.concat(section.items); });
  var result = rows.find(function (row) { return row[0] === name; });
  assert(result, "Missing field " + name + " at " + step.id);
  return result[1];
}
function index(scenario, id) {
  var n = M.getSteps(scenario).findIndex(function (item) { return item.id === id; });
  assert(n >= 0, "Missing step " + scenario + ":" + id); return n;
}
function at(scenario, id) { return M.getState(scenario, index(scenario, id)); }
function metrics(scenario, id) { return at(scenario, id).metrics; }
function item(scenario, id) { return M.getSteps(scenario)[index(scenario, id)]; }
function json(value) { return JSON.stringify(value); }
function checkFrozen(value) {
  if (!value || typeof value !== "object") return;
  assert(Object.isFrozen(value), "Mutable shared data");
  Object.keys(value).forEach(function (key) { checkFrozen(value[key]); });
}
assert(M.id === "tcp-delivery", "Wrong registry id");
assert(M.scenarios.map(function (s) { return s.id; }).join(",") === "ordered,reordered,loss,close", "Four TCP scenarios required");
assert(M.introduction.paragraphs.length >= 2 && M.introduction.paragraphs.every(isText), "Concrete introduction missing");
assert(isText(M.introduction.goal) && isText(M.introduction.action), "Introduction guidance missing");
assert(M.assumptions.length >= 7 && M.assumptions.every(isText), "Explicit model boundaries missing");
M.sources.forEach(function (source) {
  assert(sourceIds.filter(function (id) { return id === source.id; }).length === 1, "Duplicate source");
  assert(/^https:\/\/www\.rfc-editor\.org\/rfc\/rfc\d+\.html/.test(source.url), "Primary RFC source missing");
  assert(source.title && source.description, "Source needs scope");
});
M.scenarios.forEach(function (scenario) {
  var steps = M.getSteps(scenario.id), topology = M.getTopology(scenario.id), seen = [], previous = null;
  assert(steps.length >= 9, "Insufficient progression in " + scenario.id);
  checkFrozen(steps); checkFrozen(topology);
  assert(topology.width === 880 && topology.height === 270, "Unexpected drawing dimensions");
  assert(topology.nodes.length === 3 && topology.links.length === 2, "TCP path changed");
  var nodes = topology.nodes.map(function (node) {
    assert(node.x >= 0 && node.x <= topology.width && node.y >= 0 && node.y <= topology.height, "Off-canvas node");
    assert(node.y === 120, "TCP nodes should leave room for the byte diagram below");
    assert(node.title && node.address && node.kind, "Incomplete topology node");
    return node.id;
  });
  topology.links.forEach(function (link) { assert(nodes.indexOf(link.from) >= 0 && nodes.indexOf(link.to) >= 0, "Invalid link"); });
  steps.forEach(function (step, n) {
    assert(seen.indexOf(step.id) < 0, "Duplicate step " + step.id); seen.push(step.id);
    assert(phaseIds.indexOf(step.phase) >= 0, "Unknown phase " + step.phase);
    [step.title, step.summary, step.changed, step.visible, step.label].forEach(function (text) { assert(isText(text), "Unusable explanation " + step.id); });
    assert(step.paragraphs.length >= 2 && step.paragraphs.every(function (p) { return isText(p) && p.length >= 45; }), "Thin explanation " + step.id);
    assert(step.sourceIds.length && step.sourceIds.every(function (id) { return sourceIds.indexOf(id) >= 0; }), "Unknown source at " + step.id);
    assert(step.fields.length && step.fields.every(function (f) { return isText(f.layer) && isText(f.title) && f.items.length && f.items.every(function (row) { return row.length === 3 && row.every(isText); }); }), "Invalid inspector at " + step.id);
    assert(step.protocol === "local" || step.protocol === "tcp", "Unexpected protocol");
    assert(step.protocol === "local" ? step.from === null && step.to === null : nodes.indexOf(step.from) >= 0 && nodes.indexOf(step.to) >= 0 && step.from !== step.to, "Invalid direction at " + step.id);
    assert(!step.lost || scenario.id === "loss" && step.id === "middle-lost", "Spurious packet loss");
    var state = M.getState(scenario.id, n), m = state.metrics;
    checkFrozen(state);
    assert(json(state) === json(M.getState(scenario.id, n)), "Nondeterministic state");
    assert(state.facts.length >= 3 && state.facts.every(function (f) { return isText(f.label) && isText(f.value) && ["normal", "good", "warn", "bad"].indexOf(f.tone) >= 0; }), "Invalid facts");
    state.panels.forEach(function (panel) {
      assert(isText(panel.title), "Panel without title");
      if (panel.type === "ranges") {
        assert(panel.rows.length === 3, "Need sender, TCP receiver and application rows");
        panel.rows.forEach(function (row) {
          assert(isText(row.label) && row.segments.length === 3, "Bad range row");
          row.segments.forEach(function (segment) { assert(isText(segment.label) && statuses.indexOf(segment.status) >= 0, "Unknown range status"); });
        });
      } else if (panel.type === "table") {
        assert(panel.columns.every(isText) && panel.rows.every(function (row) { return row.length === panel.columns.length && row.every(isText); }), "Table shape mismatch");
      } else if (panel.type === "note") assert(isText(panel.text), "Empty note");
      else throw new Error("Unsupported panel " + panel.type);
    });
    var contiguous = 0;
    m.received.some(function (received) { if (!received) return true; contiguous += 4; return false; });
    assert(m.receiverNext === 1001 + contiguous + (m.clientFin ? 1 : 0), "ACK expectation crossed a gap " + step.id);
    assert(m.senderAck <= m.receiverNext, "Sender knows a future ACK");
    assert(m.senderAck <= m.senderNext, "ACK confirms unsent positions");
    assert(m.appText === "ABCDEFGHIJKL".slice(0, m.appText.length), "Application order corrupted");
    assert(m.appText.length <= contiguous && m.appText.length <= 12, "Application read across missing range");
    assert(m.reads.join("") === m.appText, "Read log inconsistent");
    assert(state.availableBytes === contiguous - m.appText.length, "Unread remainder must exclude consumed bytes and FIN");
    assert(state.availableBytes >= 0 && state.availableBytes <= 12, "Invalid unread remainder");
    if (previous) {
      assert(m.receiverNext >= previous.receiverNext && m.senderAck >= previous.senderAck, "Cumulative range regressed");
      assert(m.appText.length >= previous.appText.length, "Application data disappeared");
      if (step.lost) {
        assert(json(m.received) === json(previous.received) && m.receiverNext === previous.receiverNext && m.appText === previous.appText, "Lost data arrived");
      }
    }
    previous = m; count++;
  });
  assert(M.getState(scenario.id, -10) === M.getState(scenario.id, 0), "Negative index not clamped");
  assert(M.getState(scenario.id, NaN) === M.getState(scenario.id, 0), "NaN not clamped");
  assert(M.getState(scenario.id, 1.8) === M.getState(scenario.id, 1), "Fractional index not floored");
  assert(M.getState(scenario.id, 9999) === M.getState(scenario.id, steps.length - 1), "Large index not clamped");
  var last = M.getState(scenario.id, steps.length - 1).metrics;
  assert(last.appText === "ABCDEFGHIJKL" && Math.min(last.senderAck, 1013) === 1013, "File not delivered");
});
assert(M.getSteps("__proto__") === M.getSteps("ordered") && M.getSteps("missing") === M.getSteps("ordered"), "Unsafe scenario lookup");
assert(M.getState("__proto__", 0) === M.getState("ordered", 0), "State fallback mismatch");
assert(M.getSteps("loss").filter(function (s) { return s.lost; }).length === 1, "One actual loss required");
assert(!M.getSteps("reordered").some(function (s) { return s.lost; }), "Reordering depicted as loss");
assert(metrics("ordered", "ack-all").appText === "", "TCP ACK implied application read");
assert(at("ordered", "ack-all").availableBytes === 12, "All received bytes should be unread before application read");
assert(metrics("ordered", "read-three").appText === "ABC", "First chosen read wrong");
assert(at("ordered", "read-three").availableBytes === 9, "First read must consume three bytes from the available remainder");
assert(json(metrics("ordered", "read-nine").reads) === json(["ABC", "DEFGHIJKL"]), "Read boundaries accidentally mirror send boundaries");
assert(at("ordered", "read-nine").availableBytes === 0, "Consumed file cannot remain available for a second ordinary read");
at("ordered", "read-nine").panels[0].rows[1].segments.forEach(function (segment) {
  assert(segment.description === "Непрерывно принято TCP", "Receiver history must not promise that consumed bytes can still be read");
});
assert(metrics("reordered", "last-before-middle").receiverNext === 1005, "Out-of-order segment advanced ACK");
assert(json(metrics("reordered", "last-before-middle").received) === json([true, false, true]), "Out-of-order bytes not buffered");
assert(metrics("reordered", "duplicate-ack").senderAck === 1005, "Duplicate ACK became NACK or ACK1013");
assert(at("reordered", "last-before-middle").panels[0].rows[1].segments[2].status === "buffered", "Late range not distinguished");
assert(metrics("reordered", "delayed-middle-arrives").receiverNext === 1013, "Gap fill did not include stored tail");
assert(metrics("reordered", "delayed-middle-arrives").retransmissions === 0, "Delayed original called a retransmission");
assert(metrics("loss", "duplicate-ack").retransmissions === 0, "One duplicate ACK retransmits immediately");
assert(metrics("loss", "rto-expires").retransmissions === 0 && metrics("loss", "rto-expires").timer === "истёк", "Timeout not distinct from retransmission");
assert(metrics("loss", "retransmitted-middle").retransmissions === 1, "Retransmission count wrong");
assert(metrics("loss", "retransmitted-middle").receiverNext === 1013 && metrics("loss", "retransmitted-middle").senderNext === 1013, "Retransmission changed byte numbering");
assert(field(item("loss", "middle-lost"), "SEQ") === field(item("loss", "retransmitted-middle"), "SEQ"), "Retransmission uses new sequence number");
assert(field(item("close", "client-fin"), "SEQ") === "1013" && field(item("close", "ack-client-fin"), "ACK") === "1014", "Client FIN must consume one position");
assert(at("close", "client-fin").availableBytes === 0, "FIN must not add a readable data byte");
M.getSteps("close").slice(index("close", "client-fin")).forEach(function (step) {
  var closedState = at("close", step.id);
  var nextPosition = closedState.facts.find(function (fact) { return fact.label === "Следующая позиция TCP сервера"; });
  assert(nextPosition && nextPosition.value === "1014", "FIN advances the protocol position without promising new application data");
  assert(!closedState.facts.some(function (fact) { return /Сервер ждёт/.test(fact.label); }), "Closed client direction must not appear to wait for more application bytes");
  assert(closedState.availableBytes === 0, "Closed client stream has no unread file bytes in this scenario");
});
assert(metrics("close", "ack-client-fin").clientState === "FIN-WAIT-2" && metrics("close", "ack-client-fin").serverState === "CLOSE-WAIT", "Half-close states wrong");
assert(metrics("close", "server-reply").replyReceived === "OK\n" && metrics("close", "server-reply").replyRead === "", "Half-close prevented reception or implied read");
assert(field(item("close", "server-reply"), "Длина данных") === "3", "Escaped LF miscounted");
assert(metrics("close", "server-reply").serverNext === 9004 && metrics("close", "server-reply").clientReceiveNext === 9004, "Reply numbering wrong");
assert(field(item("close", "ack-reply"), "SEQ") === "1014" && field(item("close", "final-ack"), "SEQ") === "1014", "Pure ACK consumes sequence space");
assert(metrics("close", "client-reads-reply").replyRead === "OK\n", "Client never reads response");
assert(field(item("close", "server-fin"), "SEQ") === "9004" && field(item("close", "final-ack"), "ACK") === "9005", "Server FIN must consume one position");
assert(metrics("close", "final-ack").serverState === "CLOSED" && metrics("close", "final-ack").clientState === "TIME-WAIT", "Last ACK closes both sides too early");
assert(metrics("close", "time-wait-complete").clientState === "CLOSED", "TIME-WAIT never ends");
var original = M.getSteps("ordered")[0].title;
try { M.getSteps("ordered")[0].title = "changed"; } catch (_) {}
assert(M.getSteps("ordered")[0].title === original, "Caller modified shared lesson");
if (typeof print === "function") print("PASS: TCP lab — " + count + " snapshots; sequence/ACK, gaps, loss, reads and half-close checked.");
else console.log("PASS: TCP lab — " + count + " snapshots; sequence/ACK, gaps, loss, reads and half-close checked.");
