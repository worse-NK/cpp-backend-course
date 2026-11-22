#!/usr/bin/env python3
"""Offline browser acceptance of the 25 inline explanations (Chrome with its sandbox).

  /usr/bin/python3 desktop-course/tests/test_reading_scenes_browser.py \
    --roadmap build/local/roadmap --screenshots build/reading-scenes-qa
"""
import base64
import json

from cdp import ROOT
from test_lab_interactions_browser import enter, main


EXPECTED = {
    "why-oop", "struct-to-class", "constructor", "special-members-intro", "smart-ptr",
    "smart-ptr-deep", "slicing", "iterators", "exception-safety", "ipc-pipes-shared-memory",
    "linux-fd-open-description", "spsc-ring-model", "level-edge-triggered",
    "netlab-bridge-learning", "traffic-wireshark-three-panes", "conditional-update",
    "sql-window-frame", "cache-race", "request-budget-architecture", "kafka-parallel-frontier",
    "eviction-and-expiry", "service-and-endpoints", "histogram-buckets",
    "identity-revocation-timeline", "raft-log-commit",
}
STORIES = {"smart-ptr", "smart-ptr-deep", "ipc-pipes-shared-memory", "spsc-ring-model",
           "conditional-update", "cache-race", "kafka-parallel-frontier"}
SAMPLES = {"why-oop", "smart-ptr", "smart-ptr-deep", "spsc-ring-model", "iterators",
           "request-budget-architecture", "sql-window-frame"}
TICK = "new Promise(done=>requestAnimationFrame(()=>requestAnimationFrame(()=>done(true))))"


def catalog():
    records = []
    for path in sorted((ROOT.parent / "roadmap/content").glob("station*.json")):
        data = json.loads(path.read_text())
        for sec in data["theory"]:
            for b in sec["blocks"]:
                if b["type"] == "reading-scene":
                    assert sec["id"] == b["id"], (path, b)
                    records.append((data["meta"]["sourceFile"], b))
    assert len(records) == 25 and {b["id"] for _, b in records} == EXPECTED
    assert {b["id"] for _, b in records if b["mode"] == "scroll"} == STORIES
    return records


def screenshot(page, name, output):
    if output:
        data = page.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        (output / (name + ".png")).write_bytes(base64.b64decode(data["data"]))


def stage_positions(page):
    # Scan the real page without invoking component handlers, then revisit positions in
    # reverse order. Capture viewpoints with text AND a full board when the board pins.
    return page.js("""(async()=>{
      const root=document.querySelector('.reading-scene'), track=root.querySelector('.rs-track'),
        stage=track.querySelector('.rs-stage'), beats=[...track.querySelectorAll('.rs-beats>li')];
      const settle=()=>new Promise(ok=>requestAnimationFrame(()=>requestAnimationFrame(ok)));
      const go=async y=>{scrollTo({top:y,behavior:'instant'});await settle()};
      const r=track.getBoundingClientRect(), from=Math.max(0,scrollY+r.top-innerHeight*.66),
        to=scrollY+r.bottom-innerHeight*.13;
      const positions=[], forward=[], back=[], choices={};
      for(let y=from;y<to;y+=68)positions.push(y);
      positions.push(to);
      const record=sequence=>{
        const i=beats.findIndex(el=>el.matches('[aria-current="step"]')); if(i<0)return;
        if(i!==sequence.at(-1))sequence.push(i);
        const flat=track.classList.contains('rs-unpinned'),
          title=beats[i].querySelector('h4').getBoundingClientRect(), box=stage.getBoundingClientRect(),
          stacked=title.left<box.right && title.right>box.left;
        if(!flat && (box.top<-.5 || box.bottom>innerHeight+1 || (stacked && title.top<box.bottom)))return;
        if(title.top<0 || title.bottom>innerHeight+1)return;
        const aim=(!flat&&stacked?(box.bottom+innerHeight)/2:innerHeight*.35),
          score=Math.abs(title.top-aim);
        if(!(i in choices)||choices[i].score>score)choices[i]={y:scrollY,score};
      };
      for(const y of positions){await go(y);record(forward)}
      for(const y of positions.reverse()){await go(y);record(back)}
      return {choices,forward,back,flat:track.classList.contains('rs-unpinned')};})()""")


