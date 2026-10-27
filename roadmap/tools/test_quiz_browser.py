#!/usr/bin/env python3
"""Browser regression; requires Google Chrome and Python websocket-client."""

def main():
    import argparse, functools, http.server, json, subprocess, tempfile, threading, time, urllib.request
    from pathlib import Path
    import websocket
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file-only',action='store_true',help='Run direct-file checks without traversing every HTTP quiz.')
    parser.add_argument('--station',help='Traverse this station (for example 9 or 9-sql); direct-file checks still cover all stations.')
    args=parser.parse_args()

    root=Path.cwd()
    station_numbers=sorted(p.stem.removeprefix("station") for p in (root/"roadmap/content").glob("station[0-9]*.json"))
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self,*args): pass
    server=http.server.ThreadingHTTPServer(("127.0.0.1",0),functools.partial(Quiet,directory=str(root)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    site=f"http://127.0.0.1:{server.server_port}"
    port=19345
    browser=None
    ws=None
    def pages():
        return json.load(urllib.request.urlopen(f"http://localhost:{port}/json",timeout=2))
    class CDP:
        def __init__(self,url):
            self.ws=websocket.create_connection(url,origin=f"http://localhost:{port}",timeout=20)
            self.serial=0
        def call(self,method,params=None):
            self.serial+=1
            self.ws.send(json.dumps({"id":self.serial,"method":method,"params":params or {}}))
            while True:
                message=json.loads(self.ws.recv())
                if message.get("id")==self.serial:
                    assert "error" not in message,message
                    return message.get("result",{})
        def evaluate(self,expression):
            result=self.call("Runtime.evaluate",{"expression":expression,"returnByValue":True,"userGesture":True})
            assert "exceptionDetails" not in result,result
            return result["result"].get("value")
        def click(self,selector,index=0):
            assert self.evaluate(f"(()=>{{const e=document.querySelectorAll({json.dumps(selector)})[{index}];if(!e)return false;e.click();return true;}})()"),(selector,index)
            time.sleep(.025)
        def width(self,width):
            self.call("Emulation.setDeviceMetricsOverride",{"width":width,"height":950,"deviceScaleFactor":1,"mobile":width==390})
            assert self.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"),(width,"overflow")
        def ready(self,path):
            for _ in range(250):
                if self.evaluate(f"Boolean(window.STATION_DATA && window.STATION_DATA.meta.sourceFile === {json.dumps(path)} && document.querySelector('.substation-card'))"):return
                time.sleep(.1)
            detail=self.evaluate("JSON.stringify({url:location.href,state:document.readyState,react:typeof React,reactDOM:typeof ReactDOM,data:typeof STATION_DATA,scripts:Array.from(document.scripts,s=>s.src),text:document.body?.innerText?.slice(0,400)})")
            raise AssertionError("page not ready: "+path+"; "+str(detail))
    try:
        with tempfile.TemporaryDirectory(prefix="roadmap-quiz-browser-") as profile:
            browser=subprocess.Popen(["/usr/bin/google-chrome","--headless","--no-sandbox","--disable-gpu",f"--remote-debugging-port={port}",f"--remote-allow-origins=http://localhost:{port}",f"--user-data-dir={profile}","about:blank"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            for _ in range(150):
                try:
                    page=next(p for p in pages() if p["type"]=="page" and p["url"]=="about:blank")
                    ws=CDP(page["webSocketDebuggerUrl"])
                    break
                except (OSError,StopIteration): time.sleep(.1)
            assert ws is not None
            ws.call("Page.enable")
            time.sleep(.7)
            checked=attempts=theory_count=links_opened=route_links_opened=task_count=task_links_opened=0
            selected = station_numbers if args.station is None else [args.station]
            assert all(n in station_numbers for n in selected), 'Unknown station'
            for n in ([] if args.file_only else selected):
                d=json.loads((root/f"roadmap/content/station{n}.json").read_text())
                path=d["meta"]["sourceFile"]
                ws.call("Page.navigate",{"url":site+"/roadmap/"+path})
                ws.ready(path)
                route=next(s for s in d['theory'] if s['id']=='learning-route')
                assert ws.evaluate("document.querySelector('article h2').textContent")==route['title']
                route_links=ws.evaluate("Array.from(document.querySelectorAll('article .learning-route-link'),e=>e.getAttribute('href'))")
                assert len(route_links)>=len(d['substations'])+1
                for route_index in (0,len(route_links)-1):
                    target_path,target_ref=route_links[route_index].split('#section=')
                    target_data=next(json.loads(p.read_text()) for p in (root/'roadmap/content').glob('station[0-9]*.json')
                                     if json.loads(p.read_text())['meta']['sourceFile']==target_path)
                    target=next(s for s in target_data['theory'] if s['id']==target_ref)
                    ws.click('article .learning-route-link',route_index)
                    for _ in range(200):
                        candidates=[p for p in pages() if p['type']=='page' and p['id']!=page['id'] and '#section=' in p['url']]
                        if candidates:break
                        time.sleep(.1)
                    else:raise AssertionError(('route link did not open',n,route_index))
                    other=CDP(candidates[0]['webSocketDebuggerUrl'])
                    try:
                        other.ready(target_path)
                        assert other.evaluate("document.querySelector('article h2').textContent")==target['title']
                        for width in (1440,390):other.width(width)
                    finally:
                        other.call('Page.close');other.ws.close()
                    assert ws.evaluate("document.querySelector('article h2').textContent")==route['title']
                    route_links_opened+=1
                if d.get('readingOrder'):
                    # Traverse the actual cross-module beginner path, not only links.
                    assert ws.evaluate("document.querySelector('.reading-mode').getAttribute('aria-pressed')")=='true'
                    by_id={s['id']:s for s in d['theory']}
                    for ri,section_id in enumerate(d['readingOrder']):
                        assert ws.evaluate("document.querySelector('article h2').textContent")==by_id[section_id]['title'],section_id
                        if ri:
                            ws.click('.route-previous')
                            assert ws.evaluate("document.querySelector('article h2').textContent")==by_id[d['readingOrder'][ri-1]]['title']
                            ws.click('.route-next')
                        for width in (1440,390):ws.width(width)
                        if ri+1<len(d['readingOrder']):ws.click('.route-next')
                    assert not ws.evaluate("Boolean(document.querySelector('.route-next'))")
                    ws.click('.substation-card',0)
                    ws.click('.reading-mode',1)
                    assert not ws.evaluate("Boolean(document.querySelector('.route-next'))")
                    assert ws.evaluate("Array.from(document.querySelectorAll('article button')).some(b=>b.textContent==='Следующий →')")
                    ws.click('.reading-mode',0)
                    print(f"station{n}: {len(d['readingOrder'])} route steps, backwards and thematic mode OK",flush=True)
                opened=False
                for mi,module in enumerate(d["substations"]):
                    ws.click(".substation-card",mi)
                    ws.click(".tabs .tab",0)
                    sections=[s for s in d["theory"] if s["substation"]==module["id"]]
                    for si,s in enumerate(sections):
                        ws.click(".section-nav .pill",si)
                        assert s["title"] in ws.evaluate("document.querySelector('article').innerText"),(n,s["id"])
                        assert ws.evaluate("Array.from(document.querySelectorAll('article pre code'), e=>e.textContent)")==[b["code"] for b in s["blocks"] if b["type"]=="code"],(n,s["id"],"code")
                        lane_blocks = [b for b in s["blocks"] if b["type"] == "lanes"]
                        for lane_index, block in enumerate(lane_blocks):
                            labels = ws.evaluate(f"document.querySelectorAll('.lanes-axis')[{lane_index}].innerText")
                            if block.get("mode") == "fields":
                                assert "канальное обрамление" in labels and "вложенные данные" in labels
                                assert "раньше" not in labels
                            else:
                                assert "раньше" in labels and "позже" in labels
                        for width in (1440,390): ws.width(width)
                        theory_count+=1
                    ws.click(".tabs .tab",1)
                    for kind,source in d["quizzes"].items():
                        questions=[q for q in source if q["substation"]==module["id"]]
                        ws.click(".quiz-choice."+kind)
                        for i,q in enumerate(questions):
                            assert not ws.evaluate("Boolean(document.querySelector('.quiz-theory-refs'))"),"reference before answer"
                            options=ws.evaluate("Array.from(document.querySelectorAll('.option-text'),e=>e.textContent)")
                            ws.click(".option",options.index(q["options"][q["answer"]]))
                            assert q["why"] in ws.evaluate("document.querySelector('.explanation').innerText"),(n,kind,i,"explanation")
                            expected=["#section="+ref for ref in q["theoryRefs"]]
                            actual=ws.evaluate("Array.from(document.querySelectorAll('.quiz-theory-refs a'),e=>e.getAttribute('href'))")
                            assert actual==expected,(n,kind,i,actual)
                            assert ws.evaluate("Array.from(document.querySelectorAll('.quiz-theory-refs a')).every(e=>e.target==='_blank' && e.rel.includes('noopener'))")
                            for width in (1440,390): ws.width(width)
                            if not opened:
                                before=ws.evaluate("document.querySelector('.counter').textContent+'|'+document.querySelector('.explanation').innerText")
                                ws.click(".quiz-theory-refs a")
                                for _ in range(200):
                                    candidates=[p for p in pages() if p["type"]=="page" and p["id"]!=page["id"] and "#section=" in p["url"]]
                                    if candidates: break
                                    time.sleep(.1)
                                else: raise AssertionError(("new tab did not open", pages()))
                                other=CDP(candidates[0]["webSocketDebuggerUrl"])
                                try:
                                    other.ready(path)
                                    target=next(s for s in d["theory"] if s["id"]==q["theoryRefs"][0])
                                    assert other.evaluate("document.querySelector('article h2').textContent")==target["title"]
                                    active=other.evaluate("document.querySelector('.substation-card.active .substation-number').textContent")
                                    assert active==next(m["label"] for m in d["substations"] if m["id"]==target["substation"])
                                    other.width(390)
                                finally:
                                    other.call("Page.close")
                                    other.ws.close()
                                assert ws.evaluate("document.querySelector('.counter').textContent+'|'+document.querySelector('.explanation').innerText")==before,"quiz attempt changed"
                                opened=True
                                links_opened+=1
                            ws.click(".explanation .primary")
                            checked+=1
                        assert "100%" in ws.evaluate("document.querySelector('.verdict').textContent"),(n,module["id"],kind)
                        assert "Раздел усвоен" not in ws.evaluate("document.querySelector('.verdict').textContent")
                        attempts+=1
                        ws.click(".quiz-back")
                    ws.click(".tabs .tab",2)
                    module_tasks=[t for t in d['tasks'] if t['substation']==module['id']]
                    for task_index,task in enumerate(module_tasks):
                        ws.click('.task-nav .pill',task_index)
                        assert ws.evaluate("document.querySelector('.task-title').textContent")==task['title']
                        module_order={m['id']:i for i,m in enumerate(d['substations'])}
                        later=any(module_order[s['substation']]>module_order[task['substation']]
                                  for s in d['theory'] if s['id'] in task['theoryRefs'])
                        assert ws.evaluate("Boolean(document.querySelector('.task-revisit'))")==later
                        assert not ws.evaluate("Boolean(document.querySelector('.task-solution-text,.solution-code'))")
                        shown_code=ws.evaluate("document.querySelector('.question-code code')?.textContent || null")
                        assert shown_code==task.get('code'),(n,task['title'],'input code')
                        ws.click('.task-preparation summary')
                        actual=ws.evaluate("Array.from(document.querySelectorAll('.task-preparation a'),e=>e.getAttribute('href'))")
                        assert actual==['#section='+ref for ref in task['theoryRefs']]
                        assert ws.evaluate("Array.from(document.querySelectorAll('.task-preparation a')).every(e=>e.target==='_blank' && e.rel.includes('noopener'))")
                        if task_index==0:
                            before=ws.evaluate("document.querySelector('.task-title').textContent")
                            ws.click('.task-preparation a')
                            for _ in range(200):
                                candidates=[p for p in pages() if p['type']=='page' and p['id']!=page['id'] and '#section=' in p['url']]
                                if candidates:break
                                time.sleep(.1)
                            else:raise AssertionError(('task link did not open',n,module['id']))
                            other=CDP(candidates[0]['webSocketDebuggerUrl'])
                            try:
                                other.ready(path)
                                target=next(s for s in d['theory'] if s['id']==task['theoryRefs'][0])
                                assert other.evaluate("document.querySelector('article h2').textContent")==target['title']
                            finally:
                                other.call('Page.close');other.ws.close()
                            assert ws.evaluate("document.querySelector('.task-title').textContent")==before
                            task_links_opened+=1
                        ws.click('.solution-button')
                        selector='.solution-code code' if task['solutionFormat']=='code' else '.task-solution-text'
                        answer=ws.evaluate(f"document.querySelector({json.dumps(selector)}).textContent")
                        assert ''.join(answer.split())==''.join(task['solution'].split()),(n,task['title'],'answer')
                        for width in (1440,390):ws.width(width)
                        task_count+=1
                print(f"station{n}: all questions, theory pages, links and mobile OK",flush=True)
            # Direct links must override saved substation selection.
            d=json.loads((root/"roadmap/content/station0.json").read_text())
            path=d["meta"]["sourceFile"]
            # A focused station-0 run is already on this document. Start a
            # fresh navigation, like opening the UI's target=_blank links;
            # a hash-only CDP navigation does not remount the React app.
            ws.call("Page.navigate",{"url":"about:blank"})
            for _ in range(100):
                if ws.evaluate("location.href === 'about:blank'"):break
                time.sleep(.02)
            assert ws.evaluate("location.href === 'about:blank'")
            ws.call("Page.navigate",{"url":site+"/roadmap/"+path+"#section=this"})
            ws.ready(path)
            assert ws.evaluate("document.querySelector('article h2').textContent")==next(s["title"] for s in d["theory"] if s["id"]=="this")
            ws.call("Page.navigate",{"url":site+"/roadmap/"+path+"#section=not-a-section"})
            ws.ready(path)
            assert ws.evaluate("Boolean(document.querySelector('article h2'))")
            # The textbook must still open directly from disk, without a server.
            # CDN-hosted React still requires network access (or browser cache).
            for n in station_numbers:
                d=json.loads((root/f"roadmap/content/station{n}.json").read_text())
                path=d["meta"]["sourceFile"]
                first=d["theory"][0]
                local=(root/"roadmap"/path).as_uri()+"#section="+first["id"]
                ws.call("Page.navigate",{"url":local})
                ws.ready(path)
                assert ws.evaluate("document.querySelector('article h2').textContent")==first["title"]
                ws.click(".tabs .tab",1)
                ws.click(".quiz-choice.advanced")
                assert ws.evaluate("document.querySelectorAll('.option').length") >= 2
                ws.click(".option",0)
                assert ws.evaluate("Boolean(document.querySelector('.explanation'))")
                ws.click('.tabs .tab',2)
                assert ws.evaluate("Boolean(document.querySelector('.task-preparation'))")
                ws.click('.solution-button')
                assert ws.evaluate("Boolean(document.querySelector('.task-solution-text,.solution-code'))")
                ws.width(390)
            print(f"file://: all {len(station_numbers)} stations, direct theory links and quiz answers OK",flush=True)
            print(f"PASS: {checked} questions, {attempts} complete attempts, {theory_count} theory pages, {links_opened} quiz links, {route_links_opened} route links in real new tabs",flush=True)
            print(f"PASS: {task_count} tasks; {task_links_opened} preparation links opened in real new tabs",flush=True)
            ws.ws.close();ws=None
            browser.terminate();browser.wait(timeout=15);browser=None
    finally:
        if ws is not None:ws.ws.close()
        if browser is not None:browser.terminate();browser.wait(timeout=15)
        server.shutdown()


if __name__ == "__main__":
    main()
