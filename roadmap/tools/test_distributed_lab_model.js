// Prepared-state regression, not a network/Raft/payment implementation test.
const read = path => imports.byteArray.toString(imports.gi.GLib.file_get_contents(path)[1]);
const assert = (value, message) => { if (!value) throw Error(message); };
// GJS has no URLSearchParams. This narrow adapter supports the route inputs below;
// the browser renderer itself uses the native web API.
class Params {
  constructor(text = "") {
    this.values = new Map();
    const decode = part => { try { return decodeURIComponent(part.replace(/\+/g, " ")); } catch (_) { return part; } };
    for (const piece of text.split("&").filter(Boolean)) {
      const [key, ...rest] = piece.split("=");
      const name = decode(key);
      if (!this.values.has(name)) this.values.set(name, decode(rest.join("=")));
    }
  }
  get(key) { return this.values.get(key) ?? null; }
}
const scope = {};
const source = read("roadmap/assets/distributed-lab-model.js");
new Function("window", "globalThis", "URLSearchParams", source)(undefined, scope, Params);
const model = scope.CourseDistributedLab;
const ids = ["lost-reply", "stale-read", "workflow-recovery"];
assert(JSON.stringify(model.scenarios.map(s => s.id)) === JSON.stringify(ids), "Stable scenario ids");
assert(JSON.stringify(model.scenarios.map(s => s.steps.length)) === "[11,11,13]", "Prepared step counts");
let checked = 0;
for (const scenario of model.scenarios) {
  assert(Object.isFrozen(scenario) && Object.isFrozen(scenario.steps), "Immutable authored scenario");
  assert(scenario.intro.length >= 2 && scenario.assumptions.length >= 3, "Situation and explicit assumptions");
  const stepIds = new Set();
  for (let i = 0; i < scenario.steps.length; i++) {
    const step = model.snapshot(scenario.id, i), before = JSON.stringify(scenario.steps[i]);
    assert(!stepIds.has(step.id), "Unique stable step id");stepIds.add(step.id);
    for (const key of ["title", "event", "why", "rule", "question", "answer"]) {
      assert(typeof step[key] === "string" && step[key].trim().length > 20, "Explained event: " + key);
    }
    assert(Object.isFrozen(scenario.steps[i].state), "Immutable authored state");
    step.title = "mutated private clone";
    assert(JSON.stringify(scenario.steps[i]) === before, "snapshot mutation isolated");
    const state = step.state;
    if (state.type === "raft") {
      assert(state.nodes.length === 3, "Fixed replica group");
      for (const node of state.nodes) {
        assert(node.applied <= node.commit && node.commit <= node.log.at(-1).index, "applied <= known commit <= persisted");
        assert(node.log[0].index === 7, "Explicit prepared prefix");
        let expected = 0;
        for (let j = 0; j < node.log.length; j++) {
          const entry = node.log[j];
          if (j) {
            assert(entry.index === node.log[j - 1].index + 1, "No holes in shown tail");
            assert(entry.term >= node.log[j - 1].term, "Nondecreasing log terms");
          }
          if (entry.index <= node.applied) {
            const match = entry.command.match(/set\((\d+)\)/);
            if (match) expected = Number(match[1]);
          }
        }
        assert(node.value === expected, "Value matches the applied prefix");
      }
    } else {
      const p = state.provider;
      assert(p.payments <= 1 && p.refunds <= 1 && p.refunds <= p.payments, "At most one effect per intent in the contract");
      assert(p.balance === 2500 * (p.payments - p.refunds), "Prepared money arithmetic");
      if (state.orders.state === "cancelled_refunded") {
        assert(p.refunds === 1 && state.orders.knownRefund.includes("успех"), "Known final refund");
      }
    }
    for (const operation of state.history) {
      assert(operation.start <= i, "No future operation start");
      assert(operation.finish === null || operation.start <= operation.finish && operation.finish <= i, "No future completion");
    }
    checked++;
  }
}
const lost = model.scenarios[0].steps;
const replica = (step, id) => step.state.nodes.find(n => n.id === id);
assert(replica(lost[3],"B").log.at(-1).index === 8 && replica(lost[3],"A").commit === 7, "Fact before ACK knowledge");
assert(replica(lost[4],"A").commit === 8 && replica(lost[4],"A").applied === 7, "Commit before apply");
assert(replica(lost[5],"A").value === 1 && lost[5].state.history[0].finish === null, "Apply before client knows");
assert(replica(lost[8],"A").value === 1 && lost[8].state.history[0].result.includes("неизвестный"), "Timeout does not undo effect");
assert(lost[9].state.nodes.every(n => n.log.at(-1).index <= 8), "Retry adds no second user intent");
assert(lost.at(-1).state.nodes.every(n => n.value === 1), "Final catch-up state");
const stale = model.scenarios[1].steps;
assert(replica(stale[2],"A").term === 4 && replica(stale[2],"B").term === 5, "Old belief vs new term");
assert(replica(stale[5],"B").commit === 9 && replica(stale[5],"B").log.at(-1).term === 5, "Current-term no-op committed");
assert(replica(stale[7],"C").commit === 9 && replica(stale[7],"C").applied === 9, "Follower learns prior commit on new append");
assert(replica(stale[8],"B").value === 2 && replica(stale[8],"A").value === 1, "Stale local copy remains");
assert(stale[9].state.history[0].finish < stale[9].state.history[1].start, "Write response before read invocation");
assert(stale[9].state.result.local.value.includes("Нарушение") && stale[9].state.result.barrier.value.includes("Нет"), "Explicit alternative read contracts");
const flow = model.scenarios[2].steps;
assert(flow[3].state.provider.payments === 1 && flow[3].state.orders.state === "pay_pending", "External effect before local receipt");
assert(flow[4].state.orders.running === false && flow[4].state.provider.balance === 2500, "Restart does not refund");
assert(flow[5].state.warehouse.reserve.includes("истёк") && flow[5].state.orders.knownReserve.includes("активен"), "External fact vs old local observation");
assert(flow[9].state.provider.refunds === 1 && flow[9].state.orders.knownRefund.includes("неизвестен"), "Refund effect before knowledge");
assert(flow[10].state.orders.state === "manual_review", "Unknown refund escalates, not fake success");
assert(flow[11].state.orders.state === "cancelled_refunded", "Final known outcome");
assert(JSON.stringify(flow[11].state.provider) === JSON.stringify(flow[12].state.provider), "Repeated notification creates no effect");
for (const [hash,expected] of [
  ["", {scenario:"lost-reply",step:0}],
  ["#scenario=stale-read&step=9", {scenario:"stale-read",step:9}],
  ["#scenario=workflow-recovery&step=999", {scenario:"workflow-recovery",step:12}],
  ["#scenario=unknown&step=8", {scenario:"lost-reply",step:0}],
  ["#scenario=%ZZ&step=Infinity", {scenario:"lost-reply",step:0}],
  ["#scenario=stale-read&step=-1", {scenario:"stale-read",step:0}],
  ["#scenario=stale-read&step=1.5", {scenario:"stale-read",step:0}],
  ["#scenario=stale-read&step=9007199254740999", {scenario:"stale-read",step:0}]
]) assert(JSON.stringify(model.route(hash)) === JSON.stringify(expected), "Route: " + hash);
for(const args of [["missing",0],["lost-reply",-1],["lost-reply",100],["lost-reply",1.5]]) {
  let rejected=false;try{model.snapshot(...args);}catch(_){rejected=true;}assert(rejected,"Invalid snapshot refused");
}
assert(!/\bfetch\s*\(|XMLHttpRequest|WebSocket|setInterval|setTimeout/.test(source), "No network or autoplay in the model");
print("PASS: " + checked + " prepared snapshots, state invariants, exact loss/read/recovery boundaries, immutable copies and route validation. No live cluster or browser.");
