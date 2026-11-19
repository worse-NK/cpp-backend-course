#!/usr/bin/env python3
"""Offline Chrome acceptance of the reader-controlled course experiments.

Run with the same system Python/websocket dependency as test_visual.py. Pass
--roadmap to check an unpacked offline build, --screenshots to keep evidence.
Uses a temporary browser profile, not the installed course or its progress.
"""
import argparse
import base64
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
import websocket

from cdp import CDP, ROOT


def keypress(page, key, code, number):
    for event in ("keyDown", "keyUp"):
        text = {"text": "\r", "unmodifiedText": "\r"} if key == "Enter" and event == "keyDown" else {}
        page.call("Input.dispatchKeyEvent", {"type": event, "key": key, "code": code, **text,
                  "windowsVirtualKeyCode": number, "nativeVirtualKeyCode": number})


def enter(page, selector):
    focused = page.js("(()=>{const el=document.querySelector(" + json.dumps(selector) +
                      ");el?.focus();return !!el && document.activeElement===el && !el.disabled})()")
    assert focused, selector
    keypress(page, "Enter", "Enter", 13)


def capture(page, selector, name, output):
    assert page.js("document.documentElement.scrollWidth <= innerWidth"), name + ": page overflow"
    page.js("document.querySelector(" + json.dumps(selector) + ").scrollIntoView({block:'center',behavior:'instant'})")
    assert page.js("(()=>{const r=document.querySelector(" + json.dumps(selector) +
                   ").getBoundingClientRect();return r.width>0 && r.height>0 && r.top<innerHeight && r.bottom>0})()"), name
    if output:
        data = page.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        (output / (name + ".png")).write_bytes(base64.b64decode(data["data"]))


