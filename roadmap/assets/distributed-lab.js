/* Standalone renderer for immutable, prepared teaching snapshots. */
(function (window, document) {
  "use strict";
  const model = window.CourseDistributedLab;
  if (!model) throw new Error("Prepared distributed model is unavailable");
  const el = id => {
    const node = document.getElementById(id);
    if (!node) throw new Error("Missing laboratory element: " + id);
    return node;
  };
  const make = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = String(text);
    if (cls) node.className = cls;
    return node;
  };
  const clear = node => node.replaceChildren();
  const say = (id, value) => { el(id).textContent = value; };
  let current = null;
  let scenarioButtons = [];
  const stateLabels = {
    created:"заказ создан", reserved:"резерв известен",
    pay_pending:"оплата проверяется", cancelling:"принят путь отмены",
    refund_pending:"возврат проверяется", manual_review:"назначена ручная сверка",
    cancelled_refunded:"отмена и возврат подтверждены"
  };

  function factsList(items, cls) {
    const list = make("dl", undefined, cls);
    for (const [name, value] of items) {
      list.append(make("dt", name), make("dd", value));
    }
    return list;
  }
  function scrollTable(table, label) {
    const wrap = make("div", undefined, "table-scroll");
    wrap.setAttribute("tabindex", "0");
    wrap.setAttribute("role", "region");
    wrap.setAttribute("aria-label", label);
    wrap.append(table);
    return wrap;
  }
  function tableHead(names) {
    const head = make("thead"), row = make("tr");
    for (const name of names) {
      const th = make("th", name); th.setAttribute("scope", "col"); row.append(th);
    }
    head.append(row);
    return head;
  }
  function participantHeader(card, name, affected) {
    const header = make("div", undefined, "participant-header");
    header.append(make("h4", name));
    if (affected) header.append(make("span", "участник события", "affected-label"));
    card.append(header);
  }
  function replicaCard(node, affected) {
    const card = make("section", undefined, "participant" + (affected ? " is-affected" : ""));
    card.setAttribute("aria-label", "Реплика " + node.id);
    participantHeader(card, "Реплика " + node.id, affected);
    card.append(make("p", node.role + " · term " + node.term +
      (node.connected ? "" : " · изолирован"), "node-role" + (node.connected ? "" : " isolated-label")));
    const facts = factsList([
      ["Сохранено до", node.log[node.log.length - 1].index],
      ["Commit известен до", node.commit],
      ["Применено до", node.applied], ["Значение x", node.value]
    ], "node-facts");
    facts.lastElementChild.className = "value";
    card.append(facts);
    const table = make("table");
    table.append(tableHead(["Индекс", "Term", "Команда"]));
    const body = make("tbody");
    for (const entry of node.log) {
      const row = make("tr"), command = make("td", undefined, "log-command");
      command.append(make("span", entry.command));
      const applied = entry.index <= node.applied, committed = entry.index <= node.commit;
      command.append(make("span", applied ? "применено" : committed ? "commit известен" : "сохранено",
        "log-state" + (applied ? " is-applied" : committed ? " is-committed" : "")));
      row.append(make("td", entry.index), make("td", entry.term), command);body.append(row);
    }
    table.append(body);card.append(scrollTable(table, "Конец журнала реплики " + node.id));
    card.append(make("p", "Квитанции: " + (node.receipts.length ? node.receipts.join("; ") : "в этом снимке не показаны"), "node-receipt"));
    return card;
  }
  function workflowCard(id, title, values, affected) {
    const card = make("section", undefined, "participant" + (affected ? " is-affected" : ""));
    card.setAttribute("aria-label", title);
    participantHeader(card, title, affected);
    card.append(factsList(values, "workflow-facts"));
    return card;
  }
  function renderParticipants(step) {
    const box = el("participants");clear(box);
    const state = step.state;
    if (state.type === "raft") {
      box.className = "participants";
      say("state-kind", "Фиксированная группа A / B / C");
      say("state-guide", "Показан конец журнала начиная с индекса 7. Term — номер раунда полномочий Raft. «Сохранено» означает запись в устойчивом журнале; commit — известную принятую границу; «применено» — исполненную команду. Эти числа могут различаться.");
      state.nodes.forEach(node => box.append(replicaCard(node, step.focus.includes(node.id))));
    } else {
      box.className = "participants workflow-participants";
      say("state-kind", "Разные участники, разные данные");
      say("state-guide", "Все панели видны читателю. Но программа заказов не знает автоматически чужих фактов: ей нужны подтверждённые ответы или сверка. Числа — условия модели, не реальные деньги.");
      const o=state.orders, p=state.provider;
      box.append(workflowCard("orders", "Заказы", [
        ["Программа", o.running ? "работает" : "остановлена"],
        ["Сохранённый шаг", (stateLabels[o.state] || o.state) + " (" + o.state + ")"],
        ["Намерение оплаты", o.paymentKey], ["Знание об оплате", o.knownPayment],
        ["Знание о резерве", o.knownReserve], ["Намерение возврата", o.refundKey],
        ["Знание о возврате", o.knownRefund]
      ],step.focus.includes("orders")));
      box.append(workflowCard("warehouse", "Склад", [
        ["Резерв", state.warehouse.reserve], ["За каким заказом", state.warehouse.owner]
      ],step.focus.includes("warehouse")));
      box.append(workflowCard("provider", "Провайдер", [
        ["Число списаний", p.payments], ["Списание", p.payment],
        ["Число возвратов", p.refunds], ["Возврат", p.refund],
        ["Списано минус возвращено", p.balance]
      ],step.focus.includes("provider")));
    }
  }
  function renderDelivery(state) {
    const box = el("delivery");clear(box);
    if (!state.messages.length) {
      box.append(make("p", "В этом событии нет показанной доставки. Это не доказательство отсутствия любых пакетов в реальной сети.", "empty-evidence"));
      return;
    }
    const list = make("ul", undefined, "delivery-list");
    for (const message of state.messages) {
      const row = make("li");
      row.append(make("span", message.from + " → " + message.to, "delivery-route"),
        make("span", message.content, "delivery-content"),
        make("span", message.status, "delivery-status" +
          (["потеряно", "не доставляется"].includes(message.status) ? " is-lost" : "")));
      list.append(row);
    }
    box.append(list);
  }
  function renderHistory(state) {
    const box=el("operation-history");clear(box);
    if (!state.history.length) {
      box.append(make("p", "Вызовов клиента в этой части истории ещё нет.", "empty-evidence"));return;
    }
    const table=make("table");table.append(tableHead(["Операция","Начало","Известный конец","Результат"]));
    const body=make("tbody");
    for(const op of state.history) {
      const row=make("tr");
      row.append(make("td",op.operation),make("td","шаг "+(op.start+1)),
        make("td",op.finish===null?"ещё не получен":"шаг "+(op.finish+1)),make("td",op.result));
      body.append(row);
    }
    table.append(body);box.append(scrollTable(table,"История операций этой модели"));
    box.append(make("p","Номера относятся к шагам выбранной истории, а не к календарному времени. Неизвестный исход не исчезает из истории.", "reading-note"));
  }
  function renderAlternatives(state) {
    const area=el("read-comparison"),box=el("read-alternatives");clear(box);
    area.hidden=!state.result;
    if(!state.result)return;
    for(const [key,option] of Object.entries(state.result)) {
      const row=make("div",undefined,"read-alternative "+(key==="local"?"is-unsafe":"is-safe"));
      row.append(make("h4",option.label),make("p",option.value,"alternative-verdict"),make("p",option.why));
      box.append(row);
    }
  }
  function renderIntroduction(scenario) {
    say("scenario-title",scenario.title);
    const context=el("scenario-context");clear(context);
    scenario.intro.forEach(p=>context.append(make("p",p)));
    const assumptions=el("scenario-assumptions");clear(assumptions);
    scenario.assumptions.forEach(p=>assumptions.append(make("li",p)));
    el("theory-link").setAttribute("href",scenario.theory);
  }
  function renderRail(scenario,index) {
    const rail=el("step-list");clear(rail);
    scenario.steps.forEach((step,i)=>{
      const item=make("li"),button=make("button",undefined,"step-link");
      button.type="button";
      button.setAttribute("id","event-step-"+i);
      button.setAttribute("aria-label","Шаг "+(i+1)+": "+step.title);
      if(i===index)button.setAttribute("aria-current","step");
      button.append(make("span",i+1,"step-index"),make("span",step.title));
      button.addEventListener("click",()=>navigate(scenario.id,i,"event-title"));
      item.append(button);rail.append(item);
    });
  }
  function render(route,focusId) {
    const scenario=model.scenarios.find(s=>s.id===route.scenario);
    const step=model.snapshot(route.scenario,route.step);
    const changedScenario=!current||current.scenario!==route.scenario;
    current={...route};
    scenarioButtons.forEach(button=>button.setAttribute("aria-pressed",String(button.id==="scenario-"+scenario.id)));
    if(changedScenario)renderIntroduction(scenario);
    renderRail(scenario,route.step);
    say("step-count","Шаг "+(route.step+1)+" из "+scenario.steps.length);
    say("event-title",step.title);say("event-description",step.event);
    say("event-why",step.why);say("event-rule",step.rule);
    say("prediction-question",step.question+" Открыть проверку");
    say("prediction-answer",step.answer);el("prediction-check").open=false;
    renderParticipants(step);renderDelivery(step.state);renderHistory(step.state);renderAlternatives(step.state);
    say("client-knowledge",step.state.client);
    el("first-step").disabled=route.step===0;el("previous-step").disabled=route.step===0;
    el("next-step").disabled=route.step===scenario.steps.length-1;
    say("next-step",route.step===scenario.steps.length-1?"История завершена":"Следующий шаг");
    say("lab-announcement",scenario.title+". Шаг "+(route.step+1)+" из "+scenario.steps.length+". "+step.title);
    if(focusId)el(focusId).focus();
  }
  function canonical(route) {
    return "#scenario="+route.scenario+"&step="+route.step;
  }
  function navigate(scenario,step,focusId) {
    const route=model.route("#scenario="+scenario+"&step="+step);
    if(window.location.hash!==canonical(route))window.history.pushState(null,"",canonical(route));
    render(route,focusId);
  }
  function sync() {
    const route=model.route(window.location.hash);
    if(current&&current.scenario===route.scenario&&current.step===route.step)return;
    render(route);
  }
  const choices=el("scenario-navigation");
  model.scenarios.forEach(scenario=>{
    const button=make("button",undefined,"scenario-choice");button.id="scenario-"+scenario.id;button.type="button";
    button.append(make("span",scenario.title),make("span",scenario.short,"scenario-short"));
    button.addEventListener("click",()=>navigate(scenario.id,0,"scenario-title"));
    scenarioButtons.push(button);choices.append(button);
  });
  el("first-step").addEventListener("click",()=>navigate(current.scenario,0,"event-title"));
  el("previous-step").addEventListener("click",()=>navigate(current.scenario,current.step-1,"event-title"));
  el("next-step").addEventListener("click",()=>navigate(current.scenario,current.step+1,"event-title"));
  window.addEventListener("hashchange",sync);
  window.addEventListener("popstate",sync);
  document.addEventListener("keydown",event=>{
    if(event.altKey||event.ctrlKey||event.metaKey||event.shiftKey||event.defaultPrevented)return;
    if(event.target&&event.target.closest&&event.target.closest('input,textarea,select,[contenteditable],[role="region"]'))return;
    if(event.key!=="ArrowLeft"&&event.key!=="ArrowRight")return;
    const scenario=model.scenarios.find(s=>s.id===current.scenario);
    const next=current.step+(event.key==="ArrowLeft"?-1:1);
    if(next<0||next>=scenario.steps.length)return;
    event.preventDefault();navigate(current.scenario,next,"event-title");
  });
  const initial=model.route(window.location.hash);
  if(window.location.hash!==canonical(initial))window.history.replaceState(null,"",canonical(initial));
  render(initial);
})(window,document);