def board(page, selector):
    return page.js("""(selector=>{
      const root=document.querySelector(selector),cells=[...root.querySelectorAll('.rs-cell')];
      const actualArcs=[...root.querySelectorAll('.rs-arcs g')].map(g=>{
        const p=g.querySelector('path'),matrix=p.getScreenCTM();
        const at=t=>p.getPointAtLength(t).matrixTransform(matrix);
        function owner(point){
          const distances=cells.map(el=>{
            const r=el.getBoundingClientRect();
            return Math.hypot(Math.max(0,r.left-point.x,point.x-r.right),
                              Math.max(0,r.top-point.y,point.y-r.bottom));
          });
          const nearest=Math.min(...distances);
          return nearest<18 ? distances.indexOf(nearest) : -1;
        }
        if(getComputedStyle(p).stroke==='none'||p.getTotalLength()<2)return ['invisible'];
        const edge=[owner(at(0)),owner(at(p.getTotalLength()))];
        if(getComputedStyle(p).strokeDasharray!=='none')edge.push('weak');
        return edge;
      });
      return {
        visible:getComputedStyle(root).visibility==='visible' && !!root.getClientRects().length,
        values:cells.map(el=>el.querySelector('dd').textContent),
        columns:cells.map(el=>el.querySelector('dt').textContent),
        focus:cells.flatMap((el,i)=>el.classList.contains('rs-focus')?[i]:[]),
        label:root.querySelector('.rs-snap-head b').textContent,
        output:root.querySelector('.rs-console samp')?.textContent??null,
        code:root.querySelector('.rs-code')?.textContent??'', edges:actualArcs};
    })(""" + json.dumps(selector) + ")")


def check_board(page, b, i, selector):
    f, got = b["frames"][i], board(page, selector)
    assert got == dict(visible=True, values=f["values"], columns=b["columns"], focus=sorted(f.get("focus", [])),
                       label=f["label"], code=f.get("code", ""), output=f.get("output"),
                       edges=f.get("edges", [])), (b["id"], i, got, f)


def print_check(page, b):
    page.call("Emulation.setEmulatedMedia", {"media": "print"})
    if b["mode"] in {"trace", "scroll"}:
        visible = page.js("""(() => {
          const r=document.querySelector('.reading-scene'), panel=r.querySelector('.rs-stage,.rs-explorer');
          return {boardHidden:!panel.getClientRects().length, frames:[...r.querySelectorAll('.rs-beats li')]
            .filter(el=>el.getClientRects().length && el.querySelector('div').getBoundingClientRect().height>2)
            .map(el=>el.innerText)};})()""")
        assert visible["boardHidden"] and len(visible["frames"]) == len(b["frames"]), (b["id"], visible)
        for text, f in zip(visible["frames"], b["frames"], strict=True):
            assert f["label"] in text and f["note"] in text and all(v in text for v in f["values"]), (b["id"], text)
            if f.get("output"):
                assert f["output"] in text, (b["id"], text, f["output"])
    else:
        assert page.js("document.querySelector('.reading-scene').getBoundingClientRect().height>20")
    page.call("Emulation.setEmulatedMedia", {"media": "screen"})


def check_static(page, b):
    for i, f in enumerate(b["frames"]):
        if b["mode"] == "compare":
            check_board(page, b, i, f".rs-case:nth-child({i+1}) .rs-snapshot")
        elif b["mode"] == "table":
            cells = page.js(f"""(()=>{{const row=document.querySelectorAll('.rs-matrix tbody tr:not(.rs-explain-row)')[{i}];
                return [...row.querySelectorAll('td')].map(c=>[c.lastChild.textContent,c.classList.contains('rs-focus')])}})()""")
            assert cells == [[v, j in f.get("focus", [])] for j,v in enumerate(f["values"])], (b["id"], cells)
        else:
            values = page.js(f"[...document.querySelectorAll('.rs-timelist li:nth-child({i+1}) dd')].map(n=>n.textContent)")
            assert values == f["values"], (b["id"], values)
            if "span" in f:
                rect = page.js(f"document.querySelector('.rs-timelist li:nth-child({i+1}) rect:last-child').getBBox().width")
                span, axis = f["span"], b["axis"]
                assert abs(rect-300*(span[1]-span[0])/(axis["max"]-axis["min"])) < .2, (b["id"], rect)


def short_screen(page, roadmap):
    # A pinned chart would hide the entire explanation in a short landscape
    # window. Every state must still be readable in the ordinary page flow.
    filename,b = next(entry for entry in catalog() if entry[1]["id"]=="smart-ptr-deep")
    page.viewport(520,375)
    page.goto((roadmap/filename).as_uri()+"?scene=smart-ptr-deep#section=smart-ptr-deep",
              "!!document.querySelector('.rs-track.rs-unpinned')")
    details = page.js("""[...document.querySelectorAll('.rs-beat-detail')].map(el=>({
        clip:getComputedStyle(el).clipPath,position:getComputedStyle(el).position,text:el.innerText,
        height:el.getBoundingClientRect().height}))""")
    assert len(details)==len(b["frames"]), details
    for f,d in zip(b["frames"],details,strict=True):
        assert d["clip"]=="none" and d["position"]=="static" and d["height"]>10, d
        assert all(v in d["text"] for v in f["values"]), (f,d)
        if f.get("output"):
            assert f["output"] in d["text"], (f,d)
    print("520×375: all six shared/weak states readable without a sticky overlay",flush=True)


