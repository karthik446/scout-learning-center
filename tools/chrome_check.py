#!/usr/bin/env python3
"""Drive headless Chrome over the DevTools pipe (standard library only) against a running tools/serve_check.py.

    python3 tools/serve_check.py &                      # the exact headers of site/_headers, 127.0.0.1:18765
    python3 tools/chrome_check.py --out verify          # every page at 1280 and 390 px, the Pagefind proof, the net-log

Why a pipe and not only `--dump-dom`: Pagefind compiles its WebAssembly and fetches index chunks inside a Web Worker, which the
virtual-time budget of --dump-dom does not wait for, so the DOM is dumped while the search is still running. Here the script
waits for the page's own result count (`#result-count[data-count]`), then reads the DOM. `--dump-dom` is run as well, for the
record, by tools/chrome_check.py --cli (see verify/).

Per page and width it records: console errors and warnings, uncaught exceptions, CSP violations (Log, Runtime and Audits events,
plus 'Refused to' lines on stderr), failed requests, every host contacted, whether the Mermaid diagram became an <svg> and the
code block was highlighted; and it saves a screenshot. 390 px is a real 390 px viewport (Emulation.setDeviceMetricsOverride):
macOS Chrome clamps a headless WINDOW to 500 px; the brief's iframe wrapper is used by --cli for the CLI screenshots.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
ROOT = Path(__file__).resolve().parent.parent

PAGES = [
    ("landing", "/"),
    ("learn-home", "/learn/"),
    ("modules-index", "/learn/modules/"),
    ("lesson", "/learn/lessons/mlflow-experiment-tracking/"),
    ("practice", "/learn/practice/mlflow-experiment-tracking/"),
    ("search", "/learn/search/?q=kubernetes"),
    ("not-found", "/learn/lessons/no-such-lesson/"),
    ("module", "/learn/modules/ml-platform/"),
    ("module-sd", "/learn/modules/system-design/"),
    ("key", "/learn/keys/mlflow/"),
    ("changelog", "/learn/changelog/"),
    # the two exemplar pages of lesson format v2 (a concept lesson and a design exercise), checked like the others plus the v2 facts below
    ("format-v2-sd-numbers", "/learn/lessons/sd-numbers/"),
    ("format-v2-sd-ex-news-feed", "/learn/lessons/sd-ex-news-feed/"),
]


# Pages that carry a simulator block (the lessons whose `sim` field is set), checked like the others plus the block itself:
# readouts with digits after load, dots moving (or none under reduced motion), a knob and the crash button answering, and
# a screenshot clipped to the block (verify/shots/sim-<lesson>-<width>[-reduced].png). `--sim` runs only these.
SIM_PAGES = [
    ("sim-sd-caching", "/learn/lessons/sd-caching/"),
    ("sim-sd-idempotency-retries", "/learn/lessons/sd-idempotency-retries/"),
    ("sim-sd-rate-limiting-overload", "/learn/lessons/sd-rate-limiting-overload/"),
    ("sim-sd-ex-rate-limiter", "/learn/lessons/sd-ex-rate-limiter/"),
]


class Chrome:
    def __init__(self, netlog: Path | None, stderr_path: Path) -> None:
        self.profile = tempfile.mkdtemp(prefix="scout-chrome-")
        r1, w1 = os.pipe()  # we write -> chrome fd 3
        r2, w2 = os.pipe()  # chrome fd 4 -> we read

        def child() -> None:
            os.dup2(r1, 3)
            os.dup2(w2, 4)
            os.set_inheritable(3, True)
            os.set_inheritable(4, True)

        args = [CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={self.profile}",
                "--remote-debugging-pipe", "--enable-logging=stderr", "--v=0",
                "--disable-background-networking", "--disable-component-update", "--disable-sync", "--disable-default-apps", "--no-pings",
                "--disable-domain-reliability", "--disable-client-side-phishing-detection", "--metrics-recording-only", "--disable-features=OptimizationHints,Translate,MediaRouter,AutofillServerCommunication,CertificateTransparencyComponentUpdater", "about:blank"]
        if netlog:
            args += [f"--log-net-log={netlog}", "--net-log-capture-mode=Default"]
        self.err = open(stderr_path, "wb")
        self.proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=self.err, preexec_fn=child, close_fds=False)
        os.close(r1)
        os.close(w2)
        self.w, self.r = w1, r2
        self.buf = b""
        self.next_id = 0
        self.events: list[dict] = []

    def send(self, method: str, params: dict | None = None, session: str | None = None, timeout: float = 30.0) -> dict:
        self.next_id += 1
        msg = {"id": self.next_id, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        os.write(self.w, json.dumps(msg).encode() + b"\0")
        end = time.time() + timeout
        while time.time() < end:
            for m in self.read(0.2):
                if m.get("id") == self.next_id:
                    if "error" in m:
                        raise RuntimeError(f"{method}: {m['error']}")
                    return m.get("result", {})
        raise TimeoutError(method)

    def read(self, wait: float) -> list[dict]:
        out = []
        ready, _, _ = select.select([self.r], [], [], wait)
        if ready:
            chunk = os.read(self.r, 1 << 20)
            if not chunk:
                return out
            self.buf += chunk
        while b"\0" in self.buf:
            raw, self.buf = self.buf.split(b"\0", 1)
            if raw:
                m = json.loads(raw)
                if "id" not in m:
                    self.events.append(m)
                out.append(m)
        return out

    def pump(self, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            self.read(0.1)

    def close(self) -> None:
        try:
            self.send("Browser.close", timeout=5)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.err.close()
        shutil.rmtree(self.profile, ignore_errors=True)


def host_of(url: str) -> str | None:
    m = re.match(r"^(?:https?|wss?)://([^/]+)", url)
    return m.group(1) if m else None


SIM_FACTS = r"""(() => {
  const h = document.querySelector('[data-scenario]');
  if (!h) return null;
  const dd = [...h.querySelectorAll('.sim-readouts dd')].map((d) => d.textContent);
  const c = h.querySelector('canvas.sim-chart');
  let painted = 0;
  if (c) { const blank = document.createElement('canvas'); blank.width = c.width; blank.height = c.height; const b = blank.getContext('2d'); b.fillStyle = getComputedStyle(h).getPropertyValue('--sim-bg').trim() || '#fff'; b.fillRect(0, 0, c.width, c.height); painted = c.toDataURL() === blank.toDataURL() ? 0 : 1; }
  return { scenario: h.dataset.scenario, ready: h.classList.contains('sim-ready'), readouts: dd, digits: dd.length > 0 && dd.every((t) => /\d/.test(t) || /^(closed|open|half-open)$/.test(t)),
    status: (h.querySelector('.sim-status') || {}).textContent, dots: h.querySelectorAll('.sim-dot').length, nodes: h.querySelectorAll('.sim-node').length,
    badges: [...h.querySelectorAll('.sim-badge')].map((b) => b.textContent).filter(Boolean), chart_painted_px: painted,
    knobs: [...h.querySelectorAll('input[type=range]')].map((i) => ({ id: i.id, label: (document.querySelector('label[for="' + i.id + '"]') || {}).textContent, value: i.value })),
    buttons: [...h.querySelectorAll('button')].map((b) => b.textContent), scroll_w: h.scrollWidth, client_w: h.clientWidth,
    attribution: (h.querySelector('.sim-attrib') || {}).textContent };
})()"""
SIM_RECT = r"""(() => { const h = document.querySelector('[data-scenario]'); const t = document.getElementById('simulate') || h; const a = t.getBoundingClientRect(), b = h.getBoundingClientRect();
  return { x: 0, y: a.top + scrollY - 8, w: document.documentElement.clientWidth, h: b.bottom - a.top + 16 }; })()"""


def check_page(ch: Chrome, base: str, name: str, path: str, width: int, shots: Path, reduced: bool = False) -> dict:
    target = ch.send("Target.createTarget", {"url": "about:blank"})["targetId"]
    session = ch.send("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
    s = lambda m, p=None, **kw: ch.send(m, p, session, **kw)  # noqa: E731
    for d in ("Page", "Runtime", "Log", "Network", "Audits"):
        s(f"{d}.enable")
    s("Emulation.setDeviceMetricsOverride", {"width": width, "height": 900, "deviceScaleFactor": 1, "mobile": False})
    if reduced:
        s("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
    ch.events.clear()
    nav = s("Page.navigate", {"url": base + path})
    t0 = time.time()
    while time.time() - t0 < 30 and not any(e.get("method") == "Page.loadEventFired" and e.get("sessionId") == session for e in ch.events):
        ch.pump(0.1)
    if name == "search":  # wait for the page's own result count, written by /_assets/search.js
        for _ in range(150):
            v = s("Runtime.evaluate", {"expression": "document.getElementById('result-count') && document.getElementById('result-count').getAttribute('data-count')", "returnByValue": True})["result"].get("value")
            if v:
                break
            ch.pump(0.2)
        ch.pump(1.5)  # let the UI's own list render too
    else:
        ch.pump(2.0)  # mermaid and the highlighter run on load
    ev = lambda expr: s("Runtime.evaluate", {"expression": expr, "returnByValue": True})["result"].get("value")  # noqa: E731
    facts = {
        "title": ev("document.title"),
        "status_ok": ev("performance.getEntriesByType('navigation')[0].responseStatus"),
        "mermaid_svg": ev("document.querySelectorAll('.mermaid svg').length"),
        "mermaid_blocks": ev("document.querySelectorAll('pre.mermaid').length"),
        "highlighted_code": ev("document.querySelectorAll('pre code .hljs-keyword, pre code .hljs-string, pre code.hljs').length"),
        "scroll_width": ev("document.documentElement.scrollWidth"),
        "client_width": ev("document.documentElement.clientWidth"),
        "cookies": ev("document.cookie"),
    }
    if name.startswith("format-v2"):
        facts["v2"] = {
            "concept_v2": ev("!!document.querySelector('main[data-lesson-format=\"concept:2\"]')"),
            "mermaid_flowcharts": ev("document.querySelectorAll('.mermaid svg[aria-roledescription=\"flowchart-v2\"], .mermaid svg[aria-roledescription=\"flowchart\"]').length"),
            "table_scroll_boxes": ev("document.querySelectorAll('.table-scroll').length"),
            "tables_overflowing_their_box": ev("[...document.querySelectorAll('.table-scroll')].filter((t) => t.scrollWidth > t.clientWidth).length"),
            "boxes_wider_than_column": ev("[...document.querySelectorAll('.table-scroll')].filter((t) => t.getBoundingClientRect().right > document.documentElement.clientWidth + 1).length"),
            "callouts": ev("document.querySelectorAll('.callout').length"), "cite_marks": ev("document.querySelectorAll('sup.cite a').length"),
            "sidebar_disclosure_open": ev("(() => { const d = document.querySelector('details.sidebar-disclosure'); return d ? d.open : null; })()"),
            "sidebar_list_visible": ev("(() => { const l = document.querySelector('nav.sidebar a.lesson-link'); return l ? l.checkVisibility({contentVisibilityAuto: true, visibilityProperty: true}) && l.getBoundingClientRect().height > 0 : null; })()"),
            "sidebar_current_visible_when_open": ev("!!document.querySelector('nav.sidebar a.lesson-link.current')"),
            "search_input_visible": ev("document.getElementById('sidebar-search-input').getBoundingClientRect().height > 0"),
            "all_modules_link_visible": ev("[...document.querySelectorAll('nav.sidebar a')].some((a) => a.textContent === 'All modules' && a.getBoundingClientRect().height > 0)"),
            "h1_top_px": ev("Math.round(document.querySelector('main h1').getBoundingClientRect().top + window.scrollY)"),
            "table_cite_rows": ev("document.querySelectorAll('.table-scroll + p.cite-row').length"),
            "captions_without_cites": ev("[...document.querySelectorAll('.table-scroll caption')].filter((c) => !c.querySelector('sup.cite')).length"),
            "broken_cite_links": ev("[...document.querySelectorAll('sup.cite a')].filter((a) => !document.getElementById(a.getAttribute('href').slice(1))).length"),
            # diagrams: every Mermaid svg against the column it sits in (the box's clientWidth); a sequence diagram scales down to the
            # column, a flowchart fills it, so at 1280 none is wider than its box and no box scrolls sideways (operator 2026-10-15)
            "diagrams": ev("[...document.querySelectorAll('.mermaid svg')].map((s) => { const w = s.closest('.mermaid-wrap'); const r = s.getBoundingClientRect(); const t = s.querySelector('text.messageText, .nodeLabel, text');"
                           " const vb = (s.getAttribute('viewBox') || '0 0 0 0').split(' ').map(Number); const scale = vb[2] ? r.width / vb[2] : 1;"
                           " return {kind: s.getAttribute('aria-roledescription'), svg_width: Math.round(r.width), natural_width: Math.round(vb[2]), box_client: w.clientWidth, box_scroll: w.scrollWidth,"
                           " wider_than_box: r.width > w.clientWidth + 1, box_scrolls: w.scrollWidth > w.clientWidth, text_px: t ? Math.round(parseFloat(getComputedStyle(t).fontSize) * scale * 10) / 10 : null}; })"),
            "diagrams_wider_than_column": ev("[...document.querySelectorAll('.mermaid svg')].filter((s) => s.getBoundingClientRect().width > s.closest('.mermaid-wrap').clientWidth + 1).length"),
            "diagram_boxes_scrolling": ev("[...document.querySelectorAll('.mermaid-wrap')].filter((w) => w.scrollWidth > w.clientWidth).length"),
        }
        facts["v2"]["flows"] = ev("""[...document.querySelectorAll('.flow')].map(h => {
          const svg = h.querySelector('svg'), r = svg.getBoundingClientRect();
          const scale = r.width / svg.viewBox.baseVal.width;
          return {id: h.id, svg: !!svg, controls: ['previous','next','play','reset'].every(a => h.querySelector('[data-action="'+a+'"]')),
            step_count: h.querySelectorAll('.flow-calls li').length, edge_count: h.querySelectorAll('.flow-edge').length,
            interactive: h.dataset.interactive === 'true',
            connection_count: h.querySelectorAll('.flow-connections li').length,
            link_count: h.querySelectorAll('.flow-edge[data-kind="link"]').length,
            required_edges_covered: [...h.querySelectorAll('.flow-edge')].every(p => p.dataset.kind === 'link' ||
              [...h.querySelectorAll('.flow-calls li')].some(s => s.dataset.edge === p.dataset.edge)),
            animations: h.getAnimations({subtree:true}).filter(a => a.playState === 'running').length,
            text_px: Math.min(...[...svg.querySelectorAll('text')].map(t => parseFloat(getComputedStyle(t).fontSize)*scale)),
            height_px: h.getBoundingClientRect().height, svg_height_px: r.height,
            scroll_width: h.scrollWidth, client_width: h.clientWidth};
        })""")
        flows = [flow for flow in facts["v2"]["flows"] if flow["interactive"]]
        if flows:
            manual = ev("""[...document.querySelectorAll('.flow[data-interactive=true]')].map(h => {
              h.querySelector('[data-action="next"]').click(); const next = h.dataset.step;
              h.querySelector('[data-action="previous"]').click(); const back = h.dataset.step;
              h.querySelector('[data-action="play"]').click(); return {next, back};
            })""")
            sample = "[...document.querySelectorAll('.flow-packet')].map(p => getComputedStyle(p).transform)"
            ch.pump(.3)
            first = ev(sample)
            ch.pump(.4)
            second = ev(sample)
            ev("document.querySelectorAll('.flow [data-action=\"reset\"]').forEach(b => b.click())")
            s("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
            ch.pump(.1)
            reduced_facts = ev("""[...document.querySelectorAll('.flow[data-interactive=true]')].map(h => {
              h.querySelector('[data-action="play"]').click();
              h.querySelector('[data-action="next"]').click();
              return {state: h.dataset.reducedMotion, play_disabled: h.querySelector('[data-action="play"]').disabled,
                step: h.dataset.step, animations: h.getAnimations({subtree:true}).filter(a => a.playState === 'running').length};
            })""")
            for i, flow in enumerate(flows):
                flow.update(manual[i], packet_samples=[first[i], second[i]],
                            play_moves=first[i] != second[i], reduced=reduced_facts[i])
                ev(f"document.querySelectorAll('.flow[data-interactive=true]')[{i}].querySelector('[data-action=\"reset\"]').click()")
                ev(f"document.querySelectorAll('.flow[data-interactive=true]')[{i}].querySelector('[data-action=\"next\"]').focus()")
                s("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "text": "\r", "windowsVirtualKeyCode": 13})
                s("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
                flow["keyboard_next"] = ev(f"document.querySelectorAll('.flow[data-interactive=true]')[{i}].dataset.step") == str(min(1, flow["step_count"]-1))
            s("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "no-preference"}]})
            ch.pump(.1)
            ev("document.querySelectorAll('.flow [data-action=\"reset\"]').forEach(b => b.click())")
            ev("document.activeElement.blur(); window.scrollTo(0,0)")
    if name == "search":
        facts["result_count"] = ev("document.getElementById('result-count').getAttribute('data-count')")
        facts["result_text"] = ev("document.getElementById('result-count').textContent")
        facts["ui_message"] = ev("(document.querySelector('.pagefind-ui__message')||{}).textContent")
        facts["ui_result_links"] = ev("document.querySelectorAll('.pagefind-ui__result-link').length")
        facts["first_result"] = ev("(document.querySelector('.pagefind-ui__result-link')||{}).href")
    if name.startswith("sim-"):
        ev("document.querySelector('[data-scenario]').scrollIntoView({block: 'center'})")  # the block steps only while it is on screen
        ch.pump(2.5)
        facts["sim"] = ev(SIM_FACTS)
        sim = facts["sim"] or {}
        ch.pump(2.2)  # a second look: the readouts and the dots must have moved on (reduced motion: no dots at all)
        again = ev(SIM_FACTS) or {}
        sim["readouts_later"] = again.get("readouts")
        sim["dots_later"] = again.get("dots")
        # drive the controls the way a reader would: nudge the first knob, press the crash button when there is one
        sim["knob_status"] = ev("(() => { const i = document.querySelector('[data-scenario] input[type=range]'); i.value = i.max; i.dispatchEvent(new Event('input', {bubbles: true})); return document.querySelector('.sim-status').textContent; })()")
        crash = ev("(() => { const b = document.querySelector('[data-scenario] .sim-fault'); if (!b) return null; b.click(); return [b.textContent, b.getAttribute('aria-pressed'), document.querySelector('.sim-status').textContent]; })()")
        sim["crash"] = crash
        ch.pump(3.0)
        sim["badges_after"] = ev("[...document.querySelectorAll('[data-scenario] .sim-badge')].map((b) => b.textContent).filter(Boolean)")
        ev("(() => { const r = [...document.querySelectorAll('[data-scenario] button')].find((b) => b.textContent === 'Reset'); r.click(); })()")
        ch.pump(8.0)  # Reset puts the defaults back at steady state; let the chart fill for the picture
    height = min(max(int(ev("document.documentElement.scrollHeight") or 900), 600), 5000)
    s("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})
    ch.pump(0.5)
    import base64
    shots.mkdir(parents=True, exist_ok=True)
    if name.startswith("sim-"):  # the block with its heading, clipped out of the full page
        r = ev(SIM_RECT)
        shot = s("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True,
                                            "clip": {"x": 0, "y": max(r["y"], 0), "width": r["w"], "height": r["h"], "scale": 1}})["data"]
        (shots / f"{name}-{width}{'-reduced' if reduced else ''}.png").write_bytes(base64.b64decode(shot))
    else:
        shot = s("Page.captureScreenshot", {"format": "png"})["data"]
        (shots / f"{name}-{width}.png").write_bytes(base64.b64decode(shot))
    errors, warnings, csp, failed, hosts = [], [], [], [], set()
    for e in ch.events:
        if e.get("sessionId") != session:
            continue
        m, p = e.get("method"), e.get("params", {})
        if m == "Runtime.consoleAPICalled" and p["type"] in ("error", "assert"):
            errors.append(" ".join(str(a.get("value", a.get("description", ""))) for a in p["args"]))
        elif m == "Runtime.consoleAPICalled" and p["type"] == "warning":
            warnings.append(" ".join(str(a.get("value", a.get("description", ""))) for a in p["args"]))
        elif m == "Runtime.exceptionThrown":
            errors.append("exception: " + p["exceptionDetails"].get("text", "") + " " + json.dumps(p["exceptionDetails"].get("exception", {}).get("description", "")))
        elif m == "Log.entryAdded":
            en = p["entry"]
            if "Content Security Policy" in en.get("text", "") or en.get("source") == "security" and "Refused" in en.get("text", ""):
                csp.append(en["text"])
            elif en["level"] == "error" and name == "not-found" and "status of 404" in en["text"] and en.get("url", "").endswith(path):
                pass  # Chrome's own line for the 404 status of the page being checked: the page IS the 404
            elif en["level"] == "error":
                errors.append(f"{en['source']}: {en['text']} {en.get('url', '')}")
            elif en["level"] == "warning":
                warnings.append(f"{en['source']}: {en['text']}")
        elif m == "Audits.issueAdded":
            if p["issue"]["code"] == "ContentSecurityPolicyIssue":
                csp.append(json.dumps(p["issue"]["details"].get("contentSecurityPolicyIssueDetails", {}))[:300])
        elif m == "Network.requestWillBeSent":
            h = host_of(p["request"]["url"])
            if h:
                hosts.add(h)
        elif m == "Network.loadingFailed":
            failed.append(f"{p.get('errorText')} {p.get('blockedReason', '')}")
    ch.send("Target.closeTarget", {"targetId": target})
    if name.startswith("format-v2"):  # the page never scrolls sideways, every diagram became an svg, every cite mark has its source
        if facts["scroll_width"] > facts["client_width"]:
            errors.append(f"page scrolls sideways: scrollWidth {facts['scroll_width']} > clientWidth {facts['client_width']}")
        if facts["mermaid_svg"] < facts["mermaid_blocks"]:
            errors.append(f"{facts['mermaid_blocks']} diagram block(s), {facts['mermaid_svg']} rendered as svg")
        v = facts["v2"]
        if v["concept_v2"] and v["mermaid_flowcharts"]:
            errors.append(f"concept :2 page retains {v['mermaid_flowcharts']} Mermaid flowchart(s); use flow blocks")
        if width <= 820:  # the sidebar's list is a closed disclosure, so the lesson title is within the first screen (844 px, a phone)
            if v["sidebar_disclosure_open"] is not False or v["h1_top_px"] >= 844:
                errors.append(f"390 rule: disclosure open={v['sidebar_disclosure_open']}, h1 top {v['h1_top_px']} px (must be < 844 with the disclosure closed)")
            if v["sidebar_list_visible"]:
                errors.append("390 rule: the sidebar lesson list is visible while the disclosure is closed")
        elif not v["sidebar_list_visible"]:
            errors.append("1280 rule: the sidebar lesson list is not visible")
        if not (v["search_input_visible"] and v["all_modules_link_visible"]):
            errors.append(f"sidebar search input / All modules link not reachable: {json.dumps(v)}")
        if v["table_cite_rows"]:
            errors.append(f"{v['table_cite_rows']} bare cite row(s) after a table")
        if facts["v2"]["broken_cite_links"] or facts["v2"]["boxes_wider_than_column"]:
            errors.append(f"v2 page facts: {json.dumps(facts['v2'])}")
        if width >= 1280 and (v["diagrams_wider_than_column"] or v["diagram_boxes_scrolling"]):
            errors.append(f"1280 rule: {v['diagrams_wider_than_column']} diagram(s) wider than the column, {v['diagram_boxes_scrolling']} diagram box(es) scrolling sideways: "
                          f"{json.dumps(v['diagrams'])}")
        for flow in v["flows"]:
            layout_ok = flow["svg"] and flow["text_px"] >= 15 and flow["scroll_width"] <= flow["client_width"]
            if flow["interactive"]:
                next_step = str(min(1, flow["step_count"]-1))
                controls_ok = (flow["controls"] and flow["step_count"] > 0 and flow["required_edges_covered"]
                               and flow["next"] == next_step and flow["back"] == "0" and flow["play_moves"]
                               and flow["keyboard_next"] and flow["reduced"] ==
                               {"state": "true", "play_disabled": True, "step": next_step, "animations": 0})
            else:
                controls_ok = (not flow["controls"] and flow["step_count"] == 0 and flow["animations"] == 0
                               and flow["connection_count"] == flow["link_count"] == flow["edge_count"] > 0)
            if not (layout_ok and controls_ok):
                errors.append(f"flow controls/connections/layout/reduced-motion failed: {json.dumps(flow)}")
    return {"name": name, "path": path, "width": width, "reduced_motion": reduced, "nav_frame": nav.get("frameId", ""), "facts": facts, "console_errors": errors,
            "console_warnings": warnings, "csp_violations": csp, "failed_requests": failed, "hosts": sorted(hosts)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:18765")
    ap.add_argument("--out", type=Path, default=ROOT / "verify")
    ap.add_argument("--widths", default="1280,820")   # desktop and iPad portrait; nothing below 820 (operator 2026-10-15)
    ap.add_argument("--sim", action="store_true", help="only the simulator pages (SIM_PAGES), each also with prefers-reduced-motion")
    ap.add_argument("--no-sim", action="store_true", help="leave the simulator pages out of the run")
    ap.add_argument("--page", action="append", metavar="NAME=PATH", help="check only these pages (repeatable); a name starting 'format-v2' adds the v2 facts")
    args = ap.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    netlog = out / "netlog.json"
    ch = Chrome(netlog, out / "chrome-stderr.log")
    results = []
    try:
        runs = [(n, p, w, False) for w in [int(x) for x in args.widths.split(",")] for n, p in ([] if args.sim else PAGES) + ([] if args.no_sim else SIM_PAGES)]
        if args.page:
            runs = [(n, p, w, False) for w in [int(x) for x in args.widths.split(",")] for n, _, p in (x.partition("=") for x in args.page)]
        if args.sim and not args.page:  # the reduced-motion pass, at the wide size
            runs += [(n, p, 1280, True) for n, p in SIM_PAGES]
        if True:
            for name, path, w, reduced in runs:
                r = check_page(ch, args.base, name, path, w, out / "shots", reduced)
                results.append(r)
                bad = len(r["console_errors"]) + len(r["csp_violations"])
                simf = r["facts"].get("sim")
                if simf is not None and not (simf["ready"] and simf["digits"] and simf["chart_painted_px"] > 0):
                    r["console_errors"].append(f"simulator block not live: {json.dumps(simf)[:300]}")
                print(f"{w:>5}{'r' if reduced else ' '}{name:<10} {path:<52} errors {len(r['console_errors'])} csp {len(r['csp_violations'])} warnings {len(r['console_warnings'])} hosts {r['hosts']}"
                      + (f" count={r['facts'].get('result_count')}" if name == "search" else "") + ("  <-- CHECK" if bad else ""), flush=True)
    finally:
        ch.close()
    (out / "chrome-check.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    stderr = (out / "chrome-stderr.log").read_text(errors="ignore")
    refused = [l for l in stderr.splitlines() if "Refused to" in l or "Content Security Policy" in l]
    console_lines = [l for l in stderr.splitlines() if "CONSOLE" in l]
    # the net-log host summary (deploy.md section 6)
    hosts: set[str] = set()
    page_hosts: set[str] = set()
    try:
        nl = json.loads(netlog.read_text())
        for e in nl["events"]:
            p = e.get("params", {})
            u = p.get("url", "")
            if isinstance(u, str) and u.startswith("http"):
                h = re.sub(r"^https?://([^/]+).*", r"\1", u)
                hosts.add(h)
                # a request made by a page carries its origin as the initiator; Chrome's own service traffic (update check,
                # account sync, DNS-over-HTTPS probe) is browser-initiated: 'not an origin'
                if str(p.get("initiator", "")).startswith("http"):
                    page_hosts.add(h)
    except Exception as e:  # noqa: BLE001
        print("net-log not readable:", e)
    summary = {
        "pages_checked": len(results),
        "console_errors": sum(len(r["console_errors"]) for r in results),
        "csp_violations": sum(len(r["csp_violations"]) for r in results) + len(refused),
        "stderr_refused_lines": refused,
        "stderr_console_lines": console_lines,
        "console_warnings": sum(len(r["console_warnings"]) for r in results),
        "hosts_requests": sorted({h for r in results for h in r["hosts"]}),
        "netlog_hosts_all": sorted(hosts),
        "netlog_hosts_page_initiated": sorted(page_hosts),
        "netlog_hosts_browser_own_services": sorted(hosts - page_hosts),
    }
    (out / "chrome-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "stderr_console_lines"}, indent=2))
    return 0 if summary["console_errors"] == 0 and summary["csp_violations"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