def experiments(page, roadmap, width, output):
    page.viewport(width, 870)
    page.call("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
    page.call("Network.emulateNetworkConditions", {"offline": True, "latency": 0,
              "downloadThroughput": 0, "uploadThroughput": 0})
    def visit(filename, fragment, ready):
        page.goto((roadmap / filename).as_uri() + ("#" + fragment if fragment else ""), "!!document.querySelector(" + json.dumps(ready) + ")")

    visit("visual_labs.html", "", "#atlasFrame svg")
    page.wait("document.querySelectorAll('.atlas-entries h4 a').length===window.COURSE_LABS.length")
    capture(page, ".atlas-cover", f"atlas-{width}", output)
    for plate in (1, 2, 0):
        enter(page, f'[data-plate="{plate}"]')
        page.wait(f'document.querySelector(\'[data-plate="{plate}"]\').getAttribute("aria-pressed")==="true"')
    page.wait("document.querySelector('#atlasFrame a').hash.includes('reordered')")

    visit("object_lifetime_demo.html", "members", "#lifeStep")
    page.js("document.querySelector('#lifeStep').focus();true")
    for _ in range(5):
        keypress(page, "ArrowRight", "ArrowRight", 39)
    page.wait("document.querySelector('#lifeStep').value==='5' && document.querySelector('#lifeStep').getAttribute('aria-valuetext').includes('Session')")
    capture(page, "#lifeChart", f"lifetime-{width}", output)

    visit("https_journey_lab.html", "scenario=normal&step=18&view=network", ".journey-atlas")
    page.wait("!!document.querySelector('.journey-direction[data-from=server][data-to=client]') && !!document.querySelector('[data-screen-state=received]')")
    capture(page, ".journey-atlas", f"https-{width}", output)
    enter(page, "#next")
    page.wait("!!document.querySelector('[data-screen-state=rendered]') && !document.querySelector('.journey-direction')")

    visit("tcp_delivery_lab.html", "scenario=ordered&step=0", "#try-tcp-order")
    enter(page, "#try-tcp-order")
    page.wait("document.activeElement.id==='tcp-order-title'")
    for segment, ack in [(0, 1005), (2, 1005), (1, 1013)]:
        enter(page, "#tcp-deliver-" + str(segment))
        page.wait("document.querySelector('#tcp-order-ack').textContent.includes('ACK " + str(ack) + "')")
        if segment == 2:
            page.wait("document.querySelector('#tcp-order-tape').dataset.edge==='4'")
            capture(page, "#tcp-order-tape", f"tcp-{width}", output)
    enter(page, "#tcp-order-reset")

    visit("packet_path_lab.html", "scenario=pmtu6&step=0", "#mtu-probe:not([hidden])")
    enter(page, "#mtu-probe summary")
    for size in (1399, 1400, 1401):
        enter(page, "#mtu-send-" + str(size))
        outcome = "Прошёл" if size <= 1400 else "Отброшен"
        page.wait("document.querySelector('#mtu-wan').textContent===" + json.dumps(outcome))
    page.wait("document.querySelector('#mtu-estimate').textContent.includes('1500')")
    enter(page, "#mtu-deliver-ptb")
    page.wait("document.querySelector('#mtu-estimate').textContent.includes('1400') && document.querySelector('#mtu-wan').textContent==='Отброшен'")
    capture(page, "#mtu-ruler", f"mtu-{width}", output)

    visit("visual_labs.html", "lab=vector&scenario=reserved", "#vectorTarget")
    enter(page, "#jumpToExercise")
    page.wait("document.activeElement.id==='vectorChallengeTitle' && location.hash==='#lab=vector&scenario=reserved'")
    page.wait("document.querySelector('#vectorTarget').value==='end'")
    enter(page, "#vectorNo")
    page.wait("document.querySelector('#vectorAnswer').textContent.includes('Верно') && !document.querySelector('#vectorAfter').hidden")
    # Changing the position should not reveal the answer from the previous prediction.
    page.js("document.querySelector('#vectorTarget').focus();true")
    keypress(page, "Home", "Home", 36)
    page.wait("document.querySelector('#vectorTarget').value==='0' && document.querySelector('#vectorAfter').hidden")
    enter(page, "#vectorYes")
    page.wait("document.querySelector('#vectorAnswer').textContent.includes('Верно')")
    capture(page, "#vectorAfter .memory-tape", f"vector-{width}", output)

    visit("visual_labs.html", "lab=sql&scenario=left", "#sqlTraceUser")
    enter(page, "#jumpToExercise")
    page.wait("document.activeElement.id==='sqlTraceTitle' && location.hash==='#lab=sql&scenario=left'")
    enter(page, "#sqlTraceNext")
    enter(page, "#sqlTraceNext")
    page.wait("document.querySelector('#sqlTraceLeft').textContent.includes('Вера: 0') && document.querySelector('#sqlTraceRight').textContent.includes('Нет строки в отчёте')")
    capture(page, ".row-journey", f"sql-{width}", output)
    enter(page, "#sqlTracePrev")
    page.wait("document.querySelector('#sqlTraceStatus').textContent.includes('Фильтр')")

    visit("distributed_lab.html", "scenario=lost-reply&step=0", "#quorum-jump")
    enter(page, "#quorum-jump")
    page.wait("document.activeElement.id==='quorum-title' && location.hash.includes('step=2')")
    for server in ("B", "C"):
        enter(page, "#quorum-" + server)
    page.wait("/3 из 3.*1 из 3/s.test(document.querySelector('#quorum-status').textContent)")
    capture(page, "#quorum-desk .quorum-map", f"raft-{width}", output)
    enter(page, "#quorum-C")
    page.wait("/3 из 3.*2 из 3/s.test(document.querySelector('#quorum-status').textContent)")
    enter(page, "#quorum-reset")
    page.wait("/1 из 3.*1 из 3/s.test(document.querySelector('#quorum-status').textContent)")

    # Test the visible diagram, not just the surrounding transport or step label.
    # The predicate below describes the outcome which should be discernible after
    # these keyboard operations (including thread selection and rewinding).
    def step_plate(lab, mode, selector, keys, predicate):
        visit("visual_labs.html", "lab=" + lab + "&scenario=" + mode, selector)
        q = "document.querySelector(" + json.dumps(selector) + ")"
        page.wait(q + " && document.querySelector('#labRange').value==='0'")
        before = page.js(q + ".outerHTML")
        for button in keys:
            enter(page, button)
        page.wait("((el)=>!!el && !!(" + predicate + "))(" + q + ")")
        after = page.js(q + ".outerHTML")
        assert before != after, f"{lab}/{mode}: the plate never changed"
        assert page.js(q + ".scrollWidth<=" + q + ".clientWidth+1"), f"{selector}: diagram overflow"
        capture(page, selector, f"{lab}-{mode}-{width}", output)
        enter(page, "#labPrev")
        page.wait("document.querySelector('#labRange').value===" + json.dumps(str(len(keys)-1)))
        assert page.js(q + ".outerHTML") != after, f"{lab}/{mode}: plate did not rewind"

    def cpp(lab):
        return '.cpp-plate[data-cpp-plate="' + lab + '"]'

    def svc(kind):
        return '.svc-plate[data-service-plate="' + kind + '"]'

    step_plate("ownership", "cycle", cpp("ownership"), ["#labNext"]*4,
               "[...el.querySelectorAll('.cpp-slip')].map(n=>n.textContent).join('/')==='B.back/A.next'")
    step_plate("temporaries", "cxx20", cpp("temporaries"), ["#labNext"]*3,
               "el.querySelector('.cpp-cell-bad[data-now]') && !el.querySelector('.cpp-cell-read')")
    step_plate("taskownership", "run-task", cpp("taskownership"), ["#labNext"]*3,
               "el.querySelector('[data-holder=worker] .cpp-target[data-alive=true]')")
    step_plate("build", "header", cpp("build"), ["#labNext"]*7,
               "el.querySelectorAll('td.cpp-cell-read').length===3 && el.querySelector('td.cpp-cell-live[data-now]')")
    step_plate("concurrency", "separate", svc("threads"), ["#threadA", "#threadB"],
               "el.querySelectorAll('.svc-beat').length===2 && el.querySelector('.svc-who-B')")
    step_plate("network", "fragmented", svc("stream"), ["#labNext"]*7,
               "el.querySelector('.svc-record')?.textContent==='ABC' && el.querySelectorAll('.svc-read').length===3")
    step_plate("network", "retry", svc("http"), ["#labNext"]*2,
               "el.querySelector('.svc-exchange-row.svc-lost')")
    step_plate("transactions", "rr", svc("versions"), ["#labNext"]*3,
               "[...el.querySelectorAll('.svc-select strong')].map(x=>x.textContent).join('/')==='100/100' && el.querySelector('.svc-db-head strong').textContent==='110'")
    step_plate("transactions", "commit", svc("reservation"), ["#labNext"]*3,
               "el.querySelector('.svc-db-head strong').textContent==='0' && el.querySelector('.svc-inline').textContent.includes('свободна')")
    step_plate("overload", "drain", svc("load"), ["#labNext"]*7,
               "el.querySelectorAll('.svc-shutdown').length===2 && el.querySelector('.svc-label').textContent.includes('7')")

    # The web sources load React from the public CDN; only those sources may
    # skip the reader while networking is disabled. A missing or broken local
    # React distribution must fail on an unpacked desktop build.
    import re
    station = "cpp_station1_modern_cpp.html"
    remote_react = re.search(r'<script\b[^>]*\bsrc=["\'](?:https?:)?//[^"\']*/react(?:@|/)',
                             (roadmap / station).read_text(encoding="utf-8"), re.I)
    if remote_react:
        print(f"SKIP offline station invitation at {width}px: source HTML references remote React")
    else:
        visit(station, "section=ownership-graph", ".experiment-invite")
        assert page.js("document.querySelectorAll('.experiment-invite').length===1")
        anchor = ".experiment-invite a"
        page.wait("document.querySelector(" + json.dumps(anchor) + ").hash.includes('lab=ownership')")
        capture(page, ".experiment-invite", f"station-ownership-{width}", output)
        question = page.js("document.querySelector('.experiment-invite h3').textContent.trim()")
        cta = page.js("document.querySelector('.experiment-invite a').textContent.trim()")
        assert question and cta.startswith("Открыть лабораторию")
        tree = page.call("Accessibility.getFullAXTree")["nodes"]
        roles = {(n.get("role", {}).get("value"), n.get("name", {}).get("value", "").strip())
                 for n in tree if not n.get("ignored")}
        assert ("heading", question) in roles and ("link", cta) in roles, f"Missing accessible lab invitation: {question} / {cta}"
        lab_url = page.js("document.querySelector(" + json.dumps(anchor) + ").href")
        assert lab_url.startswith(roadmap.as_uri()+"/visual_labs.html#"), lab_url
        page.goto(lab_url, "!!document.querySelector('.cpp-plate[data-cpp-plate=ownership]')")
        assert page.js("document.querySelector('#returnLink').hash==='#section=ownership-graph'")


def main(callback=None, report=None):
    """Use a supplied offline acceptance suite or run the default experiments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roadmap", type=Path, default=ROOT.parent / "roadmap")
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)
    binary = shutil.which("google-chrome") or shutil.which("chromium")
    if not binary:
        raise SystemExit("Requires Chrome or Chromium")
    with tempfile.TemporaryDirectory(prefix="course-labs-browser-") as profile:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen([binary, "--headless", "--disable-gpu", "--disable-background-networking",
            "--no-first-run", "--user-data-dir=" + profile, "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=" + str(port), "--remote-allow-origins=http://127.0.0.1:" + str(port),
            "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        page = None
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("Chrome could not start with its normal sandbox")
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1) as response:
                        target = next(t for t in json.load(response) if t["type"] == "page")
                    break
                except (OSError, StopIteration):
                    time.sleep(.1)
            else:
                raise RuntimeError("No temporary browser target")
            page = CDP(target, port)
            for width in (1280, 375):
                (callback or experiments)(page, args.roadmap.resolve(), width, args.screenshots)
            assert not any(e["method"] == "Runtime.exceptionThrown" for e in page.events), "JavaScript exception"
            print(report or "PASS: offline browser experiments, keyboard actions and page fit at 1280 and 375 px")
        finally:
            if page:
                try:
                    page.call("Browser.close")
                except (OSError, websocket.WebSocketException):
                    pass  # Chrome may close the debugging channel before replying.
                page.ws.close()
            elif process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
