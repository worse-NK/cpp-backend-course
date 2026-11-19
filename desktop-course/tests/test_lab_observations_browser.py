#!/usr/bin/env python3
"""File/offline acceptance for DHCP, VPN, SQLite binding and reading one's own record."""
import json

from test_lab_interactions_browser import capture, enter, main as browser_main


def observations(page, roadmap, width, output):
    page.viewport(width, 870)
    page.call("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
    page.call("Network.emulateNetworkConditions", {"offline": True, "latency": 0,
              "downloadThroughput": 0, "uploadThroughput": 0})

    def visit(filename, ready):
        page.goto((roadmap / filename).as_uri(), ready)

    def fit(selector):
        # Page width alone does not catch a clipped child inside a scroll region.
        assert page.js("""(()=>{const r=document.querySelector(%s);return r.offsetWidth>0 &&
          [r,...r.querySelectorAll('*')].every(e=>e.clientWidth===0||e.scrollWidth<=e.clientWidth+2)})()"""
                        % json.dumps(selector)), (selector, width)

    visit("network_setup_lab.html", "!!document.querySelector('[data-lease]')")
    enter(page, '[data-observe="dhcp-ack"]')
    page.wait("document.querySelector('.lease-ticket').dataset.lease==='2' && document.activeElement.dataset.observe==='dhcp-ack'")
    enter(page, '[data-observe="dhcp-announce"]')
    page.wait("document.querySelector('.lease-ticket').dataset.lease==='3'")
    page.js("history.back();true")
    page.wait("document.querySelector('.lease-ticket').dataset.lease==='2'")
    fit("#network-observation")
    capture(page, "#network-observation", f"dhcp-observe-{width}", output)

    visit("vpn_tunnels_lab.html", "!!document.querySelector('[data-observe]')")
    enter(page, '[data-observe="inner-office"]')
    page.wait("document.querySelector('.vpn-envelope').textContent.includes('172.19.115.180')")
    enter(page, '[data-observe="outer-office"]')
    page.wait("document.querySelector('.vpn-udp').textContent.includes('40000 → 51820') && !document.querySelector('.vpn-envelope').textContent.includes('172.19.115.180')")
    fit("#network-observation")
    capture(page, "#network-observation", f"vpn-observe-{width}", output)
    enter(page, '[data-observe="gateway-decrypt"]')
    page.wait("document.querySelector('.vpn-envelope').textContent.includes('10.7.0.2')")

    visit("security_labs.html", "document.querySelector('#case')?.value==='own'")
    enter(page, "#run")
    page.wait("document.querySelectorAll('.access-pair[data-checked=false]').length===2")
    page.js("const p=document.querySelector('#policy');p.value='strict';p.dispatchEvent(new Event('change',{bubbles:true}));true")
    page.wait("!document.querySelector('.access-pair')")
    enter(page, "#run")
    page.wait("document.querySelectorAll('.access-pair[data-checked=true]').length===2")
    fit(".access-pairs")
    capture(page, ".access-pairs", f"own-card-{width}", output)

    visit("security_sql_demo.html", "document.querySelector('#search-term')?.value==='RAII'")
    enter(page, "#stage-4")
    page.wait("document.querySelector('#parameter-value').textContent===JSON.stringify('RAII')")
    sql=page.js("document.querySelector('#sql-code').textContent")
    enter(page, "#preset-quote")
    page.wait("""document.querySelector('#parameter-value').textContent===JSON.stringify("O'Reilly")""")
    assert sql==page.js("document.querySelector('#sql-code').textContent") and "$term" in sql
    enter(page, "#run")
    page.wait("""document.querySelector('#response-count').textContent==='Строк: 1' && document.querySelector('#results').textContent.includes("O'Reilly")""")
    fit("#parameter-box")
    capture(page, "#parameter-box", f"sqlite-bind-{width}", output)


if __name__ == "__main__":
    browser_main(observations, "PASS: DHCP lease snapshots/history, WireGuard observation points, own-record access checks and bound SQLite search (RAII/O'Reilly); offline, keyboard and fit at 1280 and 375 px")