def run(page, roadmap, width, output):
    page.viewport(width, 800)
    page.call("Network.emulateNetworkConditions", {"offline": True, "latency": 0,
              "downloadThroughput": 0, "uploadThroughput": 0})
    for filename, b in catalog():
        sid, mode, frames = b["id"], b["mode"], b["frames"]
        page.call("Emulation.setEmulatedMedia", {"media":"screen", "features":[
            {"name":"prefers-reduced-motion", "value":"reduce" if width==375 else "no-preference"}]})
        page.goto((roadmap / filename).as_uri() + "?scene=" + sid + "#section=" + sid,
                  f"document.querySelectorAll('.reading-scene[data-scene=\"{sid}\"]').length===1")
        page.js(TICK)
        assert page.js("document.querySelector('.reading-scene figcaption').textContent") == b["title"]
        assert page.js("""(()=>{const el=document.querySelector('.reading-scene'),r=el.getBoundingClientRect();
          return r.left>=-1 && r.right<=innerWidth+1 && el.scrollWidth<=el.clientWidth+2
                 && document.documentElement.scrollWidth<=innerWidth+1;})()"""), (width, sid, "horizontal overflow")
        active = ".rs-layer[data-shown=yes] .rs-snapshot"
        if mode == "scroll":
            n=len(frames)
            t=stage_positions(page)
            if t["flat"]: print(f"{width}: {sid}: page uses non-sticky transcript",flush=True)
            assert t["forward"]==list(range(n)) and t["back"]==list(reversed(range(n))), (width,sid,t)
            assert len(t["choices"])==n, ("no joint viewpoint",width,sid,t)
            first_resource = None
            for i in range(n):
                y=t["choices"][str(i)]["y"]
                page.js(f"scrollTo({{top:{y}, behavior:'instant'}});{TICK}")
                check_board(page,b,i,active)
                if sid in {"smart-ptr","smart-ptr-deep"}:
                    position=page.js("""(()=>{const root=document.querySelector('.rs-stage'),
                      r=root.querySelector('.rs-layer[data-shown=yes] .rs-resource').getBoundingClientRect(),
                      s=root.getBoundingClientRect();return [r.left-s.left,r.top-s.top,r.width,r.height]})()""")
                    if first_resource is None: first_resource=position
                    # Its anchor and width stay fixed; the final "no longer exists"
                    # label can legitimately wrap once the object is gone.
                    dims=4 if frames[i]["values"][-1]==frames[0]["values"][-1] else 3
                    assert all(abs(a-c)<1.1 for a,c in zip(first_resource[:dims],position[:dims])), (width,sid,i,first_resource,position)
                if output and sid in SAMPLES and i==min(2,n-1):
                    screenshot(page,f"{sid}-{width}",output)
            enter(page,".rs-guide button")
            page.wait("document.activeElement.matches('.rs-after')")
        elif mode == "trace":
            last=len(frames)-1
            assert page.js("document.querySelector('.rs-controls button').disabled")
            for i in list(range(last+1))+list(reversed(range(last))):
                if i != 0 or page.js("!document.querySelector('.rs-controls button').disabled"):
                    current=int(page.js("document.querySelector('.rs-controls span').textContent.split('/')[0].trim()"))-1
                    enter(page,".rs-controls button:" + ("last-child" if i>current else "first-child"))
                    page.wait(f"document.querySelector('.rs-controls span').textContent.trim().startsWith('{i+1} /')")
                check_board(page,b,i,active)
                if i==last:
                    assert page.js("document.querySelector('.rs-controls button:last-child').disabled")
                    if output and sid in SAMPLES: screenshot(page,f"{sid}-{width}",output)
        else:
            check_static(page,b)
            if output and sid in SAMPLES: screenshot(page,f"{sid}-{width}",output)
        assert page.js("location.hash")=="#section="+sid, sid
        print_check(page,b)
        print(f"{width}: {sid} ({mode}, {len(frames)} frames)",flush=True)
    if width==320:
        short_screen(page,roadmap)


if __name__ == "__main__":
    main(run,"PASS: 25 reading scenes offline, responsive states, print and keyboard",widths=(1280,375,320))
