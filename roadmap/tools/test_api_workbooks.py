#!/usr/bin/env python3
"""Station 8 closing workbooks: models, actual C++ and real browser SSE.

The SSE check uses loopback only, an isolated Chrome profile and the stream from
the chapter. It does not implement the textbook's application recovery protocol.
"""
import http.server
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request

from test_expanded_examples import code, station
import test_remaining_examples


class ApiClosingWorkbooks(unittest.TestCase):
    cpp = test_remaining_examples.RemainingExamples.cpp

    def test_final_state_on_chapter_cpp_service(self):
        source = code(8, "atomic-service").split("int main()", 1)[0]
        self.cpp(source + r'''
int main() {
    OneTask store;
    auto initial=store.read();
    if(store.replace(initial.version,"B",false)!=Update::applied) return 1;
    auto y=store.read();
    if(store.replace(y.version,y.title,true)!=Update::applied) return 2;
    if(store.replace(initial.version,"B",false)!=Update::stale) return 3;
    try {store.replace(9,"",false); return 4;}
    catch(const std::invalid_argument&) {}
    auto end=store.read();
    std::cout << end.title << ' ' << end.done << ' ' << end.version;
}
''', "B 1 9", flags=("-pthread",))

    def test_retry_schedule(self):
        # Explicit teaching model, not an HTTP retry implementation.
        deadline, reserve, per_attempt, minimum = 600, 50, 180, 50
        now=0
        attempts=[]
        for delay in (0,60,120):
            if delay+minimum > deadline-reserve-now:
                break
            now+=delay
            duration=min(per_attempt,deadline-reserve-now)
            attempts.append((now,now+duration))
            now+=duration
        self.assertEqual(attempts,[(0,180),(240,420)])
        self.assertEqual(now,420)
        self.assertEqual(3*3,9)

    def test_full_snapshot_and_queue_model(self):
        version=8
        applied=[]
        for incoming in (8,10,9):
            if incoming>version:
                version=incoming
                applied.append(incoming)
        self.assertEqual(applied,[10])
        self.assertEqual(200/(120-80),5)
        self.assertEqual(1000*200*1024,204800000)
        self.assertAlmostEqual(204800000/1024**2,195.3125)

    def test_closing_sections_have_all_quizzes(self):
        d=station(8)
        for ref in ("retry-budget-workbook","compatibility-rollout",
                    "event-recovery-workbook","api-final-workbook"):
            for kind,qs in d["quizzes"].items():
                with self.subTest(ref=ref,kind=kind):
                    self.assertTrue(any(ref in q["theoryRefs"] for q in qs))

    def test_migration_matrix(self):
        # Check the worked payloads against the explicitly chosen migration rule.
        def accepts(server, command):
            names=set(command)&{"title","caption"}
            allowed={"title","done"} if server==1 else {"title","caption","done"}
            return len(names)==1 and set(command)<=allowed and "done" in command
        c1={"title":"A","done":False}
        c2={"caption":"A","done":False}
        self.assertEqual([accepts(s,c) for c in (c1,c2) for s in (1,2)],
                         [True,True,False,True])
        self.assertFalse(accepts(2,{**c1,**c2}))

    @unittest.skipUnless(shutil.which("google-chrome") and importlib.util.find_spec("websocket"),
                         "requires Google Chrome and Python websocket-client")
    def test_actual_eventsource_incomplete_event_and_resume(self):
        import websocket

        payload=("retry: 10\n\n"+code(8,"event-recovery-workbook")).encode()
        seen_headers=[]
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):
                pass
            def do_GET(self):
                if self.path=="/events":
                    seen_headers.append(self.headers.get("Last-Event-ID"))
                    if len(seen_headers)>1:
                        self.send_response(204)
                        self.end_headers()
                        return
                    body=payload
                    media="text/event-stream"
                else:
                    body=b"<!doctype html><title>SSE check</title>"
                    media="text/html"
                self.send_response(200)
                self.send_header("Content-Type",media)
                self.send_header("Content-Length",str(len(body)))
                self.send_header("Cache-Control","no-store")
                self.end_headers()
                self.wfile.write(body)

        try:
            server=http.server.ThreadingHTTPServer(("127.0.0.1",0),Handler)
        except PermissionError as error:
            self.skipTest(f"Loopback sockets unavailable in this environment: {error}")
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        def stop_server():
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.addCleanup(stop_server)
        profile=tempfile.TemporaryDirectory(prefix="station8-sse-")
        self.addCleanup(profile.cleanup)
        browser=subprocess.Popen([shutil.which("google-chrome"),"--headless","--no-sandbox",
            "--disable-gpu","--remote-debugging-port=0","--remote-allow-origins=http://localhost",
            "--user-data-dir="+profile.name,"about:blank"],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        def stop_browser():
            if browser.poll() is None:
                browser.terminate()
            try: browser.wait(timeout=5)
            except subprocess.TimeoutExpired:
                browser.kill()
                browser.wait(timeout=5)
        self.addCleanup(stop_browser)
        port_file=Path(profile.name)/"DevToolsActivePort"
        for _ in range(100):
            if port_file.exists():
                break
            time.sleep(.05)
        self.assertTrue(port_file.exists(),"Chrome did not expose debugging port")
        port=int(port_file.read_text().splitlines()[0])
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json",timeout=3) as response:
            pages=json.load(response)
        page=next(p for p in pages if p["type"]=="page" and p["url"]=="about:blank")
        ws=websocket.create_connection(page["webSocketDebuggerUrl"],origin="http://localhost",timeout=15)
        self.addCleanup(ws.close)
        serial=0
        def call(method,params):
            nonlocal serial
            serial+=1
            ws.send(json.dumps(dict(id=serial,method=method,params=params)))
            while True:
                response=json.loads(ws.recv())
                if response.get("id")==serial:
                    self.assertNotIn("error",response)
                    return response["result"]
        url=f"http://127.0.0.1:{server.server_port}/"
        call("Page.navigate",dict(url=url))
        for _ in range(100):
            result=call("Runtime.evaluate",dict(expression="location.href",returnByValue=True))
            if result.get("result",{}).get("value")==url:
                break
            time.sleep(.05)
        else:
            self.fail("Browser did not navigate to loopback page")
        result=call("Runtime.evaluate",dict(awaitPromise=True,returnByValue=True,expression=r'''
new Promise((resolve,reject)=>{
    const events=[];
    const source=new EventSource('/events');
    const timer=setTimeout(()=>{source.close(); reject(new Error('SSE timeout'));},5000);
    source.addEventListener('task-changed', event=>{
        events.push({id:event.lastEventId, data:event.data});
    });
    source.onerror=()=>{
        if(source.readyState===EventSource.CLOSED){
            clearTimeout(timer); source.close(); resolve(events);
        }
    };
})
'''))
        self.assertNotIn("exceptionDetails",result)
        events=result["result"]["value"]
        self.assertEqual(events,[dict(id="41",data='{"id":"7",\n"version":8}')])
        self.assertEqual(seen_headers,[None,"41"])


if __name__=="__main__":
    unittest.main()
