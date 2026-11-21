"""Browser-level synthetic app benchmark; external egress prohibited by browser context.

Requires installed Playwright Python and Chromium; does not install or download anything.
Run: PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium python3 -m unittest tests.test_browser_e2e -v
"""
from __future__ import annotations

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

FAULTS = ("checkout", "api_500", "auth_bypass", "ui_regression", "validation", "persistence")

# Original synthetic client, not a customer application.
HTML = """<!doctype html><html><head><title>Checkout</title></head><body>
<h1 id="heading">Checkout</h1><input id="email" value="valid@example.test">
<button id="buy">Buy</button><button id="health">Check health</button>
<button id="admin">Admin</button><button id="orders">Orders</button>
<div id="result" role="status"></div>
<script>
async function call(path, opts) {
  const r = await fetch(path, opts || {});
  let j; try { j = await r.json(); } catch (_) { j = {}; }
  document.getElementById("result").textContent = JSON.stringify({status:r.status,body:j});
}
document.getElementById("buy").onclick = () => call("/checkout",{
  method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({email:document.getElementById("email").value})
});
document.getElementById("health").onclick = () => call("/health");
document.getElementById("admin").onclick = () => call("/admin");
document.getElementById("orders").onclick = () => call("/orders");
</script></body></html>"""


def app(fault):
    state = {"orders": []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, status, payload, kind="application/json"):
            data = (payload if isinstance(payload, str) else json.dumps(payload)).encode()
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/":
                html = HTML.replace('<h1 id="heading">Checkout</h1>',
                                    '<h1 id="heading">BROKEN</h1>') if fault == "ui_regression" else HTML
                return self.reply(200, html, "text/html; charset=utf-8")
            if self.path == "/health":
                return self.reply(500 if fault == "api_500" else 200, {"ok": fault != "api_500"})
            if self.path == "/admin":
                authorized = self.headers.get("Authorization") == "Bearer synthetic-admin"
                if authorized or fault == "auth_bypass":
                    return self.reply(200, {"admin": True})
                return self.reply(403, {"error": "forbidden"})
            if self.path == "/orders":
                return self.reply(200, {"orders": state["orders"]})
            return self.reply(404, {"error": "not_found"})

        def do_POST(self):
            if self.path != "/checkout":
                return self.reply(404, {"error": "not_found"})
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 4096:
                return self.reply(400, {"error": "invalid_size"})
            try:
                body = json.loads(self.rfile.read(size))
            except (ValueError, UnicodeError):
                return self.reply(400, {"error": "invalid_json"})
            if not isinstance(body, dict):
                return self.reply(400, {"error": "invalid_body"})
            email = body.get("email")
            if not isinstance(email, str) or "@" not in email:
                if fault != "validation":
                    return self.reply(422, {"error": "invalid_email"})
            order = {"id": len(state["orders"]) + 1, "email": email}
            if fault != "persistence":
                state["orders"].append(order)
            if fault == "checkout":
                return self.reply(200, {"status": "payment_failed"})
            return self.reply(201, {"status": "confirmed", "order": order})

    return Handler


def observed(page):
    # The content is populated asynchronously through real browser fetch().
    page.locator("#result").get_by_text("", exact=False) if False else None
    page.wait_for_function("document.querySelector('#result').textContent.length > 0")
    return json.loads(page.locator("#result").inner_text())


def scenario(page, fault):
    if fault == "ui_regression":
        return page.locator("#heading").inner_text() == "Checkout"
    if fault == "api_500":
        page.locator("#health").click()
        data = observed(page)
        return data["status"] == 200 and data["body"]["ok"] is True
    if fault == "auth_bypass":
        page.locator("#admin").click()
        return observed(page)["status"] == 403
    if fault == "validation":
        page.locator("#email").fill("invalid")
        page.locator("#buy").click()
        return observed(page)["status"] == 422
    if fault in ("checkout", "persistence"):
        page.locator("#buy").click()
        result = observed(page)
        if result["status"] != 201 or result["body"].get("status") != "confirmed":
            return False
        if fault == "checkout":
            return True
        page.locator("#result").evaluate("(node) => node.textContent = ''")
        page.locator("#orders").click()
        return len(observed(page)["body"]["orders"]) == 1
    raise ValueError(fault)


def benchmark(browser):
    rows = []
    for fault in FAULTS:
        for injected in (False, True):
            server = ThreadingHTTPServer(("127.0.0.1", 0), app(fault if injected else ""))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            context = browser.new_context(service_workers="block")
            # Hard block any request outside localhost, including browser initiated calls.
            context.route("**/*", lambda route: route.continue_()
                          if route.request.url.startswith(("http://127.0.0.1:", "about:"))
                          else route.abort())
            try:
                page = context.new_page()
                page.goto(f"http://127.0.0.1:{server.server_port}/", wait_until="load")
                rows.append({"case": fault, "injected": injected,
                             "detected": not scenario(page, fault)})
            finally:
                context.close()
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
    return {"runner": "playwright_chromium_local", "cases": rows,
            "true_positive": sum(r["detected"] for r in rows if r["injected"]),
            "false_positive": sum(r["detected"] for r in rows if not r["injected"]),
            "network": "browser routes only to 127.0.0.1; enforce OS-level egress deny separately"}


@unittest.skipUnless(sync_playwright, "Playwright not installed; browser tests not run")
class BrowserBenchmarkTests(unittest.TestCase):
    def test_six_seeded_browser_faults_and_clean_controls(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None,
                headless=True, args=["--no-sandbox"])
            try:
                result = benchmark(browser)
                self.assertEqual(result["true_positive"], 6, result)
                self.assertEqual(result["false_positive"], 0, result)
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
